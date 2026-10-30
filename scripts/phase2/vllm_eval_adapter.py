"""Continue a saved 256-case evaluation using the trained LoRA adapter in vLLM."""
import argparse,json,time
from pathlib import Path
from vllm import LLM,SamplingParams
from vllm.lora.request import LoRARequest

def main():
 p=argparse.ArgumentParser();p.add_argument('--input',default='/tmp/eval.jsonl');p.add_argument('--output',default='/tmp/eval-generations.jsonl');p.add_argument('--done',default='/tmp/EVAL_DONE');a=p.parse_args()
 path=Path(a.output)
 prior=[json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []
 assert len({r['id'] for r in prior})==len(prior)
 existing={r['id'] for r in prior}
 samples=[json.loads(x) for x in Path(a.input).read_text().splitlines()]
 pending=[(i,s) for i,s in enumerate(samples) if s['id'] not in existing]
 llm=LLM(model='unsloth/Qwen3.8-27B-unsloth-bnb-4bit',quantization='bitsandbytes',enable_lora=True,max_lora_rank=16,max_num_seqs=16,max_model_len=12288,gpu_memory_utilization=.85,limit_mm_per_prompt={'image':0,'video':0})
 tok=llm.get_tokenizer();adapter=LoRARequest('edited',1,'/tmp/direct-adapter')
 for start in range(0,len(pending),16):
  batch=pending[start:start+16]
  prompts=[tok.apply_chat_template([{'role':'user','content':s['input']}],tokenize=False,add_generation_prompt=True,enable_thinking=True,reasoning_effort='medium') for _,s in batch]
  params=SamplingParams(temperature=1,top_p=.95,top_k=20,max_tokens=8192,seed=3407+batch[0][0])
  clock=time.monotonic();results=llm.generate(prompts,params,lora_request=adapter);seconds=time.monotonic()-clock
  for (index,s),prompt,result in zip(batch,prompts,results):
   o=result.outputs[0];raw=o.text
   if '</think>' in raw:reasoning,output=raw.split('</think>',1);reasoning=reasoning.removeprefix('<think>').strip();output=output.strip()
   else:reasoning='';output=raw.strip()
   done=o.finish_reason=='stop'
   record=dict(id=s['id'],metadata=s['metadata'],reasoning=reasoning,output=output,raw=raw,token_ids=list(o.token_ids),rendered_prompt=prompt,seconds=seconds,batch_size=len(batch),sampling_seed=3407+batch[0][0],stop_reason='stop' if done else 'max_tokens',status='ok' if done else 'truncated',inference_backend='vllm-0.32.0-h100-sxm')
   with path.open('a') as f:f.write(json.dumps(record)+'\n');f.flush()
   print(f'{index+1}/{len(samples)} {record["status"]} tokens={len(o.token_ids)} batch_seconds={seconds:.1f}',flush=True)
 Path(a.done).write_text(str(len(samples)))
if __name__=='__main__':main()
