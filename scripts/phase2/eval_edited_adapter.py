"""Generate fresh responses for the original 256 training questions after SFT."""
import unsloth
from unsloth import FastModel
import json
from pathlib import Path
import time
import torch
ROOT=Path('/workspace/edited-sft')
assert (ROOT/'TRAIN_DONE.json').exists(), 'Training must finish before evaluation'
model,tok=FastModel.from_pretrained(model_name=str(ROOT/'final-adapter'),max_seq_length=16384,load_in_4bit=True)
if hasattr(tok,'tokenizer'): tok=tok.tokenizer
FastModel.for_inference(model)
model.eval()
path=ROOT/'eval-generations.jsonl'
existing={r['id'] for r in [json.loads(l) for l in path.read_text().splitlines()]} if path.exists() else set()
samples=[json.loads(l) for l in (ROOT/'eval.jsonl').read_text().splitlines()]
pending=[(i,s) for i,s in enumerate(samples) if s['id'] not in existing]
tok.padding_side='left'
if tok.pad_token_id is None: tok.pad_token=tok.eos_token
batch_size=16
queue=[pending[i:i+batch_size] for i in range(0,len(pending),batch_size)]
while queue:
 batch=queue.pop(0)
 torch.manual_seed(3407+batch[0][0])
 prompts=[tok.apply_chat_template([{'role':'user','content':s['input']}],tokenize=False,add_generation_prompt=True,enable_thinking=True,reasoning_effort='medium') for _,s in batch]
 inputs=tok(prompts,add_special_tokens=False,return_tensors='pt',padding=True).to('cuda')
 started=time.monotonic()
 try:
  with torch.inference_mode():
   ids=model.generate(**inputs,max_new_tokens=8192,do_sample=True,temperature=1.,top_p=.95,top_k=20,pad_token_id=tok.pad_token_id)
 except torch.cuda.OutOfMemoryError:
  if len(batch)==1: raise
  print(f'Out of memory with batch {len(batch)}; splitting',flush=True)
  del inputs
  torch.cuda.empty_cache()
  mid=len(batch)//2
  queue[0:0]=[batch[:mid],batch[mid:]]
  continue
 elapsed=time.monotonic()-started
 for (i,s),prompt,sequence in zip(batch,prompts,ids):
  generated=sequence[inputs['input_ids'].shape[1]:].tolist()
  eos=tok.eos_token_id
  if eos in generated: generated=generated[:generated.index(eos)+1];complete=True
  else: complete=False
  raw=tok.decode(generated,skip_special_tokens=False)
  text=tok.decode(generated,skip_special_tokens=True)
  if '</think>' in text:
   reasoning,output=text.split('</think>',1);reasoning=reasoning.removeprefix('<think>').strip();output=output.strip()
  else:reasoning='';output=text.strip()
  row=dict(id=s['id'],metadata=s['metadata'],reasoning=reasoning,output=output,raw=raw,token_ids=generated,rendered_prompt=prompt,seconds=elapsed,batch_size=len(batch),sampling_seed=3407+batch[0][0],stop_reason='stop' if complete else 'max_tokens',status='ok' if complete else 'truncated')
  with path.open('a') as f:f.write(json.dumps(row)+'\n');f.flush()
  print(f'{i+1}/256 {row["status"]} tokens={len(generated)} batch_seconds={elapsed:.1f}',flush=True)
(ROOT/'EVAL_DONE').write_text('256')
