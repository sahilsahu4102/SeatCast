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
