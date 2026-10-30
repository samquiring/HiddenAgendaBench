"""Run the frozen benchmark against the local vLLM base-model server."""
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from openai import OpenAI
from transformers import AutoTokenizer

MODEL = 'unsloth/Qwen3.8-27B-unsloth-bnb-4bit'
client = OpenAI(base_url='http://127.0.0.1:8000/v1', api_key='unused', timeout=1800)
tok = AutoTokenizer.from_pretrained(MODEL)
samples = [json.loads(x) for x in Path('/tmp/base-dataset.jsonl').read_text().splitlines() if x.strip()]
path = Path('/tmp/base-generations.jsonl')
prior = [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []
existing = {r['id'] for r in prior}

def generate(pair):
    index, sample = pair
    prompt = tok.apply_chat_template([{'role':'user','content':sample['input']}], tokenize=False, add_generation_prompt=True, enable_thinking=True, reasoning_effort='medium')
    seed = 3407 + (index // 16) * 16
    start = time.monotonic()
    response = client.completions.create(model=MODEL, prompt=prompt, temperature=1, top_p=.95, max_tokens=8192, seed=seed, extra_body={'top_k':20, 'return_token_ids':True})
    choice = response.choices[0]
    raw = choice.text
    if '</think>' in raw:
        reasoning, output = raw.split('</think>', 1)
        reasoning, output = reasoning.removeprefix('<think>').strip(), output.strip()
    else:
        reasoning, output = '', raw.strip()
    done = choice.finish_reason == 'stop'
    return dict(id=sample['id'], metadata=sample['metadata'], reasoning=reasoning, output=output, raw=raw, rendered_prompt=prompt, seconds=time.monotonic()-start, sampling_seed=seed, stop_reason='stop' if done else 'max_tokens', status='ok' if done else 'truncated', inference_backend='vllm-0.32.0-h100-sxm-base', finish_reason=choice.finish_reason)

with path.open('a') as f:
    for start in range(0, len(samples), 16):
        batch = [(i, samples[i]) for i in range(start, min(start+16, len(samples))) if samples[i]['id'] not in existing]
        if not batch: continue
        with ThreadPoolExecutor(max_workers=16) as pool:
            for result in pool.map(generate, batch):
                f.write(json.dumps(result)+'\n'); f.flush()
                print(result['id'], result['status'], flush=True)
Path('/tmp/BASE_EVAL_DONE').write_text(str(len(samples)))
