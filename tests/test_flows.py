from datetime import date, datetime

import duckdb
import pandas as pd
import pytest

from seatcast import flows, load

D1, D2 = date(2026, 10, 5), date(2026, 10, 6)


def toy():
    # one 4-stop pattern A-B-C-D, 5 min between stops at every hour
    con = duckdb.connect()
    ps = pd.DataFrame({'pattern_id': 'R:0', 'k': range(4), 'stop_id': list('ABCD')})
    flows.seg(con, ps)
    off = pd.DataFrame([('R:0', k, h, 300.0 * k) for h in [-1, 8] for k in range(4)],
                       columns=['pattern_id', 'k', 'h', 'cum'])
    con.register('off', off)
    return con


def tk(rows):
    t = pd.DataFrame(rows, columns=['tid', 'b', 'a', 'pc', 'ts'])
    t['ts'] = pd.to_datetime(t['ts'])
    t['route_id'], t['pattern_id'], t['daytype'], t['week'] = 'R', 'R:0', 'weekday', 1
    t['date'] = t['ts'].dt.date
    t['w'] = t['ws'] = t['pc'].astype(float)
    return t


def test_two_tickets_segment_flows():
    con = toy()
    con.register('tk', tk([(1, 0, 3, 1, '2026-10-05 08:00'), (2, 1, 2, 2, '2026-10-05 08:05')]))
    d = flows.daily(con).df().set_index('s0')
    assert d['pax'].to_dict() == {'A': 1, 'B': 3, 'C': 1}
    assert d['s1'].to_dict() == {'A': 'B', 'B': 'C', 'C': 'D'}
    assert set(d['slot']) == {16}


def test_slot_is_when_bus_passes_stop():
    con = toy()
    con.register('tk', tk([(1, 0, 3, 1, '2026-10-05 08:26')]))
    d = flows.daily(con).df().set_index('s0')['slot'].to_dict()
    assert d == {'A': 16, 'B': 17, 'C': 17}


def test_zero_flow_date_lowers_f():
    con = duckdb.connect()
    fl = pd.DataFrame({'route_id': 'R', 's0': 'A', 's1': 'B', 'slot': 16, 'daytype': 'weekday',
                       'date': [D1, D2], 'week': 1, 'pax': [4.0, 2.0], 'n': [4.0, 2.0]})
    con.register('flows', fl)
    con.register('bad', pd.DataFrame({'date': pd.Series([], dtype='datetime64[ns]')}))
    con.register('nd', pd.DataFrame({'daytype': ['weekday'], 'nd': [2]}))
    f2 = load.stats(con).set_index('slot').loc[16, 'f']
    con.register('nd', pd.DataFrame({'daytype': ['weekday'], 'nd': [4]}))
    s = load.stats(con).set_index('slot')
    assert f2 == 3 and s.loc[16, 'f'] == 1.5 and s.loc[16, 'n'] == 6 and s.loc[16, 'cv_day'] == 0.5
    assert s.loc[16, 'scale'] == 1
    assert sorted(s.index) == [15, 16, 17]  # neighbours pool this slot's flow (slot_window = 1)


def test_impute_from_placed_distribution():
    con = duckdb.connect()
    od = pd.DataFrame({'pattern_id': 'R:0', 'b': 0, 'a': [3, 3, 3, 3, 2, 2], 'pc': 1,
                       'ts': datetime(2026, 10, 5, 8, 10), 'daytype': 'weekday'})
    part = pd.DataFrame({'tid': [9], 'route_id': 'R', 'pattern_id': 'R:0', 'k': 0, 'e': 'b', 'pc': 3,
                         'ts': datetime(2026, 10, 5, 8, 40), 'date': D1, 'daytype': 'weekday', 'week': 1})
    con.register('od', od)
    con.register('part', part)
    flows.impute(con, 5)
    d = con.sql('SELECT a, w FROM imp ORDER BY a').df()
    assert d['a'].tolist() == [2, 3]
    assert d['w'].tolist() == pytest.approx([1, 2])
    assert con.sql('SELECT lvl FROM pick').fetchall() == [(1,)]
