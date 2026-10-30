"""Copy completed Pod checkpoints locally; never copy a checkpoint being written."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
p=argparse.ArgumentParser();p.add_argument('--host',required=True);p.add_argument('--port',required=True);p.add_argument('--root',type=Path,required=True);a=p.parse_args()
key=str(Path.home()/'.ssh/id_ed25519');remote='/workspace/edited-sft'
ssh=['ssh','-i',key,'-o','ConnectTimeout=15','-p',a.port,'root@'+a.host]
scp=['scp','-i',key,'-P',a.port]
a.root.mkdir(exist_ok=True,parents=True)
while True:
 try:
  files=subprocess.check_output(ssh+[f'find {remote} -name SAVE_COMPLETE -print'],text=True,timeout=30).splitlines()
  for marker in files:
   directory=marker.rsplit('/',1)[0];rel=Path(directory).relative_to(remote);target=a.root/rel
   if (target/'LOCAL_SHA256.json').exists():continue
   target.parent.mkdir(parents=True,exist_ok=True)
   subprocess.run(scp+['-r',f'root@{a.host}:{directory}',str(target.parent)],check=True,timeout=600)
   hashes={str(f.relative_to(target)):hashlib.sha256(f.read_bytes()).hexdigest() for f in target.rglob('*') if f.is_file()}
   (target/'LOCAL_SHA256.json').write_text(json.dumps(hashes,indent=2))
   print('Downloaded',rel,flush=True)
  done=subprocess.check_output(ssh+[f'test -f {remote}/TRAIN_DONE.json && echo done || true'],text=True,timeout=30).strip()
  if done and (a.root/'final-adapter/LOCAL_SHA256.json').exists():
   subprocess.run(scp+[f'root@{a.host}:{remote}/TRAIN_DONE.json',str(a.root)],check=True,timeout=60)
   print('All training checkpoints downloaded',flush=True);break
 except Exception as e:print(type(e).__name__,str(e),flush=True)
 time.sleep(20)
