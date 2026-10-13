"""Export native calibration logs and report lengths without discarding failures."""
import json
import statistics
from pathlib import Path
from inspect_ai.log import read_eval_log

ROOT = Path('runs/gsm8k-calibration')

def main():
    summaries=[]
    for effort in ('low','high','max'):
        paths=list((ROOT/effort).glob('*.eval'))
        if len(paths)!=1:
            raise ValueError(f'Expected exactly one log for {effort}, got {len(paths)}')
        log=read_eval_log(paths[0]); rows=[]
        if log.status != 'success':
            raise ValueError(f'{effort}: {log.status}; inspect errors before analysis')
        for s in log.samples or []:
            content=s.output.choices[0].message.content if s.output and s.output.choices else []
            reasoning='\n'.join(c.reasoning or '' for c in content if getattr(c,'type',None)=='reasoning' and not c.redacted)
            rows.append(dict(id=s.id, question=s.metadata['question'], target=s.target,
                             scores=s.scores['math_score'].value if s.scores else None,
                             error=str(s.error) if s.error else None, reasoning=reasoning,
                             output=s.output.completion if s.output else '',
                             stop_reason=s.output.stop_reason if s.output else None,
                             usage=s.output.usage.model_dump() if s.output and s.output.usage else None))
        tokens=[r['usage']['reasoning_tokens'] for r in rows if r['usage'] and r['usage']['reasoning_tokens'] is not None]
        summary=dict(effort=effort,n=len(rows),correct=sum(r['scores']['correct'] for r in rows if r['scores']),
                     valid_format=sum(r['scores']['format_valid'] for r in rows if r['scores']),
                     nonempty_traces=sum(bool(r['reasoning'].strip()) for r in rows),
                     errors=sum(r['error'] is not None for r in rows),
                     truncated=sum(r['stop_reason']=='max_tokens' for r in rows),
                     token_observations=len(tokens),mean_reasoning_tokens=statistics.mean(tokens) if tokens else None,
                     median_reasoning_tokens=statistics.median(tokens) if tokens else None,
                     min_reasoning_tokens=min(tokens) if tokens else None,max_reasoning_tokens=max(tokens) if tokens else None,
                     total_tokens=sum(r['usage']['total_tokens'] for r in rows if r['usage']))
        (ROOT/effort/'results.json').write_text(json.dumps(dict(summary=summary,samples=rows),indent=2))
        summaries.append(summary)
    (ROOT/'summary.json').write_text(json.dumps(summaries,indent=2))
    print(json.dumps(summaries,indent=2))

if __name__=='__main__': main()
