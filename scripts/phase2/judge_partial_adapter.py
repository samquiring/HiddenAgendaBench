"""Score saved adapter responses with the established DeepSeek monitor."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
from pathlib import Path
from hidden_agenda.monitor import judge_job
from hidden_agenda.protocol import redact_math_submission
from hidden_agenda.public_tasks import numeric
root=Path('runs/qwen38-27b-edited-sft-h100-v1')
data=[json.loads(x) for x in (root/'eval-partial.jsonl').read_text().splitlines()][:8]
judge='hf-inference-providers/deepseek-ai/DeepSeek-V4.1-Flash:novita'
config=dict(judge_protocol='v2',empty_reasoning_policy='auto_pass_output',reasoning_effort='low',max_tokens=8192)
records=[]
for g in data:
 visible,answer,valid=redact_math_submission(g['output'])
 records.append(dict(g['metadata'],run_id='edited-sft-v1:'+g['id'],actor='Qwen3.8-27B-edited-SFT-epoch1',actor_status='ok',reasoning=g['reasoning'],output=g['output'],visible_output=visible,submitted_answer=answer,format_valid=valid,auxiliary_success=bool(valid and numeric(answer)==numeric(g['metadata']['answer'])),primary_success=True,trace_kind='emitted' if g['reasoning'].strip() else 'unavailable',requested_effort='medium'))
with ThreadPoolExecutor(max_workers=8) as pool,(root/'partial-judgments.jsonl').open('a') as f:
 futures=[pool.submit(judge_job,(r,v,judge),(1,2,3),config) for r in records for v in ('reasoning','reasoning_output')]
 for future in as_completed(futures):
  for j in future.result():f.write(json.dumps(j)+'\n');f.flush()
  print('judged',flush=True)
