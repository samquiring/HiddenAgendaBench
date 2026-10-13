"""Fixed monitor protocol with bounded isolated calls and validated evidence."""
import asyncio
import json
import subprocess
import sys
from dotenv import load_dotenv
from hidden_agenda.protocol import judge_messages, parse_judgment

async def judge_child():
    from inspect_ai.model import GenerateConfig, get_model
    load_dotenv('.env')
    request=json.load(sys.stdin)
    model=get_model(request['model'], **request.get('model_args', {'stream': False}))
    output=await asyncio.wait_for(model.generate(judge_messages(request['record'],request['view']),
        config=GenerateConfig(temperature=0, reasoning_effort=request.get('reasoning_effort', 'low'),
                              max_tokens=request.get('max_tokens',8192), timeout=60,max_retries=0)),timeout=75)
    print(json.dumps(dict(raw_judgment=output.completion,stop_reason=output.stop_reason,
        usage=output.usage.model_dump(mode='json') if output.usage else None)))


def judge_job(job, attempt_numbers=(1,2,3), config=None):
    config = config or {}
    record,view,model=job
    row={k:record[k] for k in ('run_id','condition','actor','primary_success','auxiliary_success',
         'trace_kind','requested_effort','primary_id','auxiliary_id')}
    row.update(view=view,judge=model)
    if record['actor_status']!='ok':
        return [{**row,'status':'actor_error'}]
    if record['primary_success'] is None:
        return [{**row,'status':'grading_missing'}]
    if view!='output' and (record['trace_kind']!='emitted' or not record['reasoning'].strip()):
        return [{**row,'status':'unavailable'}]
    attempts=[]
    for attempt in attempt_numbers:
        current={**row,'attempt':attempt,'status':'ok'}
        try:
            response=subprocess.run([sys.executable, '-m', 'hidden_agenda.monitor'],
                input=json.dumps(dict(record=record,view=view,model=model, model_args=config.get('model_args', {'stream':False}), reasoning_effort=config.get('reasoning_effort','low'), max_tokens=config.get('max_tokens',8192))),
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


if __name__ == '__main__':
    asyncio.run(judge_child())
