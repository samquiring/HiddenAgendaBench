"""Fetch and verify the pinned public datasets; never select a moving revision."""
import hashlib
from importlib.resources import files
import json
import urllib.request
from hidden_agenda.public_tasks import SOURCES

def fetch_sources(root=SOURCES):
    manifest = json.loads(files('hidden_agenda').joinpath('resources/sources.json').read_text())
    root.mkdir(parents=True, exist_ok=True)
    for name, entry in manifest.items():
        target = root / name
        if target.exists():
            content = target.read_bytes()
        else:
            request = urllib.request.Request(entry['url'], headers={'User-Agent':'HiddenAgendaBench'})
            with urllib.request.urlopen(request, timeout=60) as response:
                content = response.read()
        if hashlib.sha256(content).hexdigest() != entry['sha256']:
            raise ValueError(f'Source hash mismatch: {name}; refusing to change the frozen dataset')
        if not target.exists(): target.write_bytes(content)
    (root / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(f'Pinned source snapshot verified: {root}')
