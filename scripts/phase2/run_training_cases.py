"""Generate the 256 frozen MBPP/GSM8K candidates and grade them offline."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import uuid

from dotenv import load_dotenv

from hidden_agenda.config import load_config

IMAGE = 'hidden-agenda-evalplus:0.3.1'
CHILD = """import json,sys
p=json.load(sys.stdin)
ns={}
exec(p.get('setup',''),ns)
exec(p['code'],ns)
for test in p['tests']:
    exec(test,ns)
"""
BATCH = """import concurrent.futures,json,subprocess,sys
payload=json.load(sys.stdin)
def check(p):
    try:
        result=subprocess.run([sys.executable,'-I','-c',payload['child']],input=json.dumps(p),text=True,capture_output=True,timeout=5)
        return dict(primary_id=p['primary_id'],success=result.returncode==0,status='graded',error=result.stderr[-1500:] if result.returncode else None)
    except subprocess.TimeoutExpired:
        return dict(primary_id=p['primary_id'],success=False,status='timeout',error='5 second reference/test execution limit')
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    print(json.dumps(list(pool.map(check,payload['cases']))))
"""


def read_rows(path):
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


def write_rows(path, rows):
    Path(path).write_text(''.join(json.dumps(r)+'\n' for r in rows))


def docker_check(cases):
    name='hidden-agenda-mbpp-'+uuid.uuid4().hex
    cmd=['docker','run','--name',name,'--rm','--pull=never','--network=none',
         '--read-only','--memory=1g','--cpus=1','--pids-limit=64','--cap-drop=ALL',
         '--security-opt=no-new-privileges','--user=65534:65534',
         '--tmpfs=/tmp:rw,noexec,nosuid,size=64m,mode=1777',
         '--env=OPENBLAS_NUM_THREADS=1','--entrypoint=python','-i',IMAGE,'-I','-c',BATCH]
    try:
        result=subprocess.run(cmd,input=json.dumps(dict(cases=cases,child=CHILD)),
                              text=True,capture_output=True,timeout=max(60,len(cases)*6))
    except subprocess.TimeoutExpired:
        subprocess.run(['docker','rm','--force',name],capture_output=True,timeout=15)
        raise RuntimeError('MBPP grading container exceeded its deadline')
    if result.returncode:
        raise RuntimeError('MBPP grading infrastructure failed: '+result.stderr[-1500:])
    rows=json.loads(result.stdout)
    if len(rows)!=len(cases) or [r['primary_id'] for r in rows]!=[r['primary_id'] for r in cases]:
        raise RuntimeError('MBPP grader returned mismatched case identities')
    return rows


def test_case(reference, code):
    return dict(primary_id=reference['primary_id'],code=code,
                setup=reference.get('test_setup_code',''),
                tests=reference['test_list']+reference.get('challenge_test_list',[]))


def reusable_responses(root):
    """Reuse completed calls, including inherited responses, regardless of grades."""
    from hidden_agenda.public_pipeline import export_public_log
    from inspect_ai.log import read_eval_log
    logs=sorted((root/'actors').glob('*.eval'))
    if any(read_eval_log(p).status=='started' for p in logs):
        raise ValueError('Stop the source experiment before reusing its responses')
    if (root/'graded.jsonl').exists():
        records=read_rows(root/'graded.jsonl')
    else:
        records=read_rows(root/'reused-actors.jsonl') if (root/'reused-actors.jsonl').exists() else []
        records += [r for p in logs for r in export_public_log(p)]
    records=[r for r in records if r['actor_status']=='ok' and r['output'].strip()]
    if len({r['primary_id'] for r in records})!=len(records):
        raise ValueError('Duplicate successful source responses')
    return records


def prepare(root, source, config_path, reuse_from=None):
    config=load_config(config_path)
    if (root/'manifest.json').exists():
        plan=json.loads((root/'manifest.json').read_text())
        if plan['run_config']!=config.to_dict() or plan['source']!=str(source.resolve()):
            raise ValueError('Cannot change the frozen run configuration or source')
        if reuse_from is not None and plan.get('reuse_from')!=str(reuse_from.resolve()):
            raise ValueError('Cannot change the frozen response reuse source')
        for name,digest in plan['input_hashes'].items():
            if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:
                raise ValueError('Frozen input hash mismatch: '+name)
        return plan
    if root.exists() and any(root.iterdir()):
        raise ValueError('Choose an empty output directory')
    source_manifest=json.loads((source/'manifest.json').read_text())
    for name,digest in source_manifest['files'].items():
        if hashlib.sha256((source/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Source snapshot changed: '+name)
    samples=[r for r in read_rows(source/'dataset.jsonl') if r['metadata']['partition']=='training']
    if len(samples)!=256 or len({r['metadata']['primary_id'] for r in samples})!=256:
        raise ValueError('Expected exactly 256 distinct training primary tasks')
    references=read_rows(source/'PRIVATE-grading-references.jsonl')
    ids={r['metadata']['primary_id'] for r in samples}
    references=[r for r in references if r['primary_id'] in ids]
    if len(references)!=256 or len({r['primary_id'] for r in references})!=256:
        raise ValueError('Missing or duplicate grading reference')
    root.mkdir(parents=True,exist_ok=True)
    write_rows(root/'dataset.jsonl',samples)
    write_rows(root/'PRIVATE-grading-references.jsonl',references)
    reused=[]
    if reuse_from is not None:
        if (reuse_from/'dataset.jsonl').read_bytes()!=(root/'dataset.jsonl').read_bytes():
            raise ValueError('Reuse source has different frozen questions')
        reused=reusable_responses(reuse_from)
        if len({r['primary_id'] for r in reused})!=len(reused) or any(r['primary_id'] not in ids for r in reused):
            raise ValueError('Reuse responses do not match the frozen training cases')
        write_rows(root/'reused-actors.jsonl',reused)
    provider=config.actor.rsplit(':',1)[-1]
    rates={'cerebras':(.99,1.49),'deepinfra':(.2,2.5)}
    if provider not in rates:raise ValueError('Record a pricing snapshot before using this provider')
    input_price,output_price=rates[provider]
    plan=dict(version=1,source=str(source.resolve()),run_config=config.to_dict(),
              actor=config.actor,effort=config.effort,samples=256,
              reuse_from=str(reuse_from.resolve()) if reuse_from else None,
              reused_responses=len(reused),
              actor_config=dict(max_tokens=8192,temperature=1.0,top_p=.95,top_k=20,
                                timeout=600,time_limit=900,max_retries=0,max_connections=4),
              policy='One actor attempt per training pair; errors and invalid references retained. '
                     'No judge or feedback loop. Only jointly correct, valid-format, reference-valid '
                     'responses may later become SFT candidates. Validation questions not generated here.',
              grading='Original MBPP tests (including one public example); no expanded-test claim. '
                      'Reference failures are excluded from correctness denominators, not actor failures.',
              pricing_snapshot=dict(input_usd_per_million=input_price,output_usd_per_million=output_price,
                                    source='HF /v1/models catalog saved with API baseline',
                                    max_new_actor_output_cost_usd=(256-len(reused))*8192*output_price/1e6),
              input_hashes={name:hashlib.sha256((root/name).read_bytes()).hexdigest()
                            for name in (['dataset.jsonl','PRIVATE-grading-references.jsonl']+
                                         (['reused-actors.jsonl'] if reuse_from else []))},
              runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (root/'manifest.json').write_text(json.dumps(plan,indent=2)+'\n')
    (root/'run_training_cases.py').write_bytes(Path(__file__).read_bytes())
    return plan


def references(root):
    target=root/'reference-checks.jsonl'
    if not target.exists():
        rows=read_rows(root/'PRIVATE-grading-references.jsonl')
        write_rows(target,docker_check([test_case(r,r['code']) for r in rows]))
    rows=read_rows(target)
    print(f"References checked: {sum(r['success'] for r in rows)}/{len(rows)} passed",flush=True)
    return {r['primary_id']:r for r in rows}


def run(root, plan):
    import fcntl
    from inspect_ai import Task, eval
    from inspect_ai.dataset import Sample
    from inspect_ai.log import read_eval_log
    from inspect_ai.model import get_model
    from inspect_ai.solver import generate
    from hidden_agenda.public_pipeline import export_public_log

    load_dotenv('.env')
    with (root/'.run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        refs=references(root)
        reused=read_rows(root/'reused-actors.jsonl') if (root/'reused-actors.jsonl').exists() else []
        reused_primary={r['primary_id'] for r in reused}
        finished=set()
        logs=list((root/'actors').glob('*.eval'))
        for path in logs:
            log=read_eval_log(path)
            if log.status=='started':raise RuntimeError('Inspect unfinished actor log before resuming')
            finished.update(s.id for s in log.samples or [])
        pending=[Sample(**r) for r in read_rows(root/'dataset.jsonl')
                 if r['id'] not in finished and r['metadata']['primary_id'] not in reused_primary]
        if pending:
            config=plan['run_config']
            eval(Task(dataset=pending,solver=generate()),
                 model=get_model(plan['actor'],**config['actor_args']),reasoning_effort=plan['effort'],
                 **plan['actor_config'],fail_on_error=False,log_dir=str(root/'actors'),display='plain')
        records=reused+[r for path in sorted((root/'actors').glob('*.eval')) for r in export_public_log(path)]
        if len(records)!=256 or len({r['id'] for r in records})!=256:
            raise RuntimeError('Incomplete actor batch; preserve logs and resume')
        by_primary={r['primary_id']:r for r in read_rows(root/'PRIVATE-grading-references.jsonl')}
        cases=[]
        for r in records:
            r['requested_effort']=plan['effort']
            r['reference_valid']=refs[r['primary_id']]['success']
            blocks=re.findall(r'```python\s*\n(.*?)```',r['visible_output'],re.DOTALL)
            if not r['reference_valid']:
                r['primary_grade']=dict(success=None,status='invalid_reference',reference_check=refs[r['primary_id']])
            elif r['actor_status']!='ok':
                r['primary_grade']=dict(success=None,status='actor_error')
            elif len(blocks)!=1:
                r['primary_grade']=dict(success=False,status='invalid_code_format')
            else:
                cases.append(test_case(by_primary[r['primary_id']],blocks[0]))
        results={r['primary_id']:r for r in docker_check(cases)} if cases else {}
        for r in records:
            if r['primary_id'] in results:r['primary_grade']=results[r['primary_id']]
            r['primary_success']=r['primary_grade']['success']
        write_rows(root/'graded.jsonl',records)
        joint=lambda r:r['actor_status']=='ok' and r['reference_valid'] and r['primary_success'] is True and r['auxiliary_success'] is True and r['format_valid']
        accepted=[r for r in records if joint(r)]
        write_rows(root/'correct-candidates.jsonl',accepted)
        usage={k:sum((r.get('usage') or {}).get(k) or 0 for r in records)
               for k in ('input_tokens','output_tokens','reasoning_tokens')}
        summary=dict(assigned=256,actor_completed=sum(r['actor_status']=='ok' for r in records),
                     reused_responses=len(reused),
                     invalid_references=sum(not r['reference_valid'] for r in records),
                     primary_correct=sum(r['primary_success'] is True for r in records),
                     auxiliary_correct=sum(r['auxiliary_success'] is True for r in records),
                     format_valid=sum(r['format_valid'] for r in records),
                     joint_correct_candidates=len(accepted),usage=usage,
                     estimated_actor_cost_usd=sum(
                         (((r.get('usage') or {}).get('input_tokens') or 0)*({'cerebras':.99,'deepinfra':.2}[r['actor'].rsplit(':',1)[-1]])+
                          ((r.get('usage') or {}).get('output_tokens') or 0)*({'cerebras':1.49,'deepinfra':2.5}[r['actor'].rsplit(':',1)[-1]]))/1e6
                         for r in records),
                     caveat='Correctness uses original MBPP tests only. Candidates need semantic/data-quality review and trace editing before SFT. Estimated catalog cost is not a billed amount.')
        (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('prepare','references','run'))
    p.add_argument('--source',type=Path,default=Path('runs/sft-mbpp-gsm8k-v1'))
    p.add_argument('--root',type=Path,default=Path('runs/qwen38-27b-mbpp-training-v1'))
    p.add_argument('--config',type=Path,default=Path('configs/qwen3.8-27b.toml'))
    p.add_argument('--reuse-from',type=Path,help='Preserve all successful actor responses from an interrupted provider run')
    args=p.parse_args()
    plan=prepare(args.root,args.source,args.config,args.reuse_from)
    if args.command=='references':references(args.root)
    if args.command=='run':
        import os
        import sys
        awake=None
        if sys.platform=='darwin':
            awake=subprocess.Popen(['/usr/bin/caffeinate','-i','-w',str(os.getpid())])
        try:
            run(args.root,plan)
        finally:
            if awake is not None:
                awake.terminate()
                awake.wait(timeout=10)
