import importlib.util
import json
from pathlib import Path


def test_reuse_preserves_inherited_and_incorrect_completed_responses(tmp_path):
    spec=importlib.util.spec_from_file_location('training_runner',
        Path(__file__).parents[1]/'scripts/phase2/run_training_cases.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    records=[dict(primary_id='MBPP/601',actor_status='ok',output='original inherited output',
                  primary_success=True),
             dict(primary_id='MBPP/602',actor_status='ok',output='completed but incorrect',
                  primary_success=False),
             dict(primary_id='MBPP/603',actor_status='error',output='',primary_success=None)]
    (tmp_path/'graded.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
    kept=module.reusable_responses(tmp_path)
    assert kept==records[:2]
