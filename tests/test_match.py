from pathlib import Path

import pandas as pd
import pytest

from seatcast import gtfs, match
from seatcast.clean import norm, parse_route

TOY = Path(__file__).parent / 'fixtures' / 'toy_gtfs'


@pytest.fixture(scope='module')
def feed(tmp_path_factory):
    w = tmp_path_factory.mktemp('work')
    g = gtfs.load(TOY, w=w)
    pat, ps, _ = gtfs.patterns(g=g, w=w)
    return g, pat, ps


def ods(code, pairs):
    b = parse_route(code)
    return pd.DataFrame([{'route_raw': code, 'base': b[0] if b else None, 'dir': b[1] if b else None,
                          'ss': s, 'es': e, 'ss_n': norm(s), 'es_n': norm(e), 'p': 1, 'n': 1} for s, e in pairs])


def row(res, s, e):
    x = res['od']
    return x[(x['ss_n'] == norm(s)) & (x['es_n'] == norm(e))].iloc[0]


def test_route_rungs(feed):
    g, pat, _ = feed
    c = pd.DataFrame({'route_raw': ['10UP', '10DOWN2', '010UP', '11UP', 'ZZ SERVICE']})
    c['base'], c['dir'] = zip(*[(parse_route(x) or (None, None))[:2] for x in c['route_raw']])
    r = match.match_routes(c, match.groutes(g, pat), {'ZZSERVICE': '10DOWN'})
    assert list(zip(r['route_id'].fillna('-'), r['rung_route'])) == [('R1', 1), ('R2', 2), ('R1', 3), ('-', 0), ('R2', 4)]


def test_stop_rungs(feed):
    names = ['Kashmere Gate ISBT', 'Kashmiri Gate ISBT', 'Uttam Nagr', 'Nagar', 'Rohini', 'Rohini Sec 23', 'Utam Nagar W']
    res = match.build(ods('10UP', [(n, 'Mandi House') for n in names]), *feed)
    nm = res['names'].query("route_id == 'R1'").set_index('name_n')
    got = {n: (nm.at[norm(n), 'rung'], nm.at[norm(n), 'gtfs_n']) for n in names}
    assert got['Kashmere Gate ISBT'] == ('a', 'kashmere gate isbt')
    assert got['Kashmiri Gate ISBT'] == ('c', 'kashmere gate isbt')      # 88.9: fuzzy accept
    assert got['Utam Nagar W'] == ('c', 'uttam nagar west')              # 85.7 vs 71.4: margin met
    assert pd.isna(got['Uttam Nagr'][0])                                  # 76.9 tie: margin reject
    assert pd.isna(got['Nagar'][0])                                       # subset guard, two supersets
    assert got['Rohini'] == ('e', 'rohini sector 22')                    # subset guard, unique superset
    assert pd.isna(got['Rohini Sec 23'][0])                               # number guard


def test_guards():
    s = lambda q, c: match.score([q], [c], {'maybe': 75, 'rest': 70})[0][0, 0]
    assert s('s j terminal', 'munirka village terminal') < 75            # generic word alone is no match
    assert s('hamdard nagar sangam vihar', 'ambedkar nagar') < 75        # unshared words too different
    assert s('hauz rani', 'hauj rani') >= 88


def test_duplicate_name_index(feed):
    # Mandi House is both k=1 and k=5 on 10UP: pick the in-order pair with the smallest span
    res = match.build(ods('10UP', [('Kashmere Gate ISBT', 'Mandi House'), ('Uttam Nagar West', 'Mandi House'),
                                   ('Mandi House', 'Uttam Nagar East')]), *feed)
    got = [(r['b'], r['a']) for r in [row(res, 'Kashmere Gate ISBT', 'Mandi House'),
                                      row(res, 'Uttam Nagar West', 'Mandi House'),
                                      row(res, 'Mandi House', 'Uttam Nagar East')]]
    assert got == [(0, 1), (4, 5), (1, 3)]


def test_swapped_direction(feed):
    # tickets coded 10UP travel in 10DOWN's stop order: the whole code moves to R2
    res = match.build(ods('10UP', [('Uttam Nagar West', 'Kashmere Gate ISBT'), ('Uttam Nagar East', 'Rohini Sec 22'),
                                   ('Rohini Sec 22', 'Kashmere Gate ISBT')]), *feed)
    assert res['swaps']['route_raw'].tolist() == ['10UP']
    x = res['od']
    assert (x['route_id'] == 'R2').all() and (x['status'] == 'ok').all() and x['swapped'].all()
    r = row(res, 'Uttam Nagar West', 'Kashmere Gate ISBT')
    assert (r['pattern_id'], r['b'], r['a']) == ('R2:0', 1, 5)


def test_same_stop_dropped(feed):
    res = match.build(ods('10UP', [('Rohini Sec 22', 'Rohini Sector 22'), ('Rohini Sec 22', 'Uttam Nagar East')]), *feed)
    assert res['od']['status'].tolist() == ['same', 'ok']


def test_alias_variants():
    # "a|b": the first GTFS spelling present on the route wins, so one alias row covers both road sides
    q = pd.DataFrame({'route_id': ['r1', 'r2'], 'name_n': ['s j hospital'] * 2, 'raw': ['S J Hospital'] * 2, 'p': [5, 3]})
    cand = pd.DataFrame({'route_id': ['r1', 'r2'], 'gtfs_n': ['safdurjung hospital aiims', 'aiims safdurjung hospital'],
                         'raw': ['x', 'y']})
    al = pd.DataFrame({'route_id': [''], 'name_n': ['s j hospital'],
                       'gtfs_n': ['safdurjung hospital aiims|aiims safdurjung hospital']})
    nm = match.match_names(q, cand, al, None).set_index('route_id')
    assert nm.loc['r1', 'gtfs_n'] == 'safdurjung hospital aiims'
    assert nm.loc['r2', 'gtfs_n'] == 'aiims safdurjung hospital'
    assert (nm['rung'] == 'b').all()
