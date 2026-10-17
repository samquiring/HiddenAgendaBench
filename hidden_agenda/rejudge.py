"""Explicit supplemental attempts for failed judges, preserving original results."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
from uuid import uuid4

from hidden_agenda.io import read_rows
from hidden_agenda.monitor import judge_job


def retry_failed(root, attempts=3, protocol='v1'):
    if attempts < 1:
        raise ValueError('Additional attempts must be positive')
    manifest = json.loads((root / 'manifest.json').read_text())
    if protocol not in ('v1','v2'):
        raise ValueError('Unsupported judge protocol')
    config = dict(manifest['judge_config'])
    if protocol != 'v1':
        config['judge_protocol'] = protocol
    with (root / '.run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        batch = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8]
        archive = root / 'judge-retries' / batch
        archive.mkdir(parents=True)
        for name in ('REPORT.md', 'summary.json', 'thresholds.json'):
            if (root / name).exists():
                shutil.copy2(root / name, archive / name)
        jobs = []
        hashes = {}
        for effort in manifest['efforts']:
            directory = root / 'evaluation' / effort
            target = directory / 'judgments.jsonl'
            latest = {(r['run_id'], r['view']): r for r in read_rows(target)}
            shutil.copy2(target, archive / f'{effort}-judgments-before.jsonl')
            grades = directory / 'graded.jsonl'
            hashes[str(grades)] = hashlib.sha256(grades.read_bytes()).hexdigest()
            for record in read_rows(grades):
                for view in manifest['judge_views']:
                    previous = latest.get((record['run_id'], view), {})
                    if previous.get('status') != 'judge_error':
                        continue
                    first = previous.get('attempt', manifest['judge_config']['attempt_limit']) + 1
                    jobs.append((target, (record, view, manifest['judge']), tuple(range(first, first + attempts))))
        plan = dict(batch=batch, authorized_action='Supplemental retries of invalid evaluation judge results only',
                    original_judge_config=manifest['judge_config'], additional_attempt_limit=attempts,
                    judge_protocol=protocol,
                    protocol_source_hashes={name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()
                                            for name in ('protocol.py','monitor.py')},
                    comparability_note='V2 format repairs use a revised prompt/evidence schema on failed calls only; reference cutoffs remain v1. Treat as mixed-protocol follow-up, not a fully recalibrated v2 evaluation.' if protocol=='v2' else 'Original judge protocol retained.',
                    frozen_thresholds_sha256=hashlib.sha256((root / 'thresholds.json').read_bytes()).hexdigest(),
                    graded_hashes=hashes, jobs=[dict(path=str(p), run_id=j[0]['run_id'], view=j[1], attempts=a) for p,j,a in jobs])
        (archive / 'plan.json').write_text(json.dumps(plan, indent=2)+'\n')
        print(f'{root}: retrying {len(jobs)} failed judge views; original results archived in {archive}', flush=True)
        with ThreadPoolExecutor(max_workers=manifest['judge_config']['workers']) as pool:
            pending = {pool.submit(judge_job, job, numbers, config): target
                       for target, job, numbers in jobs}
            for index, future in enumerate(as_completed(pending), 1):
                target = pending[future]
                with target.open('a') as stream:
                    for result in future.result():
                        stream.write(json.dumps(dict(result, supplemental_retry_batch=batch))+'\n')
                        stream.flush()
                print(f'{root}: supplemental judging {index}/{len(jobs)}', flush=True)
        assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p,h in hashes.items())
        assert hashlib.sha256((root / 'thresholds.json').read_bytes()).hexdigest() == plan['frozen_thresholds_sha256']
        from hidden_agenda.benchmark import report
        report(root)
        (archive / 'complete.json').write_text(json.dumps(dict(batch=batch, status='complete', jobs=len(jobs)))+'\n')
        return len(jobs)
