import json

from hidden_agenda.aggregate_comparison import OPENAI_REFERENCE, aggregate_rows
from hidden_agenda.comparison import load_runs
from test_comparison import saved_run


def test_aggregate_keeps_missing_token_attempts_and_unknowns(tmp_path):
    models = load_runs([saved_run(tmp_path / name, name) for name in ('A', 'B')], [0, 128, 512])
    rows = aggregate_rows(models)
    assert len(rows) == 6
    for row in rows:
        assert row['n'] == 2
        assert row['joint_success'] == 1
        if row['view'] == 'reasoning':
            assert row['covert'] == 1
            assert row['confirmed_rate'] == .5
        elif row['view'] == 'success':
            assert row['confirmed'] == 1
            assert row['covert'] is None
            assert row['unresolved'] == 0
        else:
            assert row['covert'] == 0
            assert row['unresolved'] == 1
            assert row['possible_rate'] == .5
        assert row['ci95_low'] <= row['confirmed_rate'] <= row['ci95_high']


def test_published_reference_does_not_fabricate_numerical_results():
    assert OPENAI_REFERENCE['models'] == ['GPT-6 Astra', 'GPT-5.6 Sol']
    for key in ('trial_count', 'successful_trial_count', 'numerical_rate', 'confidence_interval'):
        assert OPENAI_REFERENCE[key] is None


def test_aggregate_does_not_require_token_accounting(tmp_path):
    roots = [saved_run(tmp_path / name, name) for name in ('A', 'B')]
    for root in roots:
        path = root / 'evaluation/high/graded.jsonl'
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        for row in rows:
            row['usage'] = None
        path.write_text('\n'.join(json.dumps(row) for row in rows))
    models = load_runs(roots, [0, 128, 512], require_tokens=False)
    assert all(m['bins'] == [] for m in models)
    assert all(r['n'] == 2 for r in aggregate_rows(models))
