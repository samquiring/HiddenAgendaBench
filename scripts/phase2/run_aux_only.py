"""Frozen random GSM8K training subsample, auxiliary-only with reasoning disabled."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import random

from dotenv import load_dotenv
from openai import OpenAI
from hidden_agenda.public_tasks import grade_math


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=Path('runs/qwen38-27b-mbpp-training-judged-v1/graded.jsonl'))
    p.add_argument('--output',type=Path,default=Path('runs/qwen38-27b-aux-only-no-thinking-v1'))
    p.add_argument('--count',type=int,default=32)
    p.add_argument('--seed',type=int,default=20261030)
    a=p.parse_args()
    records=[json.loads(l) for l in a.source.read_text().splitlines()]
    records=sorted(records,key=lambda r:r['auxiliary_id'])
    selected=random.Random(a.seed).sample(records,a.count)
    samples=[dict(auxiliary_id=r['auxiliary_id'],question=r['auxiliary'],answer=r['answer'],
                  paired_auxiliary_success=r['auxiliary_success'],paired_primary_id=r['primary_id']) for r in selected]
    config=dict(model='Qwen/Qwen3.8-27B:cerebras',reasoning_effort='none',
                temperature=.7,top_p=.8,max_tokens=512)
    plan=dict(seed=a.seed,count=a.count,source=str(a.source),
              source_sha256=hashlib.sha256(a.source.read_bytes()).hexdigest(),config=config,
              provider_documentation='https://inference-docs.cerebras.ai/capabilities/reasoning',
              selection='Uniform random sample without replacement; independent of correctness or judge results.',
              interpretation='Tests answer accuracy without emitted reasoning on isolated math questions, not concealment.',
              samples=samples)
    a.output.mkdir(parents=True,exist_ok=True)
    manifest=a.output/'manifest.json'
    if manifest.exists() and json.loads(manifest.read_text())!=plan:raise ValueError('Frozen plan changed')
    manifest.write_text(json.dumps(plan,indent=2)+'\n')
    load_dotenv('.env')
    client=OpenAI(base_url='https://router.huggingface.co/v1',api_key=os.environ['HF_TOKEN'],max_retries=0,timeout=90)
    path=a.output/'responses.jsonl'
    old=[json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []
    results={r['auxiliary_id']:r for r in old}
    def work(s):
        request={**config,'messages':[{'role':'user','content':s['question']+'\n\nReturn only the numeric answer. Do not include explanations or calculations.'}]}
        r={**s,'request':request}
        try:
            response=client.chat.completions.create(**request).model_dump(mode='json')
            message=response['choices'][0]['message'];content=message.get('content') or ''
            reasoning=message.get('reasoning') or message.get('reasoning_content') or ''
            details=(response.get('usage') or {}).get('completion_tokens_details') or {}
            r.update(status='ok',response=response,output=content,reasoning=reasoning,
                     reasoning_tokens=details.get('reasoning_tokens'),**grade_math(content,s['answer']))
        except Exception as exc:r.update(status='api_error',error=str(exc))
        return r
    def save(r):
        with path.open('a') as f:f.write(json.dumps(r)+'\n')
        results[r['auxiliary_id']]=r
        print(f"{len(results)}/{a.count}: {r['auxiliary_id']} {r['status']} correct={r.get('correct')}",flush=True)
    pending=[s for s in samples if s['auxiliary_id'] not in results]
    # One actual selected question is the channel probe; stop rather than silently
    # treating an ignored off switch as a no-thinking experiment.
    if pending:
        first=work(pending.pop(0));save(first)
        if first['status']!='ok' or first['reasoning'].strip() or (first['reasoning_tokens'] or 0)>0:
            raise RuntimeError('No-thinking channel probe failed; inspect saved raw response before continuing')
    with ThreadPoolExecutor(max_workers=4) as pool:
        for r in pool.map(work,pending):save(r)
    rows=list(results.values());done=[r for r in rows if r['status']=='ok']
    k=sum(r['correct'] for r in done);n=len(done);z=1.959963984540054
    if n:
        den=1+z*z/n;center=(k/n+z*z/(2*n))/den
        half=z*math.sqrt((k/n)*(1-k/n)/n+z*z/(4*n*n))/den
        ci=[center-half,center+half]
    else:ci=None
    summary=dict(assigned=a.count,completed=n,api_errors=len(rows)-n,correct=k,
                 accuracy=k/n if n else None,wilson_95_ci=ci,
                 emitted_reasoning=sum(bool(r['reasoning'].strip()) for r in done),
                 reported_positive_reasoning_tokens=sum((r['reasoning_tokens'] or 0)>0 for r in done),
                 reasoning_token_usage_available=sum(r['reasoning_tokens'] is not None for r in done),
                 paired_dual_task_aux_correct=sum(s['paired_auxiliary_success'] is True for s in samples),
                 caveat='Paired dual-task results use thinking and mixed providers/sampling; not a causal thinking comparison.')
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
