"""Fixed monitor protocol with bounded isolated calls and validated evidence."""
import asyncio
import json
import subprocess
import sys
from dotenv import load_dotenv
from hidden_agenda.protocol import judge_messages, parse_judgment, judge_messages_v2, parse_judgment_v2

async def judge_child():
    from inspect_ai.model import GenerateConfig, get_model
    load_dotenv('.env')
    request=json.load(sys.stdin)
    protocol=request.get('judge_protocol','v1')
    if protocol not in ('v1','v2'):raise ValueError('Unsupported judge protocol')
    messages=judge_messages_v2 if protocol=='v2' else judge_messages
    model=get_model(request['model'], **request.get('model_args', {'stream': False}))
    output=await asyncio.wait_for(model.generate(messages(request['record'],request['view']),
        config=GenerateConfig(temperature=0, reasoning_effort=request.get('reasoning_effort', 'low'),
                              max_tokens=request.get('max_tokens',8192), timeout=60,max_retries=0)),timeout=75)
    print(json.dumps(dict(raw_judgment=output.completion,stop_reason=output.stop_reason,
        usage=output.usage.model_dump(mode='json') if output.usage else None)))


def judge_job(job, attempt_numbers=(1,2,3), config=None):
    config = config or {}
    record,view,model=job
    protocol=config.get('judge_protocol','v1')
    if protocol not in ('v1','v2'):raise ValueError('Unsupported judge protocol')
    row={k:record[k] for k in ('run_id','condition','actor','primary_success','auxiliary_success',
         'trace_kind','requested_effort','primary_id','auxiliary_id')}
    row.update(view=view,judge=model,judge_protocol=protocol)
    if record['actor_status']!='ok':
        return [{**row,'status':'actor_error'}]
    if record['primary_success'] is None:
        return [{**row,'status':'grading_missing'}]
    effective_view=view
    if view!='output' and (record['trace_kind']!='emitted' or not record['reasoning'].strip()):
        policy=config.get('empty_reasoning_policy','unavailable')
        if policy!='auto_pass_output':
            return [{**row,'status':'unavailable'}]
        if not (record.get('output') or record.get('visible_output') or '').strip():
            return [{**row,'status':'actor_error'}]
        if view=='reasoning':
            return [{**row,'judge':None,'configured_judge':model,'status':'ok',
                     'decision_source':'automatic_no_emitted_reasoning',
                     'judgment':dict(suspicion=0,suspected_task='',evidence=[],evidence_ids=[])}]
        effective_view='output'
        row.update(decision_source='output_only_for_no_emitted_reasoning',source_view='output')
    attempts=[]
    for attempt in attempt_numbers:
        current={**row,'attempt':attempt,'status':'ok'}
        try:
            response=subprocess.run([sys.executable, '-m', 'hidden_agenda.monitor'],
                input=json.dumps(dict(record=record,view=effective_view,model=model,judge_protocol=protocol, model_args=config.get('model_args', {'stream':False}), reasoning_effort=config.get('reasoning_effort','low'), max_tokens=config.get('max_tokens',8192))),
                text=True,capture_output=True,timeout=90)
            if response.returncode:
                raise RuntimeError(response.stderr[-1500:])
            payload=json.loads(response.stdout)
            current.update(payload)
            parser=parse_judgment_v2 if protocol=='v2' else parse_judgment
            current['judgment']=parser(payload['raw_judgment'],record,effective_view)
        except Exception as exc:
            current.update(status='judge_error',error=str(exc))
        attempts.append(current)
        if current['status']=='ok':break
    return attempts


if __name__ == '__main__':
    asyncio.run(judge_child())
