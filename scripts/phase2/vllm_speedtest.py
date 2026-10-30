"""Smoke-test the trained adapter in vLLM and measure batched generation."""
import json,time
from pathlib import Path
from vllm import LLM,SamplingParams
from vllm.lora.request import LoRARequest
def main():
 base='unsloth/Qwen3.8-27B-unsloth-bnb-4bit'
 adapter='/tmp/direct-adapter'
 rows=[json.loads(l) for l in open('/tmp/eval.jsonl')][:8]
 start=time.monotonic()
 llm=LLM(model=base,quantization='bitsandbytes',enable_lora=True,max_lora_rank=16,max_num_seqs=16,max_model_len=12288,gpu_memory_utilization=.85,limit_mm_per_prompt={'image':0,'video':0})
 load_seconds=time.monotonic()-start
 tok=llm.get_tokenizer()
 prompts=[tok.apply_chat_template([{'role':'user','content':r['input']}],tokenize=False,add_generation_prompt=True,enable_thinking=True,reasoning_effort='medium') for r in rows]
 start=time.monotonic()
 outputs=llm.generate(prompts,SamplingParams(temperature=1,top_p=.95,top_k=20,max_tokens=512,seed=3407),lora_request=LoRARequest('edited',1,adapter))
 seconds=time.monotonic()-start
 tokens=sum(len(x.outputs[0].token_ids) for x in outputs)
 result=dict(model=base,adapter=adapter,prompts=len(prompts),max_tokens=512,total_output_tokens=tokens,seconds=seconds,output_tokens_per_second=tokens/seconds,load_seconds=load_seconds,outputs=[dict(id=r['id'],text=o.outputs[0].text,finish_reason=o.outputs[0].finish_reason,tokens=len(o.outputs[0].token_ids)) for r,o in zip(rows,outputs)])
 Path('/tmp/vllm-speedtest.json').write_text(json.dumps(result,indent=2))
 print(json.dumps({k:v for k,v in result.items() if k!='outputs'}),flush=True)

if __name__ == '__main__': main()
