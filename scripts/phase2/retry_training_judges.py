"""Repair only unresolved training annotations/verdicts, preserving all valid results."""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from judge_training import rows, append, classify, report, CONFIG, JUDGE
from hidden_agenda.monitor import judge_job


def run(root, workers=6, nonempty_evidence_reminder=False):
    import fcntl
    with (root/'.run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        records=[r for r in rows(root/'graded.jsonl') if r['actor_status']=='ok']
        all_categories=rows(root/'categories.jsonl')
        all_judges=rows(root/'judgments.jsonl')
        cats={r['run_id']:r for r in all_categories}
        judges={(r['run_id'],r['view']):r for r in all_judges}
        jobs=[]
        for r in records:
            old=cats.get(r['run_id'])
            if not old or old['status']!='ok':
                last=max((x.get('attempt',0) for x in all_categories if x['run_id']==r['run_id']),default=0)
                jobs.append(('category',r,None,last))
        for r in records:
            for view in ('reasoning','reasoning_output'):
                old=judges.get((r['run_id'],view))
                if not old or old['status']!='ok':
                    last=max((x.get('attempt',0) for x in all_judges if x['run_id']==r['run_id'] and x['view']==view),default=0)
                    jobs.append(('judge',r,view,last))
        config={**CONFIG,'nonempty_evidence_reminder':nonempty_evidence_reminder}
        plan=dict(created_at=datetime.now(timezone.utc).isoformat(),workers=workers,
                  nonempty_evidence_reminder=nonempty_evidence_reminder,
                  category_jobs=sum(j[0]=='category' for j in jobs),
                  monitor_jobs=sum(j[0]=='judge' for j in jobs),
                  policy='Only unresolved results retried; valid judgments and actor responses unchanged. '
                         'Original category attempts retained; two extra monitor attempts per failed view. '
                         'Stop scheduling after four consecutive network-failed jobs.',
                  prior_hashes={name:hashlib.sha256((root/name).read_bytes()).hexdigest()
                                for name in ('graded.jsonl','categories.jsonl','judgments.jsonl')},
                  script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        append(root/'annotation-repair-plans.jsonl',plan)
        print(json.dumps(plan,indent=2),flush=True)

        def work(job):
            kind,r,view,last=job
            if kind=='category':
                result=classify(r)
                for row in result:
                    row['attempt']+=last
                    row['repair_round']='network-recovery-v1'
                return kind,result
            return kind,judge_job((r,view,JUDGE),(last+1,last+2),config)

        pending_jobs=iter(jobs)
        failures=0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            running={}
            for _ in range(workers):
                job=next(pending_jobs,None)
                if job is not None:running[pool.submit(work,job)]=job
            finished=0
            stopped=False
            while running:
                done,_=wait(running,return_when=FIRST_COMPLETED)
                for future in done:
                    running.pop(future)
                    kind,result=future.result()
                    target=root/('categories.jsonl' if kind=='category' else 'judgments.jsonl')
                    for row in result:append(target,row)
                    last=result[-1]
                    network_failure=last['status']!='ok' and any(s in last.get('error','') for s in ('ConnectionError','TimeoutError','timed out','resolve host'))
                    failures=failures+1 if network_failure else 0
                    finished+=1
                    if finished%20==0 or finished==len(jobs):print(f'Repair progress: {finished}/{len(jobs)} jobs',flush=True)
                    if failures>=4:stopped=True
                    if not stopped:
                        job=next(pending_jobs,None)
                        if job is not None:running[pool.submit(work,job)]=job
        report(root)
        if stopped:raise RuntimeError('Network remained unavailable; stopped further scheduling and preserved completed results')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path('runs/qwen38-27b-mbpp-training-judged-v1'))
    p.add_argument('--workers',type=int,default=6)
    p.add_argument('--nonempty-evidence-reminder',action='store_true',
                   help='Record a prompt amendment reminding the judge to cite only nonempty lines; validation is unchanged')
    a=p.parse_args()
    if a.workers<1 or a.workers>12:p.error('workers must be between 1 and 12')
    awake=subprocess.Popen(['/usr/bin/caffeinate','-i','-w',str(os.getpid())]) if sys.platform=='darwin' else None
    try:run(a.root,a.workers,a.nonempty_evidence_reminder)
    finally:
        if awake is not None:awake.terminate();awake.wait(timeout=10)
