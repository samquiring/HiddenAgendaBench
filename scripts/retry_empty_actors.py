"""One explicit retry of empty/error actor calls; preserve the source dataset."""
import argparse
from collections import defaultdict
from copy import deepcopy
import fcntl
import hashlib
import json
from pathlib import Path

from dotenv import load_dotenv
from hidden_agenda.benchmark import append, rows, report
from hidden_agenda.judge_replay import export_dataset


def failed_call(row):
    return row['actor_status'] != 'ok' or not (row.get('output') or '').strip()


def repair(source, output, timeout=None, time_limit=None, actor_override=None):
    from inspect_ai import Task, eval
    from inspect_ai.dataset import Sample
    from inspect_ai.model import get_model
    from inspect_ai.solver import generate
    from hidden_agenda.public_pipeline import export_public_log, grade_public_records
    from hidden_agenda.monitor import judge_job
    from hidden_agenda.comparison import compare

    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output:
        raise ValueError('Use a separate output directory')
    output.mkdir(parents=True, exist_ok=True)
    load_dotenv('.env')
    with (output / '.repair.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        records = rows(source / 'trajectories.jsonl')
        targets = [r for r in records if failed_call(r)]
        plan = dict(source=str(source), attempts=1,
                    selection='Actor error or empty final response, independent of grades and monitor outcomes. Nonempty formatting/answer failures are not retried.',
                    inputs={name: hashlib.sha256((source/name).read_bytes()).hexdigest()
                            for name in ('trajectories.jsonl', 'judgments.jsonl')},
                    targets=[{k:r[k] for k in ('model_run','partition','effort','run_id','id','condition')} for r in targets])
        if timeout is not None or time_limit is not None:
            plan.update(timeout_override=timeout,time_limit_override=time_limit)
        if actor_override is not None:
            plan['actor_override'] = actor_override
        plan_path = output / 'actor-retry-plan.json'
        if plan_path.exists() and json.loads(plan_path.read_text()) != plan:
            raise ValueError('Frozen retry plan differs')
        plan_path.write_text(json.dumps(plan, indent=2))
        by_model = defaultdict(list)
        for row in targets:
            by_model[row['model_run']].append(row)
        replacements = {}
        for model, selected in by_model.items():
            manifest = json.loads((source/model/'manifest.json').read_text())
            actor = actor_override or manifest['actor']
            if actor.rsplit(':',1)[0] != manifest['actor'].rsplit(':',1)[0]:
                raise ValueError('Provider repairs must use the same model identifier')
            work = output / 'actor-retries' / model
            work.mkdir(parents=True, exist_ok=True)
            graded_path = work / 'graded.jsonl'
            saved = rows(graded_path)
            if not saved:
                paths = sorted((work/'actors').glob('*.eval'))
                if not paths:
                    keys = {(r['partition'],r['id'],r['condition']) for r in selected}
                    samples = [Sample(**s) for s in manifest['samples']
                               if (s['metadata']['partition'],s['metadata']['id'],s['metadata']['condition']) in keys]
                    print(f'Retrying {len(samples)} empty/error calls: {model}', flush=True)
                    actor_config = dict(manifest['actor_config'])
                    if timeout is not None:
                        actor_config['timeout'] = timeout
                    if time_limit is not None:
                        actor_config['time_limit'] = time_limit
                    eval(Task(dataset=samples,solver=generate()),
                         model=get_model(actor,**manifest.get('actor_args',{'stream':False})),
                         reasoning_effort=manifest['efforts'][0], **actor_config,
                         log_dir=str(work/'actors'), display='plain')
                    paths = sorted((work/'actors').glob('*.eval'))
                exported = [r for p in paths for r in export_public_log(p)]
                expected = {(r['partition'],r['id'],r['condition']) for r in selected}
                actual = {(r['partition'],r['id'],r['condition']) for r in exported}
                if actual != expected or len(exported) != len(expected):
                    raise RuntimeError(f'{model}: retry logs incomplete; inspect before resuming')
                for row in grade_public_records(exported):
                    row['requested_effort'] = manifest['efforts'][0]
                    append(graded_path,row)
                saved = rows(graded_path)
            for original in selected:
                replacement = next(r for r in saved if (r['partition'],r['id'],r['condition']) ==
                                   (original['partition'],original['id'],original['condition']))
                replacements[(model,original['run_id'])] = replacement

        roots, manifests = [], []
        for model in dict.fromkeys(r['model_run'] for r in records):
            src, dst = source/model, output/model
            manifest = deepcopy(json.loads((src/'manifest.json').read_text()))
            previous = manifest.get('actor_retries')
            manifest['actor_retries'] = dict(source=str(src),plan=str(plan_path),previous=previous,
                timeout_override=timeout,time_limit_override=time_limit,
                actor_override=actor_override if by_model[model] else None,
                count=len(by_model[model]),policy='One retry per failed call; use retry regardless of score. Original attempts remain in source and retry logs.')
            dst.mkdir(parents=True,exist_ok=True)
            (dst/'manifest.json').write_text(json.dumps(manifest,indent=2))
            for name in ('thresholds.json','calibration-transfer.json'):
                if (src/name).exists():
                    (dst/name).write_bytes((src/name).read_bytes())
            for partition in ('calibration','evaluation'):
                for effort in manifest['efforts']:
                    old = src/partition/effort
                    new = dst/partition/effort
                    new.mkdir(parents=True,exist_ok=True)
                    repaired = [replacements.get((model,r['run_id']),r) for r in rows(old/'graded.jsonl')]
                    (new/'graded.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in repaired))
                    # Reuse every unchanged judgment; only new actor responses need judging.
                    existing = rows(old/'judgments.jsonl')
                    unchanged = [j for j in existing if (model,j['run_id']) not in replacements]
                    retry_judgments = new/'retry-judgments.jsonl'
                    latest = {(j['run_id'],j['view']):j for j in rows(retry_judgments)}
                    for r in repaired:
                        if r['run_id'] not in {v['run_id'] for (m,_),v in replacements.items() if m==model}:
                            continue
                        for view in manifest['judge_views']:
                            if (r['run_id'],view) in latest:
                                continue
                            attempts = tuple(range(1,manifest['judge_config']['attempt_limit']+1))
                            for j in judge_job((r,view,manifest['judge']),attempts,manifest['judge_config']):
                                append(retry_judgments,j)
                                latest[(r['run_id'],view)] = j
                    combined = unchanged+list(latest.values())
                    (new/'judgments.jsonl').write_text(''.join(json.dumps(j)+'\n' for j in combined))
            report(dst)
            roots.append(dst)
            manifests.append(manifest)
        counts = export_dataset(roots,manifests,output)
        compare(roots,output/'comparison',openai_reference=True)
        audit = [{**{k:r[k] for k in ('model_run','id','condition','partition','run_id')},
                  'retry_run_id':replacements[(r['model_run'],r['run_id'])]['run_id'],
                  'retry_actor_status':replacements[(r['model_run'],r['run_id'])]['actor_status']}
                 for r in targets]
        (output/'complete.json').write_text(json.dumps(dict(status='complete',**counts,retries=audit),indent=2))
        print(f'Repaired dataset: {output}',flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default='runs/judge-v2-uniform')
    parser.add_argument('--output', default='runs/judge-v2-repaired')
    parser.add_argument('--timeout', type=int, help='Explicit request-timeout override for a separate repair round')
    parser.add_argument('--time-limit', type=int, help='Explicit sample wall-clock limit override for a separate repair round')
    parser.add_argument('--actor', help='Explicit alternate provider route for the same model; recorded per repaired response')
    args = parser.parse_args()
    repair(args.source,args.output,args.timeout,args.time_limit,args.actor)
