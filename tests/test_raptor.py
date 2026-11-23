from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from seatcast import gtfs, raptor

TOY = Path(__file__).parent / 'fixtures' / 'toy_net'
H = 3600


@pytest.fixture(scope='module')
def net(tmp_path_factory):
    return raptor.load(TOY, rebuild=True, w=tmp_path_factory.mktemp('work'))


def ix(net, s):
    return net.stop_id.tolist().index(s)


def go(net, a, b, t, dt='weekday', **kw):
    return raptor.query(net, [(ix(net, a), 0)], [(ix(net, b), 0)], t, dt, **kw)


def buses(j):
    return [l['route_id'] for l in j['legs'] if l['mode'] == 'bus']


def test_secs_past_midnight():
    assert gtfs.secs(pd.Series(['08:00:00', '25:30:05', ' 7:05:00'])).tolist() == [8 * H, 25 * H + 30 * 60 + 5, 7 * H + 300]


def test_direct(net):
    j = go(net, 'A', 'C', 8 * H, 'saturday')
    assert [(x['rides'], x['arrive'], buses(x)) for x in j] == [(1, 8 * H + 40 * 60, ['R1'])]
    l = j[0]['legs'][1]
    assert (l['k1'], l['k2'], l['dep'], l['times']) == (0, 2, 8 * H, [8 * H, 8 * H + 1200, 8 * H + 2400])
    assert l['pattern'] == 'R1:0' and l['trip_id'] == 'R1_08_00'


def test_pareto_transfer_vs_direct(net):
    j = go(net, 'A', 'D', 8 * H)
    assert [(x['rides'], x['arrive'], buses(x)) for x in j] == [(1, 9 * H, ['R1']), (2, 8 * H + 35 * 60, ['R2', 'R3'])]


def test_daytype_and_ban(net):
    assert [x['rides'] for x in go(net, 'A', 'D', 8 * H, 'saturday')] == [1]  # R3 runs weekdays only
    assert [buses(x) for x in go(net, 'A', 'D', 8 * H, ban={'R1'})] == [['R2', 'R3']]


def test_footpath_transfer(net):
    j = go(net, 'C', 'G', 9 * H)
    assert [(x['rides'], x['arrive']) for x in j] == [(2, 9 * H + 35 * 60)]
    m = [l['mode'] for l in j[0]['legs']]
    assert m == ['walk', 'bus', 'walk', 'bus', 'walk']
    w = j[0]['legs'][2]
    assert w['from'] == ix(net, 'E') and w['to'] == ix(net, 'F') and 0 < w['sec'] < 300


def test_footpath_then_egress_is_one_walk(net):
    j = go(net, 'C', 'F', 9 * H)
    assert [l['mode'] for l in j[0]['legs']] == ['walk', 'bus', 'walk']
    w = j[0]['legs'][-1]
    assert w['from'] == ix(net, 'E') and w['to'] is None and 0 < w['sec'] < 300


def test_past_midnight(net):
    j = go(net, 'A', 'D', 24 * H + 20 * 60)
    assert [(x['arrive'], x['legs'][1]['trip_id']) for x in j] == [(25 * H + 30 * 60, 'R1_24_30')]


def test_window(net):
    assert go(net, 'A', 'D', 5 * H) == []
    assert go(net, 'A', 'D', 5 * H, window=240) != []


def test_overtaking_split(net):
    assert list(net.pid).count('R7:0') == 2  # the 08:10 trip overtakes the 08:00 one
    for p in range(len(net.pid)):
        assert raptor.sorted_cols(net.view('weekday')[p][1])
    assert go(net, 'X', 'Y', 8 * H)[0]['arrive'] == 8 * H + 40 * 60
    assert not raptor.sorted_cols(np.array([[0, 60], [10, 50]]))
    assert raptor.fifo(np.array([[0, 60], [10, 50], [20, 70]])) == [[0, 2], [1]]


def test_patterns_and_dist(net, tmp_path):
    pat, ps, tp = gtfs.patterns(TOY, w=tmp_path)
    assert pat.set_index('pattern_id').loc['R1:0', ['n_trips', 'n_stops', 'dist_src']].tolist() == [3, 4, 'shape']
    assert ps[ps['pattern_id'] == 'R1:0']['dist_m'].tolist() == [0, 2400, 4800, 7200]
    assert pat.set_index('pattern_id').loc['R2:0', 'dist_src'] == 'haversine'
    assert (tmp_path / 'patterns.parquet').exists() and (tmp_path / 'pattern_stops.parquet').exists()
    assert 'Foxtrot & Co' in net.stop_name


def test_near_and_footpaths(net):
    e = ix(net, 'E')
    to = net.fp_to[net.fp_ptr[e]:net.fp_ptr[e + 1]]
    assert [net.stop_id[i] for i in to] == ['F']
    assert [i for i, _ in raptor.near(net, 28.6405, 77.25)] == [e, ix(net, 'F')]
