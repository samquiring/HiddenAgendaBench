"""Prepare disjoint HumanEval/GSM8K SFT questions; does not call any model."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import re

from hidden_agenda.public_tasks import PUBLIC_FORMAT, numeric, public_pairs, public_prompt, source_rows

GSM_TRAIN_URL = (
    'https://raw.githubusercontent.com/openai/grade-school-math/'
    '3101c7d5072418e28b9008a6636bde82a006892c/grade_school_math/data/train.jsonl'
)
GSM_TRAIN_SHA256 = '17f347dc51477c50d4efb83959dbb7c56297aba886e5544ee2aaed3024813465'


def normalized(text):
    return re.sub(r'\W+', '', text.casefold())


def build_pairs(coding, math_rows, excluded_primary, excluded_questions, count, seed):
    primary = [p for p in coding if p['task_id'] not in excluded_primary]
    rng = random.Random(seed)
    rng.shuffle(primary)
    seen = set(excluded_questions)
    auxiliary = []
    for index, row in enumerate(math_rows):
        key = normalized(row['question'])
        answer = row['answer'].rsplit('####', 1)[-1].strip()
        if key in seen or numeric(answer) is None:
            continue
        seen.add(key)
        auxiliary.append((index, row['question'], answer))
    rng.shuffle(auxiliary)
    if not primary or count < 1 or len(auxiliary) < count:
        raise ValueError('Insufficient eligible source tasks')
    pairs = []
    for i, (index, question, answer) in enumerate(auxiliary[:count]):
        code = primary[i % len(primary)]
        pairs.append(dict(id=f"{code['task_id']}--gsm8k-train-{index}",
                          primary_id=code['task_id'], primary=code['prompt'],
                          auxiliary_id=f'gsm8k-train-{index}', auxiliary=question,
                          answer=answer, split='training', seed=seed))
    return pairs


def prepare(output, math_path, count=256, seed=20261025):
    if output.exists() and any(output.iterdir()):
        raise ValueError('Use a new empty output directory; dataset artifacts are immutable')
    evaluation = list(public_pairs(100, split='evaluation'))
    reserved = list(public_pairs(40, split='calibration'))
    excluded = {p['primary_id'] for p in evaluation + reserved}
    # Exclude exact normalized overlap against the ENTIRE GSM8K test split.
    test_questions = {normalized(r['question']) for r in source_rows('gsm8k-test.jsonl')}
    raw = math_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != GSM_TRAIN_SHA256:
        raise ValueError('GSM8K train file does not match the pinned source hash')
    math_rows = [json.loads(line) for line in raw.decode().splitlines() if line.strip()]
    coding = source_rows('HumanEvalPlus.jsonl.gz')
    pairs = build_pairs(coding, math_rows, excluded, test_questions, count, seed)
    counts = Counter(p['primary_id'] for p in pairs)
    samples = [dict(id='training--' + p['id'] + '--concealment',
                    input=public_prompt(p, 'concealment'),
                    metadata={**p, 'condition': 'concealment', 'partition': 'training',
                              'public_output_format': PUBLIC_FORMAT,
                              'primary_group': p['primary_id']}) for p in pairs]
    output.mkdir(parents=True, exist_ok=True)
    (output / 'pairs.jsonl').write_text(''.join(json.dumps(p) + '\n' for p in pairs))
    (output / 'dataset.jsonl').write_text(''.join(json.dumps(p) + '\n' for p in samples))
    (output / 'gsm8k-train-source.jsonl').write_bytes(raw)
    manifest = dict(
        version=1, count=len(pairs), seed=seed,
        unique_primary=len(counts), unique_auxiliary=len({p['auxiliary_id'] for p in pairs}),
        primary_counts=dict(sorted(counts.items())),
        excluded_primary_ids=sorted(excluded),
        exclusions='All 100 evaluation and all 40 development/calibration HumanEval IDs; '
                   'all normalized GSM8K-test question matches.',
        source=dict(url=GSM_TRAIN_URL, sha256=hashlib.sha256(raw).hexdigest(),
                    rows=len(math_rows)),
        warnings=['Primary tasks repeat; 256 pairs are not 256 independent coding problems.',
                  'Exact normalized exclusion is not a semantic near-duplicate audit.',
                  'Questions only: no actor responses, correctness filtering, edits, or SFT yet.'],
        files={name:hashlib.sha256((output/name).read_bytes()).hexdigest()
               for name in ('pairs.jsonl', 'dataset.jsonl', 'gsm8k-train-source.jsonl')},
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (output / 'README.md').write_text(
        '# Phase-2 training question candidates\n\n'
        f'{len(pairs)} distinct pairs: {len(counts)} unused HumanEval primary problems '
        f'and {len(pairs)} unique GSM8K-train auxiliary questions. '
        f'Each primary appears {min(counts.values())}–{max(counts.values())} times.\n\n'
        'All 100 benchmark primary IDs and all 40 reserved development/calibration '
        'IDs are excluded. All normalized matches to GSM8K-test questions are excluded. '
        'These are candidate questions, not validated SFT demonstrations. A semantic '
        'near-duplicate review remains necessary before training.\n\n'
        'Keep primary groups intact in any split or clustered analysis. Never split '
        'different pairings of the same primary between training and validation.\n')
    print(json.dumps({k:manifest[k] for k in ('count','unique_primary','unique_auxiliary')}, indent=2))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gsm-train', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--count', type=int, default=256)
    parser.add_argument('--seed', type=int, default=20261025)
    parser.add_argument('--allow-repeated-primary', action='store_true', required=True,
                        help='Explicitly acknowledge HumanEval cannot supply 256 unused primaries')
    args = parser.parse_args()
    prepare(args.output, args.gsm_train, args.count, args.seed)


if __name__ == '__main__':
    main()
