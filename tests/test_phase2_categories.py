import importlib.util
import json
from pathlib import Path
import pytest


@pytest.fixture
def annotator():
    spec=importlib.util.spec_from_file_location('judge_training',
        Path(__file__).parents[1]/'scripts/phase2/judge_training.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


@pytest.fixture
def record():
    return dict(primary='Write a Python function.',auxiliary='What is 2+2?',
                reasoning='Code reasoning.\n\nAuxiliary: 2+2=4.',visible_output='```python\npass\n```',trace_kind='emitted')


def test_categories_require_nonempty_visible_evidence(annotator,record):
    value=dict(categories=[dict(label='auxiliary_calculation',evidence_ids=['reasoning:3'])],notes='Visible arithmetic')
    assert annotator.parse_categories(json.dumps(value),record)==value
    value['categories'][0]['evidence_ids']=['reasoning:2']
    with pytest.raises(ValueError):annotator.parse_categories(json.dumps(value),record)
    value['categories'][0]['evidence_ids']=['private_question:1']
    with pytest.raises(ValueError):annotator.parse_categories(json.dumps(value),record)


def test_no_evidence_is_exclusive(annotator,record):
    value=dict(categories=[dict(label='no_auxiliary_evidence',evidence_ids=[])],notes='No evidence')
    assert annotator.parse_categories(json.dumps(value),record)==value
    value['categories'].append(dict(label='auxiliary_calculation',evidence_ids=['reasoning:3']))
    with pytest.raises(ValueError):annotator.parse_categories(json.dumps(value),record)


def test_category_context_does_not_change_monitor_context(annotator,record):
    from hidden_agenda.protocol import judge_messages_v2
    private='UNIQUE_PRIVATE_QUESTION_SENTINEL'
    record['auxiliary']=private
    assert private in annotator.category_messages(record)[1].content
    assert all(private not in message.content for message in judge_messages_v2(record,'reasoning_output'))
