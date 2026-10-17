"""Uniform rejudging of saved trajectories, without actor calls or code execution."""
from copy import deepcopy
import fcntl
import hashlib
import json
from pathlib import Path

from hidden_agenda.io import read_rows


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_dataset(roots, manifests, output):
    """One final judgment per assigned view; retain skipped/unavailable outcomes."""
    records, judgments = [], []
    for root, manifest in zip(roots,manifests):
        for partition in ('calibration','evaluation'):
            for effort in manifest['efforts']:
                directory = root/partition/effort
                saved = read_rows(directory/'graded.jsonl')
                latest = {(r['run_id'],r['view']):r for r in read_rows(directory/'judgments.jsonl')}
                expected = {(r['run_id'],view) for r in saved for view in manifest['judge_views']}
                if set(latest)!=expected:
                    raise ValueError(f'{directory}: missing or unexpected final judge views')
                if any(r.get('judge_protocol')!='v2' for r in latest.values()):
                    raise ValueError(f'{directory}: non-v2 judgment in uniform dataset')
                context = dict(model_run=root.name,partition=partition,effort=effort)
                records.extend(dict(r,**context) for r in saved)
                judgments.extend(dict(latest[key],**context) for key in sorted(expected))
    for name, values in [('trajectories.jsonl',records),('judgments.jsonl',judgments)]:
        target = output/name
        temporary = output/(name+'.tmp')
        with temporary.open('w') as stream:
            for value in values:stream.write(json.dumps(value)+'\n')
        temporary.replace(target)
    return dict(trajectories=len(records),final_judgments=len(judgments))


def prepare_replay(source, destination, workers=24, attempts=6):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if workers < 1 or attempts < 1:
        raise ValueError('workers and attempts must be positive')
    original = json.loads((source/'manifest.json').read_text())
    inputs = {str(source/'manifest.json'):digest(source/'manifest.json')}
    for partition in ('calibration','evaluation'):
        for effort in original['efforts']:
            path = source/partition/effort/'graded.jsonl'
            records = read_rows(path)
            assigned = [s for s in original['samples'] if s['metadata']['partition']==partition]
            expected = {(s['metadata']['id'],s['metadata']['condition']) for s in assigned}
            actual = {(r['id'],r['condition']) for r in records}
            if actual != expected or len(records)!=len(expected) or len({r['run_id'] for r in records})!=len(expected):
                raise ValueError(f'{path}: incomplete or duplicate saved actor grades')
            inputs[str(path)] = digest(path)
    manifest = deepcopy(original)
    manifest['judge_config'].update(judge_protocol='v2', workers=workers, attempt_limit=attempts)
    manifest['replay_only'] = True
    manifest['judge_replay'] = dict(source=str(source), input_hashes=inputs,
        protocol_source_hashes={name:digest(Path(__file__).parent/name) for name in ('protocol.py','monitor.py')},
        policy='Fresh uniform v2 calibration and evaluation judgments; reuse saved actor outputs and deterministic grades only.')
    destination.mkdir(parents=True,exist_ok=True)
    path = destination/'manifest.json'
    if path.exists():
        if json.loads(path.read_text())!=manifest:
            raise ValueError(f'{destination}: replay configuration or source data changed')
    else:
        with path.open('x') as stream:
            json.dump(manifest,stream,indent=2)
    for partition in ('calibration','evaluation'):
        for effort in manifest['efforts']:
            src = source/partition/effort/'graded.jsonl'
            target = destination/partition/effort/'graded.jsonl'
            target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():
                if digest(target)!=digest(src):
                    raise ValueError(f'{target}: actor grades differ from source')
            else:
                with target.open('xb') as stream:
                    stream.write(src.read_bytes())
    return manifest


def replay_all(sources, output, workers=24, attempts=6):
    from hidden_agenda.benchmark import judge, thresholds, reuse_thresholds, report
    from hidden_agenda.comparison import load_runs
    sources = [Path(p).resolve() for p in sources]
    output = Path(output).resolve()
    if len(sources)<2 or len({p.name for p in sources})!=len(sources):
        raise ValueError('Provide at least two source runs with distinct directory names')
    output.mkdir(parents=True,exist_ok=True)
    with (output/'.replay.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        destinations = [output/p.name for p in sources]
        manifests = [prepare_replay(s,d,workers,attempts) for s,d in zip(sources,destinations)]
        # This check reads only existing source results; it cannot generate actors.
        load_runs(sources, [0,128,512,2048,8192], require_tokens=False)
        plan = dict(sources=list(map(str,sources)), destinations=list(map(str,destinations)),
                    judge=manifests[0]['judge'], judge_protocol='v2',workers=workers,attempt_limit=attempts,
                    calibration_source=str(destinations[0]),
                    rule='Freeze maximum of 30 valid v2 clean calibration scores per view; transfer to every target before evaluation calls.')
        path = output/'replay-plan.json'
        if path.exists() and json.loads(path.read_text())!=plan:
            raise ValueError('Replay plan differs from frozen plan')
        if not path.exists():
            with path.open('x') as stream:json.dump(plan,stream,indent=2)
        for root,manifest in zip(destinations,manifests):
            for effort in manifest['efforts']:
                judge(root/'calibration'/effort,manifest)
        cutoffs = thresholds(destinations[0])
        if any(r['threshold'] is None for views in cutoffs.values() for r in views.values()):
            raise RuntimeError('V2 reference calibration incomplete; evaluation calls not started')
        for root in destinations[1:]:
            reuse_thresholds(root,destinations[0])
        print('Uniform v2 thresholds frozen before evaluation: '+json.dumps(cutoffs),flush=True)
        for root,manifest in zip(destinations,manifests):
            for effort in manifest['efforts']:
                judge(root/'evaluation'/effort,manifest)
            report(root)
        for root,manifest in zip(destinations,manifests):
            for path,expected in manifest['judge_replay']['input_hashes'].items():
                if digest(Path(path))!=expected:
                    raise ValueError(f'Source input changed during replay: {path}')
        from hidden_agenda.comparison import compare
        compare(destinations,output/'comparison',openai_reference=True)
        counts=export_dataset(destinations,manifests,output)
        (output/'complete.json').write_text(json.dumps(dict(status='complete',runs=list(map(str,destinations)),**counts))+'\n')
        print(f'Uniform v2 comparison: {output/"comparison/REPORT.md"}',flush=True)
