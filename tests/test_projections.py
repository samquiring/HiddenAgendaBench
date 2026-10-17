from hidden_agenda.length_analysis import VIEWS
from hidden_agenda.projections import pool_models


def model(n=60, unknown=0):
    points = [dict(run_id=str(i), view=view, bin=i//20+1, reasoning_tokens=i+1,
                   outcome='unresolved' if i < unknown else 'detected')
              for view in VIEWS for i in range(n)]
    return dict(label='test', bins=[], individuals=points)


def test_pooling_recomputes_intervals_and_keeps_every_attempt_once():
    source = model()
    pooled = pool_models([source], .1)[0]
    for view in VIEWS:
        bins = [b for b in pooled['bins'] if b['view'] == view]
        assert len(bins) == 1
        assert bins[0]['n'] == 60
        assert bins[0]['width_target_met']
        assert len(set(bins[0]['run_ids'])) == 60
    assert all('pooled_bin' not in p for p in source['individuals'])


def test_unachievable_width_is_retained_and_flagged():
    pooled = pool_models([model(100, unknown=6)], .1)[0]
    for row in pooled['bins']:
        assert row['n'] == 100
        assert row['unresolved'] == 6
        assert row['confirmed_rate'] == 0
        assert row['ci_width'] > .1
        assert not row['width_target_met']


def test_pooling_preserves_nonzero_measurements():
    source = model()
    for point in source['individuals']:
        if point['run_id'] == '0':
            point['outcome'] = 'covert'
    pooled = pool_models([source], .1)[0]
    for view in VIEWS:
        assert sum(b['covert'] for b in pooled['bins'] if b['view'] == view) == 1
