# Checks on the real outputs of each pipeline step. Each skips when its input isn't built (as in CI).
import re

import duckdb
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

from seatcast import OUT, RAW, WORK, cfg

CSV = RAW / 'tickets' / 'October-Delhi.csv'
TIX = WORK / 'tickets.parquet'
PAT, PS, NET = WORK / 'patterns.parquet', WORK / 'pattern_stops.parquet', WORK / 'network.npz'
FEED = RAW / 'gtfs' / 'stops.txt'
PLATE = re.compile(r'DL ?\d{1,2} ?[A-Z]{1,3} ?\d{4}')


def need(*ps):
    return pytest.mark.skipif(not all(p.exists() for p in ps), reason='needs pipeline data')


@pytest.fixture(scope='module')
def t():
    return pd.read_parquet(TIX)


# P1 ingest
@need(CSV, TIX)
def test_tickets_complete(t):
    q = (f"SELECT COUNT(*), SUM(CAST(passenger_count AS INT)) FROM read_csv('{CSV.as_posix()}', "
         "header = true, nullstr = ['NULL', ''], all_varchar = true)")
    n, pax = duckdb.sql(q).fetchall()[0]
    assert (len(t), t['pc'].sum()) == (n, pax)


@need(TIX)
def test_tickets_fields(t):
    for c in ['tid', 'pc', 'ts', 'date', 'slot', 'daytype', 'route_raw']:
        assert t[c].notna().all(), c
    assert t['tid'].is_unique
    assert t['pc'].between(1, 6).all()
    m = t['ts'].dt.hour * 60 + t['ts'].dt.minute
    assert (m // cfg()['slot_min'] == t['slot']).all()


@need(TIX)
def test_daytypes(t):
    g = t.groupby('date')['daytype'].agg(['nunique', 'first'])
    assert (g['nunique'] == 1).all()
    d = pd.Series(pd.to_datetime(g.index))
    assert (d.max() - d.min()).days + 1 == len(d)  # no missing days
    wd = d.dt.day_of_week
    hol = d.isin(pd.to_datetime(cfg()['holidays']))
    exp = np.where(hol | (wd == 6), 'sunday', np.where(wd == 5, 'saturday', 'weekday'))
    assert (g['first'].to_numpy() == exp).all()


@need(TIX)
def test_ticket_facts(t):
    w = t['pc'].sum()
    assert t.loc[t['fare_class'] == 'std', 'pc'].sum() / w > 0.98  # CLAUDE.md §3 fact 1: app e-tickets
    assert t.loc[t['base'].notna(), 'pc'].sum() / w > 0.999  # route codes parse
    assert t['f_zero'].sum() < 100  # fact 3: next to no zero fares


# P5a patterns and network
@need(PAT, PS)
def test_patterns():
    pat, ps = pd.read_parquet(PAT), pd.read_parquet(PS)
    assert set(pat['pattern_id']) == set(ps['pattern_id'])
    assert not ps.duplicated(['pattern_id', 'k']).any()
    g = ps.groupby('pattern_id')
    assert (g['k'].min() == 0).all() and (g['k'].max() + 1 == g.size()).all()
    assert (g['dist_m'].diff().dropna() >= 0).all()  # distance never runs backwards
    assert pat.groupby('route_id')['canonical'].sum().eq(1).all()


@need(NET, FEED)
def test_demo_query():
    from seatcast import raptor
    net = raptor.load()
    src = raptor.near(net, 28.6469, 77.3159)  # Anand Vihar ISBT
    dst = raptor.near(net, 28.6315, 77.2167)  # Connaught Place
    j = raptor.query(net, src, dst, 18 * 3600)
    assert j and min(x['arrive'] for x in j) < 20 * 3600


# Every step: nothing vehicle-level in public outputs (CLAUDE.md §2 rule 5)
@need(OUT)
def test_outputs_private():
    for p in OUT.rglob('*'):
        if p.suffix == '.parquet':
            assert not {'v', 'vehicle', 'vehicle_number'} & set(pq.read_schema(p).names), p
        elif p.suffix in ('.json', '.geojson', '.csv', '.md'):
            assert not PLATE.search(p.read_text(encoding='utf-8')), p
