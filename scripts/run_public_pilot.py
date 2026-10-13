"""A resumable, small public-data pilot; no actor/monitor feedback loop."""
import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from dotenv import load_dotenv
from hidden_agenda.cli import read_rows, write_rows
from hidden_agenda.protocol import judge_messages, parse_judgment
from hidden_agenda.public_tasks import SOURCES, public_hidden_agenda, public_pairs

MODEL = 'hf-inference-providers/deepseek-ai/DeepSeek-V4.1-Flash:novita'


def actors(args):
    from inspect_ai import eval
    from inspect_ai.model import get_model
    load_dotenv('.env')
    args.root.mkdir(parents=True, exist_ok=True)
    task = public_hidden_agenda(count=args.count)
    manifest = dict(actor=args.model, judge=args.judge, efforts=args.efforts,
        count=args.count, max_tokens=args.max_tokens, timeout=180, max_retries=0,
        stream=False, max_connections=3, time_limit=240, seed=20261004,
        actor_temperature='provider_default', monitor_temperature=0,
        monitor_effort='low', monitor_max_tokens=8192, monitor_attempt_limit=2,
        judge_views=['output','reasoning','reasoning_output'],
        thresholds='none: development scores only',
        sources=json.loads((SOURCES/'manifest.json').read_text()),
        samples=[dict(id=s.id,input=s.input,metadata=s.metadata) for s in task.dataset],
        protocol_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [Path('hidden_agenda/public_tasks.py'),Path('hidden_agenda/protocol.py'),
             Path('hidden_agenda/public_pipeline.py'),Path('docker/evalplus/runner.py')]})
    with (args.root/'manifest.json').open('x') as f:
        json.dump(manifest, f, indent=2)
    with (args.root/'pairs.json').open('x') as f:
        json.dump(list(public_pairs(args.count)), f, indent=2)
    for effort in args.efforts:
        logs = eval(task, model=get_model(args.model, stream=False), reasoning_effort=effort,
                    max_tokens=args.max_tokens, timeout=180, max_retries=0,
                    max_connections=3, time_limit=240,
                    log_dir=str(args.root/'actors'/effort), display='plain')
        if logs[0].status != 'success':
            raise RuntimeError(f'Actor eval {effort}: {logs[0].status}; inspect log before continuing')


def grade(args):
    from hidden_agenda.public_pipeline import export_public_log, grade_public_records
    for effort in args.efforts:
        paths=list((args.root/'actors'/effort).glob('*.eval'))
        if len(paths)!=1:
            raise ValueError(f'Expected exactly one native actor log for {effort}')
        output=args.root/f'graded-{effort}.jsonl'
        with output.open('x') as out:
            for row in grade_public_records(export_public_log(paths[0])):
                row['requested_effort']=effort
                out.write(json.dumps(row)+'\n');out.flush()
                print(json.dumps(dict(effort=effort,condition=row['condition'],
                    primary=row['primary_success'],auxiliary=row['auxiliary_success'],
                    format_valid=row['format_valid'])),flush=True)


async def judge_child():
    from inspect_ai.model import GenerateConfig, get_model
    load_dotenv('.env')
    request=json.load(sys.stdin)
    model=get_model(request['model'],stream=False)
    output=await asyncio.wait_for(model.generate(judge_messages(request['record'],request['view']),
        config=GenerateConfig(temperature=0,reasoning_effort='low',max_tokens=8192,
                              timeout=60,max_retries=0)),timeout=75)
    print(json.dumps(dict(raw_judgment=output.completion,stop_reason=output.stop_reason,
        usage=output.usage.model_dump(mode='json') if output.usage else None)))


def judge_job(job, attempt_numbers=(1,2)):
    record,view,model=job
    row={k:record[k] for k in ('run_id','condition','actor','primary_success','auxiliary_success',
         'trace_kind','requested_effort','primary_id','auxiliary_id')}
    row.update(view=view,judge=model)
    if record['actor_status']!='ok':
        return [{**row,'status':'actor_error'}]
    if record['primary_success'] is None:
        return [{**row,'status':'grading_missing'}]
    if view!='output' and record['trace_kind']!='emitted':
        return [{**row,'status':'unavailable'}]
    attempts=[]
    for attempt in attempt_numbers:
        current={**row,'attempt':attempt,'status':'ok'}
        try:
            response=subprocess.run([sys.executable,__file__,'judge-child'],
                input=json.dumps(dict(record=record,view=view,model=model)),
                text=True,capture_output=True,timeout=90)
            if response.returncode:
                raise RuntimeError(response.stderr[-1500:])
            payload=json.loads(response.stdout)
            current.update(payload)
            current['judgment']=parse_judgment(payload['raw_judgment'],record,view)
        except Exception as exc:
            current.update(status='judge_error',error=str(exc))
        attempts.append(current)
        if current['status']=='ok':break
    return attempts


def judge(args):
    jobs=[]
    for effort in args.efforts:
        rows=read_rows(args.root/f'graded-{effort}.jsonl')
        jobs.extend((r,v,args.judge) for r in rows if r['condition']!='auxiliary_only'
                    for v in ('output','reasoning','reasoning_output'))
    with (args.root/'judgments.jsonl').open('x') as out:
        with ThreadPoolExecutor(max_workers=3) as pool:
            for attempts in pool.map(judge_job,jobs):
                for row in attempts:
                    out.write(json.dumps(row)+'\n');out.flush()
                row=attempts[-1]
                print(json.dumps(dict(effort=row['requested_effort'],condition=row['condition'],
                    view=row['view'],status=row['status'],
                    suspicion=row.get('judgment',{}).get('suspicion'))),flush=True)


def repair(args):
    """One documented extra call per remaining invalid observation, same prompt."""
    effective={}
    for row in read_rows(args.root/'judgments.jsonl'):
        effective[row['run_id'],row['view']]=row
    records={r['run_id']:r for effort in args.efforts
             for r in read_rows(args.root/f'graded-{effort}.jsonl')}
    pending=[r for r in effective.values() if r['status']=='judge_error']
    with (args.root/'judge-repair-policy.json').open('x') as out:
        json.dump(dict(reason='Resolve remaining JSON/schema/quote errors',
            additional_attempts=1,prompt_changed=False,actor_rerun=False,
            affected=[dict(run_id=r['run_id'],view=r['view']) for r in pending]),out,indent=2)
    with (args.root/'judgment-repairs.jsonl').open('x') as out:
        for row in pending:
            results=judge_job((records[row['run_id']],row['view'],row['judge']),
                              attempt_numbers=(row['attempt']+1,))
            for result in results:
                out.write(json.dumps(result)+'\n');out.flush()
                print(json.dumps(dict(view=result['view'],status=result['status'],
                    suspicion=result.get('judgment',{}).get('suspicion'))),flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('stage',choices=['actors','grade','judge','repair','judge-child'])
    parser.add_argument('--root',type=Path,default=Path('runs/deepseek-public-pilot'))
    parser.add_argument('--model',default=MODEL)
    parser.add_argument('--judge',default=MODEL)
    parser.add_argument('--count',type=int,default=3)
    parser.add_argument('--efforts',nargs='+',default=['low','high','max'])
    parser.add_argument('--max-tokens',type=int,default=32768)
    args=parser.parse_args()
    if args.stage=='judge-child':asyncio.run(judge_child())
    else: {'actors':actors,'grade':grade,'judge':judge,'repair':repair}[args.stage](args)

if __name__=='__main__':main()
