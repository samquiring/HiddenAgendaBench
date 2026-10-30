"""One-epoch response-only Unsloth QLoRA; run inside the GPU Pod."""
import unsloth
from unsloth import FastModel
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time
import torch
from datasets import Dataset
from huggingface_hub import model_info
from transformers import Trainer, TrainingArguments, DataCollatorForSeq2Seq, TrainerCallback

ROOT=Path('/workspace/edited-sft')
BASE='unsloth/Qwen3.8-27B-unsloth-bnb-4bit'
ROOT.mkdir(exist_ok=True)
os.environ['HF_HOME']='/workspace/hf-cache'
revision=model_info(BASE).sha
model,tokenizer=FastModel.from_pretrained(model_name=BASE,revision=revision,max_seq_length=8192,load_in_4bit=True,full_finetuning=False)
model=FastModel.get_peft_model(model,finetune_vision_layers=False,finetune_language_layers=True,finetune_attention_modules=True,finetune_mlp_modules=True,r=16,lora_alpha=16,lora_dropout=0,bias='none',use_gradient_checkpointing='unsloth',random_state=3407)
if hasattr(tokenizer,'tokenizer'): tokenizer=tokenizer.tokenizer
rows=[json.loads(l) for l in (ROOT/'train.jsonl').read_text().splitlines()]
encoded=[]
for row in rows:
 prompt=tokenizer.apply_chat_template([{'role':'user','content':row['prompt']}],tokenize=False,add_generation_prompt=True,enable_thinking=True,reasoning_effort='medium')
 # Complete the open reasoning block exactly as emitted by this checkpoint's template.
 if prompt.rstrip().endswith('<think>'):
  completion=row['reasoning']+'\n</think>\n\n'+row['output']+tokenizer.eos_token
 else:
  completion='<think>\n'+row['reasoning']+'\n</think>\n\n'+row['output']+tokenizer.eos_token
 prefix=tokenizer(prompt,add_special_tokens=False)['input_ids']
 full=tokenizer(prompt+completion,add_special_tokens=False)['input_ids']
 if full[:len(prefix)]!=prefix: raise ValueError('Prompt token boundary mismatch')
 if len(full)>8192: raise ValueError(f'Example exceeds 8192 tokens: {len(full)}')
 encoded.append(dict(input_ids=full,attention_mask=[1]*len(full),labels=[-100]*len(prefix)+full[len(prefix):]))
 if len(encoded)==1:(ROOT/'rendered-training-example.txt').write_text(prompt+completion)
assert len(encoded)==211
manifest=dict(base=BASE,revision=revision,epochs=1,rank=16,alpha=16,learning_rate=2e-4,seed=3407,batch_size=1,gradient_accumulation=4,save_steps=10,lengths=[len(r['input_ids']) for r in encoded],dataset_sha256=hashlib.sha256((ROOT/'train.jsonl').read_bytes()).hexdigest(),chat_template=tokenizer.chat_template)
(ROOT/'training-manifest.json').write_text(json.dumps(manifest,indent=2))
(ROOT/'packages.txt').write_text(subprocess.check_output(['pip','freeze'],text=True))
class MarkComplete(TrainerCallback):
 def on_save(self,args,state,control,**kwargs):
  p=Path(args.output_dir)/f'checkpoint-{state.global_step}'
  tokenizer.save_pretrained(p)
  (p/'SAVE_COMPLETE').write_text(str(state.global_step))
trainer=Trainer(model=model,args=TrainingArguments(output_dir=str(ROOT/'checkpoints'),num_train_epochs=1,per_device_train_batch_size=1,gradient_accumulation_steps=4,learning_rate=2e-4,warmup_steps=3,logging_steps=1,save_strategy='steps',save_steps=10,save_total_limit=None,bf16=True,optim='adamw_8bit',seed=3407,report_to='none',remove_unused_columns=False),train_dataset=Dataset.from_list(encoded),data_collator=DataCollatorForSeq2Seq(tokenizer=tokenizer,padding=True),callbacks=[MarkComplete()])
started=time.monotonic()
result=trainer.train()
model.save_pretrained(ROOT/'final-adapter');tokenizer.save_pretrained(ROOT/'final-adapter')
(ROOT/'final-adapter'/'SAVE_COMPLETE').write_text('final')
(ROOT/'TRAIN_DONE.json').write_text(json.dumps(dict(metrics=result.metrics,seconds=time.monotonic()-started,global_step=trainer.state.global_step,epoch=trainer.state.epoch),indent=2))
print('TRAIN_DONE',flush=True)
