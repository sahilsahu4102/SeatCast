import pandas as pd
import pytest

from seatcast import load

K = {'crush_factor': 1.5, 'quantile': 0.95, 'iters': 5}


def test_calibration_caps_one_route_and_keeps_total():
    # route A: load 200 per bus at E = 1, over 1.5 x 60; route B: 10 per bus
    c = pd.DataFrame({'route_id': ['A'] * 3 + ['B'] * 3, 'f': [200.0] * 3 + [10.0] * 3, 'N_obs': 1.0,
                      'total': 60.0})
    D = pd.Series({'A': 100.0, 'B': 300.0})
    m, fixed = load.calibrate(c, D, 1.0, K)
    assert fixed.to_dict() == {'A': True, 'B': False}
    assert m['A'] == pytest.approx(90 / 200)
    assert m['B'] > 1
    assert (m * D).sum() == pytest.approx(D.sum())


def test_infeasible_caps_only():
    # both routes over the cap: nothing can absorb the riders, so no route is lifted
    c = pd.DataFrame({'route_id': ['A', 'B'], 'f': [200.0, 300.0], 'N_obs': 1.0, 'total': 60.0})
    m, fixed = load.calibrate(c, pd.Series({'A': 1.0, 'B': 1.0, 'C': 5.0}), 1.0, K)
    assert m.to_dict() == pytest.approx({'A': 0.45, 'B': 0.3, 'C': 1.0})
    assert fixed.to_dict() == {'A': True, 'B': True, 'C': False}


def test_no_cap_is_a_no_op():
    c = pd.DataFrame({'route_id': ['A', 'B'], 'f': [10.0, 20.0], 'N_obs': 1.0, 'total': 60.0})
    m, fixed = load.calibrate(c, pd.Series({'A': 1.0, 'B': 2.0}), 1.0, K)
    assert not fixed.any() and (m == 1).all()


def test_observed_n_joins_route_daytype_band():
    c = pd.DataFrame({'route_id': ['A', 'A', 'B'], 'daytype': 'weekday', 'h': [8, 18, 8], 'N': 4.0})
    r = pd.DataFrame({'route_id': ['A', 'A'], 'daytype': 'weekday', 'band': [7, 17], 'ratio': [0.5, 0.75]})
    o = load.observe(c, r, 'h')
    assert o['N_obs'].tolist() == [2.0, 3.0, 4.0]  # B has no row: ratio 1
    assert load.observe(c, None, 'h')['N_obs'].tolist() == [4.0, 4.0, 4.0]
