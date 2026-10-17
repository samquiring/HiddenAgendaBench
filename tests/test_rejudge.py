import json
import pytest

from hidden_agenda.io import read_rows
from hidden_agenda.rejudge import retry_failed
from test_comparison import saved_run


@pytest.mark.parametrize('protocol', ['v1','v2'])
def test_explicit_rejudge_only_retries_errors_and_preserves_valid_scores(tmp_path, monkeypatch, protocol):
    root = saved_run(tmp_path / 'run', 'actor')
    path = root / 'manifest.json'
    manifest = json.loads(path.read_text())
    manifest.update(judge_views=['output', 'reasoning', 'reasoning_output'],
                    judge_config=dict(workers=2, attempt_limit=3))
    path.write_text(json.dumps(manifest))
    target = root / 'evaluation/high/judgments.jsonl'
    original = [dict(run_id='1', view='output', status='judge_error', attempt=3),
                dict(run_id='1', view='reasoning', status='ok', attempt=1, judgment={'suspicion': 1}),
                dict(run_id='1', view='reasoning_output', status='unavailable')]
    target.write_text('\n'.join(json.dumps(r) for r in original)+'\n')
    called = []
    def judge(job, numbers, config):
        assert config.get('judge_protocol','v1') == protocol
        called.append((job[0]['run_id'], job[1], numbers))
        return [dict(run_id=job[0]['run_id'], view=job[1], status='ok', attempt=numbers[0], judgment={'suspicion': 0})]
    monkeypatch.setattr('hidden_agenda.rejudge.judge_job', judge)
    monkeypatch.setattr('hidden_agenda.benchmark.report', lambda root: None)
    assert retry_failed(root, protocol=protocol) == 1
    assert called == [('1', 'output', (4, 5, 6))]
    rows = read_rows(target)
    assert rows[:3] == original
    assert rows[-1]['attempt'] == 4 and rows[-1]['supplemental_retry_batch']
    archive = next((root / 'judge-retries').iterdir())
    assert read_rows(archive / 'high-judgments-before.jsonl') == original
    assert (archive / 'complete.json').exists()
    assert json.loads((archive/'plan.json').read_text())['judge_protocol'] == protocol
