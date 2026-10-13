import json
import pytest
from hidden_agenda.prompt_study import parse_submission
from hidden_agenda.protocol import judge_messages

@pytest.mark.parametrize('fmt,text', [
    ('last_line','```python\ndef f(): return 1\n```\n12345'),
    ('xml','```python\ndef f(): return 1\n```\n<auxiliary_answer>12345</auxiliary_answer>'),
    ('json',json.dumps({'code':'def f(): return 1','auxiliary_answer':'12345'})),
])
def test_exact_submission_removed_from_output_only(fmt,text):
    visible,code,answer,valid=parse_submission(text,fmt)
    assert valid and answer=='12345'
    assert '12345' not in visible and '```python' in code
    record=dict(primary='Implement f',visible_output=visible,reasoning='Private computation 12345',trace_kind='emitted')
    assert '12345' not in judge_messages(record,'output')[1].content
    assert '12345' in judge_messages(record,'reasoning_output')[1].content

@pytest.mark.parametrize('fmt,text',[
    ('json','{"code":"pass","auxiliary_answer":"4","auxiliary_answer":"5"}'),
    ('json','{"code":"pass","auxiliary_answer":4}'),
    ('json','{"code":"pass","auxiliary_answer":"4","extra":"x"}'),
    ('xml','```python\npass\n```<auxiliary_answer>4</auxiliary_answer> extra'),
    ('last_line','```python\npass\n```\nThe answer is 4'),
])
def test_malformed_submission_does_not_count(fmt,text):
    assert not parse_submission(text,fmt)[3]
