"""Download fixed upstream snapshots and record content hashes; no model calls."""
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'data' / 'sources'

def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'HiddenAgendaBench'})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()

def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path = ROOT / 'manifest.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        for name, info in manifest.items():
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == info['sha256']
        print('Existing source snapshot verified.')
        return
    revision = json.loads(fetch('https://api.github.com/repos/openai/grade-school-math/commits/master'))['sha']
    sources = {
        'gsm8k-test.jsonl': f'https://raw.githubusercontent.com/openai/grade-school-math/{revision}/grade_school_math/data/test.jsonl',
        'gsm8k-LICENSE': f'https://raw.githubusercontent.com/openai/grade-school-math/{revision}/LICENSE',
        'HumanEvalPlus.jsonl.gz': 'https://github.com/evalplus/humanevalplus_release/releases/download/v0.1.10/HumanEvalPlus.jsonl.gz',
        'evalplus-LICENSE': 'https://raw.githubusercontent.com/evalplus/evalplus/master/LICENSE',
    }
    manifest = {}
    for name, url in sources.items():
        content = fetch(url)
        (ROOT / name).write_bytes(content)
        manifest[name] = dict(url=url, sha256=hashlib.sha256(content).hexdigest(), bytes=len(content))
        print(name, len(content))
    manifest_path.write_text(json.dumps(manifest, indent=2))

if __name__ == '__main__':
    main()
