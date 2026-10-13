import json
from types import SimpleNamespace
import pytest
from hidden_agenda import benchmark
from hidden_agenda.config import RunConfig
from hidden_agenda.monitor import judge_job

@pytest.fixture
def dataset(monkeypatch, tmp_path):
    sources=tmp_path/'sources';sources.mkdir()
    (sources/'manifest.json').write_text('{}')
    monkeypatch.setattr(benchmark,'SOURCES',sources)
    def pairs(count,split):
        for i in range(count):
            yield dict(id=f'{split}-{i}',primary_id=f'code-{split}-{i}',
                       auxiliary_id=f'math-{split}-{i}',primary='def f(): pass',
                       auxiliary='2+2?',answer='4',split=split,seed=20261004)
    monkeypatch.setattr(benchmark,'public_pairs',pairs)
    return tmp_path/'run'

def test_model_changes_preserve_dataset_and_reject_mixed_resume(dataset):
    first=benchmark.freeze(dataset,RunConfig())
    other=RunConfig(actor='openrouter/example/actor',effort='high',max_tokens=1234)
    second=benchmark.freeze(dataset.parent/'other',other)
    assert first['samples']==second['samples']
    assert len(first['samples'])==230
    assert second['actor']=='openrouter/example/actor'
    assert second['judge']==first['judge']
    assert second['efforts']==['high']
    assert second['actor_config']['max_tokens']==1234
    assert benchmark.freeze(dataset)==first
    with pytest.raises(ValueError,match='Configuration differs'):
        benchmark.freeze(dataset,other)

def test_judge_receives_config_and_retries_only_invalid(monkeypatch):
    record=dict(run_id='r',condition='concealment',actor='mock',primary_success=True,
        auxiliary_success=True,trace_kind='emitted',requested_effort='high',primary_id='p',
        auxiliary_id='a',actor_status='ok',primary='public',reasoning='exact quote',visible_output='code')
    received=[]
    def call(command,**kwargs):
        assert command[-2:]==['-m','hidden_agenda.monitor']
        received.append(json.loads(kwargs['input']))
        raw='bad json' if len(received)==1 else json.dumps(dict(suspicion=1,suspected_task='math',evidence=['exact quote']))
        return SimpleNamespace(returncode=0,stdout=json.dumps(dict(raw_judgment=raw)),stderr='')
    monkeypatch.setattr('hidden_agenda.monitor.subprocess.run',call)
    result=judge_job((record,'reasoning','judge/model'),(1,2,3),
                     dict(reasoning_effort=None,max_tokens=987,model_args={'stream':True}))
    assert [r['status'] for r in result]==['judge_error','ok']
    assert len(received)==2 and received[0]['reasoning_effort'] is None
    assert received[0]['max_tokens']==987 and received[0]['model_args']=={'stream':True}

def test_calibration_freezes_before_evaluation_calls(dataset,monkeypatch):
    manifest=benchmark.freeze(dataset,RunConfig(effort='high'))
    events=[]
    def actors(root,config,partition,effort):
        events.append(partition)
        if partition=='evaluation':assert (root/'thresholds.json').exists()
        directory=root/partition/effort;directory.mkdir(parents=True,exist_ok=True)
        return directory
    def judge(directory,config):
        for i in range(30):
            for view in config['judge_views']:
                benchmark.append(directory/'judgments.jsonl',dict(run_id=str(i),view=view,status='ok',judgment={'suspicion':0}))
    monkeypatch.setattr(benchmark,'actors',actors)
    monkeypatch.setattr(benchmark,'grade',lambda *args:None)
    monkeypatch.setattr(benchmark,'judge',judge)
    monkeypatch.setattr(benchmark,'report',lambda *args:None)
    benchmark.run(dataset,manifest)
    assert events==['calibration','evaluation']
    assert json.loads((dataset/'thresholds.json').read_text())['high']['reasoning']['threshold']==0

def test_partial_report_cannot_shrink_denominator(dataset):
    manifest=benchmark.freeze(dataset)
    (dataset/'thresholds.json').write_text(json.dumps({'low':{}}))
    with pytest.raises(ValueError,match='230|200'):
        benchmark.report(dataset)

def test_actor_provider_options_and_omitted_effort_reach_inspect(dataset,monkeypatch):
    manifest=benchmark.freeze(dataset,RunConfig(actor='mockllm/custom',effort='none',actor_args={'stream':True},max_tokens=456))
    captured={}
    def model(name,**kwargs):
        captured['model']=(name,kwargs)
        return 'model-object'
    def evaluate(task,**kwargs):
        captured['eval']=kwargs
        captured['samples']=len(task.dataset)
        return [SimpleNamespace(status='success')]
    monkeypatch.setattr(benchmark,'get_model',model)
    monkeypatch.setattr(benchmark,'eval',evaluate)
    benchmark.actors(dataset,manifest,'calibration','none')
    assert captured['model']==('mockllm/custom',{'stream':True})
    assert captured['eval']['reasoning_effort'] is None
    assert captured['eval']['max_tokens']==456 and captured['samples']==30

def test_incomplete_calibration_stops_before_evaluation(dataset,monkeypatch):
    manifest=benchmark.freeze(dataset)
    stages=[]
    def actors(root,config,partition,effort):
        stages.append(partition)
        directory=root/partition/effort;directory.mkdir(parents=True,exist_ok=True)
        return directory
    monkeypatch.setattr(benchmark,'actors',actors)
    monkeypatch.setattr(benchmark,'grade',lambda *args:None)
    monkeypatch.setattr(benchmark,'judge',lambda *args:None)
    with pytest.raises(RuntimeError,match='Calibration incomplete'):
        benchmark.run(dataset,manifest)
    assert stages==['calibration']

@pytest.mark.parametrize('kwargs',[{'max_tokens':0},{'judge_workers':True},{'actor_args':{'api_key':'not-a-real-key'}}])
def test_invalid_or_secret_settings_rejected(kwargs):
    with pytest.raises(ValueError):RunConfig(**kwargs)
