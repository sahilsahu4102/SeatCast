import duckdb
import pandas as pd
import pytest

from seatcast import checks


@pytest.fixture
def con():
    c = duckdb.connect()
    c.execute(checks.MAC)
    return c


def test_haversine(con):
    one = con.execute('SELECT haversine_m(28.6, 77.2, 28.6, 77.2)').fetchone()[0]
    deg = con.execute('SELECT haversine_m(28.0, 77.0, 29.0, 77.0)').fetchone()[0]
    assert one == 0 and abs(deg - 111195) < 100


def test_ist_to_utc(con):
    # 2026-10-14 10:00 IST = 04:30 UTC
    t = con.execute("SELECT ist_utc(TIMESTAMP '2026-10-14 10:00:00')").fetchone()[0]
    assert t == con.execute("SELECT epoch(TIMESTAMP '2026-10-14 04:30:00')").fetchone()[0]
    assert str(con.execute(f'SELECT ist_day({t})').fetchone()[0]) == '2026-10-14'
    assert con.execute(f'SELECT ist_hour({t})').fetchone()[0] == 10


def test_asof_window(con):
    g = pd.DataFrame({'v': ['A', 'A', 'B'], 't': [100, 200, 100], 'lat': [1.0, 2.0, 3.0], 'lon': [0.0] * 3, 'route_id': [7, 7, 8]})
    t = pd.DataFrame({'tid': [1, 2, 3, 4], 'v': ['A', 'A', 'B', 'C'], 't': [230, 290, 150, 150]})
    con.register('g', g)
    con.register('t', t)
    r = con.sql(checks.asof('t', 'g', 60)).df().sort_values('tid')
    # 1: ping at 200 (lag 30); 2: lag 90 > 60 dropped; 3: ping at 100 (lag 50); 4: unknown vehicle dropped
    assert r['tid'].tolist() == [1, 3] and r['lag'].tolist() == [30, 50] and r['lat'].tolist() == [2.0, 3.0]
    assert con.sql(checks.asof('t', 'g', 100)).df()['tid'].tolist().count(2) == 1


def test_dstats():
    s = checks.dstats(pd.Series([100, 200, 400, 600, 1000.0]), [300, 500])
    assert s['median_m'] == 400 and s['within_300m'] == 0.4 and s['within_500m'] == 0.6


def test_shrunk_ratio():
    assert checks.shrunk(0, 0, 10) == 1
    assert checks.shrunk(30, 20, 10) == pytest.approx(40 / 30)
    assert checks.shrunk(0, 10, 10) == 0.5


def test_band():
    b = [0, 7, 10, 17, 20, 24]
    assert [checks.band(h, b) for h in (0, 6, 7, 9, 10, 16, 17, 19, 20, 23)] == [0, 0, 7, 7, 10, 10, 17, 17, 20, 20]


def test_daytype_holidays():
    h = {'2026-10-02', '2026-10-20'}
    # Fri holiday, Tue holiday, Wed, Sat, Sun
    assert [checks.daytype(d, h) for d in ('2026-10-02', '2026-10-20', '2026-10-14', '2026-10-17', '2026-10-11')] == [
        'sunday', 'sunday', 'weekday', 'saturday', 'sunday']


def test_pass_clustering(con):
    n = pd.DataFrame({'route_id': [1] * 7, 'stop_id': ['s'] * 7, 'v': ['A'] * 5 + ['B'] * 2,
                      't': [0, 100, 300, 1500, 1560, 0, 1200], 'm': [90, 40, 80, 70, 20, 10, 10]})
    con.register('n', n)
    r = con.sql(checks.passq('n', 900)).df().sort_values(['v', 't'])
    # A: pings 0..300 form one pass (closest ping at 100), 1500..1560 another (closest 1560); B: 20 min apart -> two passes
    assert r['v'].tolist() == ['A', 'A', 'B', 'B'] and r['t'].tolist() == [100, 1560, 0, 1200]
    two = pd.DataFrame({'route_id': [1, 1], 'stop_id': ['s', 's'], 'v': ['C', 'C'], 't': [0, 300], 'm': [5, 5]})
    con.register('two', two)
    assert len(con.sql(checks.passq('two', 900)).df()) == 1


def test_km_step_filter(con):
    # same vehicle: 200 m ok; 5 m jitter; 200 s gap; route change; ~1.5 km jump. each step is ~111 m per 0.001 deg unless noted
    g = pd.DataFrame({'v': ['A'] * 7, 'route_id': [1, 1, 1, 1, 2, 2, 2],
                      't_utc': [0, 10, 20, 300, 310, 320, 330],
                      'lat': [28.0, 28.002, 28.002 + 0.00004, 28.00204 + 0.0, 28.00204, 28.00204, 28.00204 + 0.014],
                      'lon': [77.0] * 7})
    con.register('g', g)
    k = {**checks.NEW, 'km_dt': [1, 120], 'km_step': [10, 1000]}
    r = con.sql(checks.kmq('g', k)).df()
    # step 1->2 (222 m) kept; 2->3 (4 m) jitter; 3->4 dt 280 s; 4->5 route change; 5->6 zero; 6->7 1.55 km jump
    assert r['steps'].sum() == 1 and abs(r['km'].sum() - 0.2224) < 0.01 and r['route_id'].iloc[0] == 1


def test_hop_banding(con):
    st = pd.DataFrame({'trip_id': ['t'] * 3, 'dep': [7 * 3600 + 3000, 8 * 3600 + 600, 8 * 3600 + 1800]})
    tp = pd.DataFrame({'trip_id': ['t'], 'pattern_id': ['p']})
    ps = pd.DataFrame({'pattern_id': ['p'] * 3, 'k': [0, 1, 2], 'dist_m': [0.0, 1000.0, 3000.0]})
    tr = pd.DataFrame({'trip_id': ['t'], 'route_id': ['9'], 'service_id': ['s']})
    ok = pd.DataFrame({'service_id': ['s'], 'daytype': ['weekday']})
    sc, lr = checks.hopkm(con, st, tp, ps, tr, ok)
    # hop 1 (1 km) departs 07:50 -> hour 7; hop 2 (2 km) departs 08:10 -> hour 8; last stop starts no hop
    assert sc.sort_values('h')[['h', 'sched']].values.tolist() == [[7, 1.0], [8, 2.0]] and lr.loc[9] == 3.0
