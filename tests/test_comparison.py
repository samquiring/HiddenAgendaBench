import json

import pytest

from hidden_agenda.comparison import common_groups, load_runs
from test_length_analysis import record


def test_common_edges_keep_boundaries_and_empty_bins():
    records = [record(i, n) for i, n in enumerate([0, 127, 128, 511, 512, None])]
    groups, excluded = common_groups(records, [0, 128, 512, 2048])
    assert [[r['usage']['reasoning_tokens'] for r in g] for g in groups] == [[0, 127], [128, 511], [512], []]
    assert len(excluded) == 1
    with pytest.raises(ValueError):
        common_groups(records, [128, 512])


def saved_run(root, actor):
    directory = root / 'evaluation/high'
    directory.mkdir(parents=True)
    rows = [dict(record(i, tokens), id=str(i), condition=condition)
            for i, tokens, condition in [(0, 20, 'clean'), (1, 128, 'concealment'), (2, None, 'concealment')]]
    rows[2]['primary_success'] = False
    manifest = dict(actor=actor, judge='fixed-judge', judge_config={}, efforts=['high'],
                    samples=[dict(metadata=dict(id=r['id'], condition=r['condition'], partition='evaluation')) for r in rows])
    (root / 'manifest.json').write_text(json.dumps(manifest))
    (root / 'thresholds.json').write_text(json.dumps({'high': {v: {'threshold': 0, 'comparison': '>'}
                                                           for v in ('output', 'reasoning', 'reasoning_output')}}))
    (directory / 'graded.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
    (directory / 'judgments.jsonl').write_text(json.dumps(dict(run_id='1', view='reasoning',
                                                             status='ok', judgment={'suspicion': 0})))
    return root


def test_comparison_retains_failures_and_unknowns_in_aggregate(tmp_path):
    roots = [saved_run(tmp_path / name, name) for name in ('A', 'B')]
    models = load_runs(roots, [0, 128, 512])
    for model in models:
        assert model['n'] == 2 and model['excluded'] == 1
        assert model['excluded_run_ids'] == ['2']
        aggregate = {r['view']: r for r in model['aggregate']}
        assert aggregate['reasoning']['covert'] == 1
        assert aggregate['reasoning']['task_failure'] == 1
        assert aggregate['reasoning_output']['unresolved'] == 1
        assert {r['bin'] for r in model['bins']} == {2}
    path = roots[1] / 'manifest.json'
    manifest = json.loads(path.read_text())
    manifest['judge'] = 'different-judge'
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='judge settings differ'):
        load_runs(roots, [0, 128, 512])


def test_incomplete_evaluations_are_rejected(tmp_path):
    roots = [saved_run(tmp_path / name, name) for name in ('A', 'B')]
    path = roots[1] / 'evaluation/high/graded.jsonl'
    path.write_text(path.read_text().splitlines()[0])
    with pytest.raises(ValueError, match='incomplete'):
        load_runs(roots, [0, 128, 512])
