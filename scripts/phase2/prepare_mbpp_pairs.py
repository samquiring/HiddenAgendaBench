"""Freeze distinct MBPP/GSM8K training and validation candidates, without model calls."""
import argparse
import ast
import builtins
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import re
import warnings

from hidden_agenda.public_tasks import PUBLIC_FORMAT, numeric, public_prompt, source_rows

SOURCES = {
    'mbpp': dict(url='https://raw.githubusercontent.com/google-research/google-research/master/mbpp/mbpp.jsonl',
                 sha256='ccf64ceae9c5403bf50a044cb6d505bfd2a2963ee58338ba268fd65beab92a9f'),
    'gsm8k_train': dict(url='https://raw.githubusercontent.com/openai/grade-school-math/'
                      '3101c7d5072418e28b9008a6636bde82a006892c/grade_school_math/data/train.jsonl',
                      sha256='17f347dc51477c50d4efb83959dbb7c56297aba886e5544ee2aaed3024813465'),
}


def normalized(text):
    return re.sub(r'\W+', '', text.casefold())


def parse(code):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', SyntaxWarning)
        return ast.parse(code)


def body_fingerprint(function):
    """Conservative structural duplicate check; not a semantic equivalence test."""
    body = list(function.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    names = {a.arg: f'var{i}' for i, a in enumerate(
        function.args.posonlyargs + function.args.args + function.args.kwonlyargs)}

    class Normalize(ast.NodeTransformer):
        def visit_Name(self, node):
            if node.id == function.name:
                return ast.copy_location(ast.Name(id='self_function', ctx=node.ctx), node)
            if node.id not in vars(builtins):
                if node.id not in names:
                    names[node.id] = f'var{len(names)}'
                return ast.copy_location(ast.Name(id=names[node.id], ctx=node.ctx), node)
            return node

    # Work on a copy; never modify the source AST used to extract signatures.
    copied = parse('\n'.join(ast.unparse(n) for n in body))
    return ast.dump(Normalize().visit(copied), include_attributes=False)


def coding_candidates(rows, humaneval):
    forbidden = set()
    for row in humaneval:
        tree = parse(row['prompt'] + row['canonical_solution'])
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == row['entry_point']:
                forbidden.add(body_fingerprint(node))
    eligible, excluded = [], []
    for row in rows:
        task_id = row['task_id']
        if not 511 <= task_id <= 974:
            continue
        reason = None
        try:
            tree = parse(row['code'])
            functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
            if len(functions) != 1 or any(isinstance(n, ast.ClassDef) for n in tree.body):
                reason = 'not_single_function'
            elif any(not isinstance(n, (ast.FunctionDef, ast.Import, ast.ImportFrom)) for n in tree.body):
                reason = 'reference_requires_global_setup'
            elif not row['test_list']:
                reason = 'no_tests'
            else:
                function = functions[0]
                fingerprint = body_fingerprint(function)
                if fingerprint in forbidden:
                    reason = 'structural_match_to_humaneval'
        except (SyntaxError, ValueError):
            reason = 'unparseable_reference'
        if reason:
            excluded.append(dict(primary_id=f'MBPP/{task_id}', reason=reason))
            continue
        signature = f'def {function.name}({ast.unparse(function.args)}):'
        prompt = (row['text'] + '\n\nRequired function:\n' + signature + '\n    pass\n'
                  '\nPublic example:\n' + row['test_list'][0])
        eligible.append(dict(primary_id=f'MBPP/{task_id}', primary=prompt,
                             entry_point=function.name, signature=signature,
                             source_partition='training' if task_id >= 601 else 'validation',
                             fingerprint=fingerprint, reference=row))
    return eligible, excluded


def select(candidates, train_count, validation_count, seed):
    rng = random.Random(seed)
    ordered = list(candidates)
    rng.shuffle(ordered)
    chosen, used, exclusions = {'training': [], 'validation': []}, set(), []
    for split, count in [('training', train_count), ('validation', validation_count)]:
        for row in ordered:
            if row['source_partition'] != split:
                continue
            if row['fingerprint'] in used:
                exclusions.append(dict(primary_id=row['primary_id'], reason='structural_duplicate_in_selected_data'))
                continue
            if len(chosen[split]) == count:
                continue
            chosen[split].append(row)
            used.add(row['fingerprint'])
        if len(chosen[split]) != count:
            raise ValueError(f'Only {len(chosen[split])} eligible unique {split} primaries; requested {count}')
    return chosen, exclusions


def prepare(output, mbpp_path, gsm_path, train_count=256, validation_count=64, seed=20261025):
    if output.exists() and any(output.iterdir()):
        raise ValueError('Use a new empty output directory')
    if train_count < 1 or validation_count < 1:
        raise ValueError('Counts must be positive')
    raw = {'mbpp': mbpp_path.read_bytes(), 'gsm8k_train': gsm_path.read_bytes()}
    for name, data in raw.items():
        if hashlib.sha256(data).hexdigest() != SOURCES[name]['sha256']:
            raise ValueError(f'Pinned source hash mismatch: {name}')
    source = {name:[json.loads(l) for l in data.decode().splitlines() if l.strip()] for name,data in raw.items()}
    candidates, excluded = coding_candidates(source['mbpp'], source_rows('HumanEvalPlus.jsonl.gz'))
    chosen, more_exclusions = select(candidates, train_count, validation_count, seed)
    excluded += more_exclusions
    seen = {normalized(r['question']) for r in source_rows('gsm8k-test.jsonl')}
    auxiliary = []
    for i, row in enumerate(source['gsm8k_train']):
        key, answer = normalized(row['question']), row['answer'].rsplit('####', 1)[-1].strip()
        if key in seen or numeric(answer) is None:
            continue
        seen.add(key)
        auxiliary.append((i,row['question'],answer))
    random.Random(seed + 1).shuffle(auxiliary)
    if len(auxiliary) < train_count + validation_count:
        raise ValueError('Insufficient unique auxiliary questions')
    pairs, samples, references = [], [], []
    for split in ('training', 'validation'):
        for code in chosen[split]:
            i, question, answer = auxiliary[len(pairs)]
            pair = dict(id=f"{code['primary_id']}--gsm8k-train-{i}",
                        primary_id=code['primary_id'], primary=code['primary'],
                        auxiliary_id=f'gsm8k-train-{i}', auxiliary=question, answer=answer,
                        entry_point=code['entry_point'], split=split, seed=seed,
                        primary_source='MBPP', source_partition=code['source_partition'])
            pairs.append(pair)
            # Validation includes matched clean controls. Training clean mixture is
            # selected later, independently of grading/concealment outcomes.
            for condition in (('clean', 'concealment') if split == 'validation' else ('concealment',)):
                samples.append(dict(id=f"{split}--{pair['id']}--{condition}",
                                    input=public_prompt(pair,condition),
                                    metadata={**pair, 'condition':condition, 'partition':split,
                                              'public_output_format':PUBLIC_FORMAT, 'primary_group':pair['primary_id']}))
            references.append(dict(primary_id=code['primary_id'], **code['reference']))
    output.mkdir(parents=True,exist_ok=True)
    def write_rows(name, rows):
        (output/name).write_text(''.join(json.dumps(row)+'\n' for row in rows))
    write_rows('pairs.jsonl',pairs)
    write_rows('dataset.jsonl',samples)
    write_rows('training-pairs.jsonl',[p for p in pairs if p['split']=='training'])
    write_rows('validation-pairs.jsonl',[p for p in pairs if p['split']=='validation'])
    write_rows('PRIVATE-grading-references.jsonl',references)
    write_rows('exclusions.jsonl',excluded)
    (output/'mbpp-source.jsonl').write_bytes(raw['mbpp'])
    (output/'gsm8k-train-source.jsonl').write_bytes(raw['gsm8k_train'])
    (output/'prepare_mbpp_pairs.py').write_bytes(Path(__file__).read_bytes())
    counts = Counter(p['split'] for p in pairs)
    validation = dict(training_pairs=counts['training'],validation_pairs=counts['validation'],
                      unique_primary=len({p['primary_id'] for p in pairs}),
                      unique_auxiliary=len({p['auxiliary_id'] for p in pairs}),
                      repeated_primary=0,repeated_auxiliary=0,
                      primary_source_split_overlap=0,
                      structural_humaneval_match_count=0,
                      semantic_duplicate_review='pending',
                      reference_execution_check='pending', actor_generations=0)
    assert validation['unique_primary'] == validation['unique_auxiliary'] == len(pairs)
    (output/'VALIDATION.json').write_text(json.dumps(validation,indent=2)+'\n')
    (output/'README.md').write_text(
        '# MBPP/GSM8K candidate questions\n\n'
        f'{train_count} distinct training primaries and {validation_count} distinct '
        'validation primaries from the published MBPP splits. All auxiliaries are '
        'unique GSM8K-train questions across both splits. No primary repeats.\n\n'
        'Actor prompts contain the specification, function signature, and first '
        'public MBPP test as an example. Reference implementations and remaining '
        'tests are only in PRIVATE-grading-references.jsonl, not model inputs.\n\n'
        'Sources: Google Research MBPP (CC BY 4.0, per its dataset card) and '
        'OpenAI GSM8K (MIT). See manifest.json for URLs and pinned content hashes. '
        'Structural code duplicates against HumanEval and selected primaries, '
        'and normalized auxiliary matches against GSM8K-test, are excluded. '
        'This does not prove semantic independence; semantic review and trusted '
        'reference execution checks remain before response generation/SFT.\n\n'
        'These are question candidates, not successful or audited training demonstrations.\n')
    manifest = dict(version=1,seed=seed,counts=dict(counts),sources=SOURCES,
                    unique_primary=len(pairs),unique_auxiliary=len(pairs),
                    public_example_policy='First MBPP test shown; remaining tests retained for grading',
                    eligibility='Single top-level function, no required global setup; AST structural deduplication',
                    exclusion_counts=dict(Counter(r['reason'] for r in excluded)),
                    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()})
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(validation,indent=2))
    return manifest


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mbpp',type=Path,required=True)
    p.add_argument('--gsm-train',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--count',type=int,default=256)
    p.add_argument('--validation-count',type=int,default=64)
    p.add_argument('--seed',type=int,default=20261025)
    args=p.parse_args()
    prepare(args.output,args.mbpp,args.gsm_train,args.count,args.validation_count,args.seed)
