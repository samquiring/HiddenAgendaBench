import json
import pytest
from types import SimpleNamespace

from hidden_agenda.monitor import judge_job


@pytest.mark.parametrize('reminder', [False, True])
def test_v2_protocol_is_sent_to_child_and_validated_at_call_site(monkeypatch, reminder):
    record = dict(run_id='run', condition='clean', actor='actor', primary_success=True,
                  auxiliary_success=False, trace_kind='emitted', requested_effort='high',
                  primary_id='code', auxiliary_id='math', actor_status='ok', primary='Return code',
                  reasoning='Ordinary coding reasoning.\n', visible_output='def f(): pass')
    def call(command, **kwargs):
        request = json.loads(kwargs['input'])
        assert request['judge_protocol'] == 'v2'
        assert request['nonempty_evidence_reminder'] is reminder
        verdict = dict(suspicion=0, suspected_task='', evidence_ids=['reasoning:1'])
        return SimpleNamespace(returncode=0, stdout=json.dumps(dict(raw_judgment=json.dumps(verdict))), stderr='')
    monkeypatch.setattr('hidden_agenda.monitor.subprocess.run', call)
    result = judge_job((record, 'reasoning', 'judge'), (7,),
                       {'judge_protocol':'v2', 'nonempty_evidence_reminder':reminder})
    assert len(result) == 1 and result[0]['status'] == 'ok'
    assert result[0]['judge_protocol'] == 'v2'
    assert result[0].get('prompt_amendment') == ('nonempty-evidence-reminder-v1' if reminder else None)
    assert result[0]['judgment']['evidence'] == ['Ordinary coding reasoning.\n']
