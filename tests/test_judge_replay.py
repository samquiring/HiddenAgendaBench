import json

import pytest

from hidden_agenda.benchmark import actors
from hidden_agenda.judge_replay import prepare_replay, export_dataset
from test_comparison import saved_run


def test_replay_copies_grades_and_freezes_uniform_v2_config(tmp_path):
    source = saved_run(tmp_path/'source','actor')
    cal = source/'calibration/high/graded.jsonl'
    cal.parent.mkdir(parents=True)
    cal.write_text('')
    destination = tmp_path/'replay'
    manifest = prepare_replay(source,destination,workers=24,attempts=6)
    assert manifest['replay_only']
    assert manifest['judge_config']['judge_protocol']=='v2'
    assert manifest['judge_config']['attempt_limit']==6
    assert (source/'evaluation/high/graded.jsonl').read_bytes()==(destination/'evaluation/high/graded.jsonl').read_bytes()
    assert not (destination/'evaluation/high/actors').exists()
    assert prepare_replay(source,destination,24,6)==manifest
    with pytest.raises(ValueError,match='generation is prohibited'):
        actors(destination,manifest,'evaluation','high')
    with pytest.raises(ValueError,match='configuration or source data changed'):
        prepare_replay(source,destination,workers=12,attempts=6)


def test_replay_rejects_partial_actor_dataset(tmp_path):
    source = saved_run(tmp_path/'source','actor')
    cal = source/'calibration/high/graded.jsonl'
    cal.parent.mkdir(parents=True)
    cal.write_text('')
    path = source/'evaluation/high/graded.jsonl'
    rows = path.read_text().splitlines()
    path.write_text('\n'.join(rows[:-1]))
    with pytest.raises(ValueError,match='incomplete or duplicate'):
        prepare_replay(source,tmp_path/'replay')


def test_consolidation_requires_all_views_and_keeps_unavailable_results(tmp_path):
    source = saved_run(tmp_path/'source','actor')
    manifest=json.loads((source/'manifest.json').read_text())
    manifest['judge_views']=['reasoning']
    cal=source/'calibration/high'
    cal.mkdir(parents=True)
    (cal/'graded.jsonl').write_text('')
    (cal/'judgments.jsonl').write_text('')
    with pytest.raises(ValueError,match='missing or unexpected'):
        export_dataset([source],[manifest],tmp_path)
    rows=[dict(run_id=str(i),view='reasoning',status='unavailable' if i==0 else 'ok',judge_protocol='v2') for i in range(3)]
    (source/'evaluation/high/judgments.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
    counts=export_dataset([source],[manifest],tmp_path)
    assert counts==dict(trajectories=3,final_judgments=3)
    results=[json.loads(line) for line in (tmp_path/'judgments.jsonl').read_text().splitlines()]
    assert results[0]['status']=='unavailable'
    assert all(r['model_run']=='source' and r['partition']=='evaluation' for r in results)
