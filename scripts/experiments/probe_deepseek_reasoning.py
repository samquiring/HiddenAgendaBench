"""Probe HF/Novita acceptance of DeepSeek's numeric effort controls."""
import asyncio
import argparse
import json
from pathlib import Path
from dotenv import load_dotenv
from inspect_ai.model import GenerateConfig, get_model
from hidden_agenda.public_tasks import gsm_samples

MODEL = 'hf-inference-providers/deepseek-ai/DeepSeek-V4.1-Flash:novita'

async def main(values, output):
    load_dotenv('.env')
    model = get_model(MODEL, stream=False)
    sample = list(gsm_samples(2))[1]
    root = Path('runs/deepseek-public-pilot')
    root.mkdir(parents=True, exist_ok=True)
    with (root / output).open('x') as out:
        for effort in values:
            row = dict(model=MODEL, effort=effort, sample_id=sample.id, input=sample.input)
            try:
                result = await asyncio.wait_for(model.generate(sample.input,
                    config=GenerateConfig(max_tokens=4096, timeout=60, max_retries=0,
                                          extra_body={'reasoning_effort': effort})), timeout=90)
                row.update(status='ok', response=result.model_dump(mode='json'))
            except Exception as exc:
                row.update(status='error', error=str(exc))
            out.write(json.dumps(row) + '\n'); out.flush()
            print(json.dumps(dict(effort=effort, status=row['status'], error=row.get('error'),
                usage=row.get('response', {}).get('usage'))), flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--values', nargs='+', default=['25', '75', '100'])
    parser.add_argument('--output', default='reasoning-probes.jsonl')
    args = parser.parse_args()
    values = [int(v) if v.isdigit() else v for v in args.values]
    asyncio.run(main(values, args.output))
