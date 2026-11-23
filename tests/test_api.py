import json
import re
import statistics
import time

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from seatcast import OUT, api, plan
from test_plan import toy

BUILD = api.build  # the real loader, kept before any test patches it
PLATE = re.compile(r'DL ?\d{1,2} ?[A-Z]{1,3} ?\d{4}')
BAN = {'f', 'scale', 'ndata', 'series', 'vehicle_number'}


def private(x, path=''):
    # every key in a JSON response that must never be served
    out = []
    if isinstance(x, dict):
        for k, v in x.items():
            if k in BAN or 'vehicle' in k.lower() or 'series' in k.lower():
                out.append(path + '/' + k)
            out += private(v, path + '/' + k)
    elif isinstance(x, list):
        for v in x:
            out += private(v, path)
    return out


def check(r):
    assert r.status_code == 200, r.text
    assert not PLATE.search(r.text), 'plate in ' + str(r.url)
    assert private(r.json()) == [], r.url
    return r.json()


def toy_world(w):
    W = toy(w)
    W.op = pd.DataFrame({'route_id': ['R1', 'R2', 'R3'], 'daytype': 'weekday', 'hour': [8, 8, 18], 'P_max': 100.0,
                         'F_sched': 2.0, 'F_req': 3, 'gap': 1.0, 'standee_min': [50.0, 80.0, 30.0],
                         'plus1_benefit': [10.0, 20.0, 5.0], 'L_max': 50.0, 'LF_max': 1.25, 'n_max': 20.0,
                         'max_from': 'Alpha', 'max_to': 'Bravo', 'route': ['R1UP', 'R2UP', 'R3UP'],
                         'base': ['R1', 'R2', 'R3'], 'dir': 'UP', 'series': 'DL1PD', 'vehicle_number': 'DL1PD' + '1234', 'f': 1.0})  # plate built at runtime: CI fails on plate literals
    W.cov = {'coverage': {'match': {'route_matched_pct': 95.0, 'rungs': {'f': 3.1}},
                          'load': {'E': {'central': 44.6}, 'scale_max': 2.0}},
             'gps_checks': {'overlap': {'share_tickets_null_vehicle': .45, 'by_series': {'DL51EV': {'vehicle_days': 1}}},
                            'route_check': {'ok': True}}}
    return W


@pytest.fixture(scope='module')
def c(tmp_path_factory):
    W = toy_world(tmp_path_factory.mktemp('work'))
    mp = pytest.MonkeyPatch()
    mp.setattr(api, 'build', lambda: W)
    api.heat.cache_clear()
    with TestClient(api.app) as x:
        yield x
    mp.undo()
    api.heat.cache_clear()


def test_health_and_docs(c):
    assert check(c.get('/health')) == {'ok': True}
    assert c.get('/docs').status_code == 200 and '/journeys' in c.get('/openapi.json').json()['paths']
    assert c.get('/').status_code == 200 and 'text/html' in c.get('/').headers['content-type']


def test_stops(c):
    a = check(c.get('/stops/all'))
    assert {'stop_id': 'A', 'name': 'Alpha', 'lat': 28.6, 'lon': 77.2} in a and len(a) == 9
    assert [s['name'] for s in check(c.get('/stops', params={'q': 'bravo'}))][:1] == ['Bravo']
    assert len(check(c.get('/stops', params={'q': 'a'}))) <= 10


def test_journeys(c):
    r = check(c.get('/journeys', params={'from': 'A', 'to': 'D', 'depart': '2026-10-28T08:00', 'pref': 'fastest'}))
    assert len(r['options']) == 3 and r['query']['from_point']['name'] == 'Alpha'
    b = next(l for l in r['options'][0]['legs'] if l['mode'] == 'bus')
    assert {'route', 'dir', 'headsign', 'board', 'alight', 'depart', 'arrive', 'ride_min', 'crowding', 'segments',
            'stops'} <= set(b)
    assert {'level', 'p_seat', 'stand_min', 'crowded_between', 'text', 'confidence', 'n', 'range'} <= set(b['crowding'])
    assert r['notes'] and 'quiet_hour' in r and all('for' in s for s in r['suggestions'])
    r = check(c.get('/journeys', params={'from': '28.6,77.2', 'to': '28.66,77.2', 'depart': '2026-10-28T08:00'}))
    assert r['options'] and r['query']['pref'] == 'balanced'
    r = check(c.get('/journeys', params={'from': 'D', 'to': 'A', 'depart': '2026-10-28T08:00'}))
    assert r['options'] == [] and r['reason'] == 'no_route'
    assert check(c.get('/journeys', params={'from': 'A', 'to': 'D'}))['query']['depart']  # defaults to now


@pytest.mark.parametrize('q, status, code', [
    ({'from': 'A', 'to': 'A'}, 400, 'same_stop'),
    ({'from': '10,10', 'to': 'A'}, 422, 'outside_area'),
    ({'from': 'nowhere', 'to': 'A'}, 422, 'unknown_stop'),
    ({'from': 'A', 'to': 'D', 'pref': 'cheapest'}, 422, 'invalid_input'),
    ({'from': 'A', 'to': 'D', 'daytype': 'holiday'}, 422, 'invalid_input'),
    ({'from': 'A', 'to': 'D', 'depart': '28/10/2026 08:00'}, 422, 'invalid_input'),
    ({'from': 'A', 'to': 'D', 'depart': '2026-13-45T08:00'}, 422, 'bad_depart'),
    ({'from': 'A' * 65, 'to': 'D'}, 422, 'invalid_input'),
    ({'to': 'D'}, 422, 'invalid_input'),
])
def test_journeys_bad_input(c, q, status, code):
    r = c.get('/journeys', params=q)
    assert r.status_code == status and r.json()['detail']['code'] == code


def test_bad_input_elsewhere(c):
    for u in ['/stops?q=' + 'x' * 65, '/stops', '/crowding/heatmap?hour=24', '/crowding/heatmap?hour=-1',
              '/crowding/route/R1/UP?time=25:00', '/crowding/route/R1/SIDEWAYS', '/operator/top?period=noon',
              '/crowding/heatmap?daytype=monday']:
        r = c.get(u)
        assert r.status_code == 422 and r.json()['detail']['code'] == 'invalid_input', u
    assert c.get('/crowding/route/R9/UP').json()['detail']['code'] == 'unknown_route'


def test_route(c):
    r = check(c.get('/crowding/route/R1/UP', params={'daytype': 'weekday', 'time': '08:10'}))
    assert r['route'] == 'R1UP' and [(g['from'], g['to']) for g in r['segments']] == \
        [('Alpha', 'Bravo'), ('Bravo', 'Charlie'), ('Charlie', 'Delta')]
    g = r['segments'][0]
    assert g['level'] == 'FEW_SEATS_AVAILABLE' and g['p_seat'] == .9 and g['n'] == 20 and g['confidence'] == 'medium'
    assert g['L'] == 22.0 and g['L_low'] < g['L'] < g['L_high']
    assert r['segments'][2]['level'] == plan.NO and r['segments'][2]['n'] is None  # no cell published at slot 16
    r = check(c.get('/crowding/route/R2/UP', params={'time': '08:40'}))
    assert r['segments'][0]['reason'] == 'implausible' and r['segments'][0]['L'] is None


def test_heatmap(c):
    g = check(c.get('/crowding/heatmap', params={'daytype': 'weekday', 'hour': 8}))
    assert g['type'] == 'FeatureCollection'
    p = {(f['properties']['from'], f['properties']['to']): f['properties'] for f in g['features']}
    assert p[('Alpha', 'Bravo')]['routes'] == 2  # R1 and R2 share the stretch; R2's flagged slot is left out
    assert p[('Alpha', 'Bravo')]['LF'] == pytest.approx((.55 + 1.2 + .3) / 3, abs=.01)
    assert p[('Bravo', 'Delta')]['level'] == 'CRUSHED_STANDING_ROOM_ONLY'
    assert check(c.get('/crowding/heatmap', params={'hour': 3}))['features'] == []


def test_operator(c):
    r = check(c.get('/operator/top', params={'daytype': 'weekday', 'period': 'am'}))
    assert [x['route'] for x in r['rows']] == ['R2UP', 'R1UP']
    assert set(r['rows'][0]) == set(api.OPS)
    assert [x['route'] for x in check(c.get('/operator/top', params={'period': 'all'}))['rows']] == ['R2UP', 'R1UP', 'R3UP']
    assert check(c.get('/operator/top', params={'daytype': 'sunday'}))['rows'] == []


def test_coverage(c):
    r = check(c.get('/coverage'))
    assert r['match']['route_matched_pct'] == 95.0 and r['match']['rungs'] == {'rung_f': 3.1}
    assert r['gps']['route_check'] == {'ok': True} and r['gps']['overlap'] == {}


def test_privacy_scan_catches(c):
    assert private({'a': [{'vehicle_number': 1}], 'f': 2, 'by_series': {}}) == ['/a/vehicle_number', '/f', '/by_series']
    assert PLATE.search('bus DL1PD' + '1234 today') and PLATE.search('DL 51 EV ' + '0001') and not PLATE.search('DL51EV')


# ---------- gate G4 on the real outputs ----------

REAL = (OUT / 'cells.parquet').exists() and (OUT / 'operator.parquet').exists()


@pytest.fixture(scope='module')
def real():
    if not REAL:
        pytest.skip('needs data/out from the pipeline')
    mp, old = pytest.MonkeyPatch(), api.S.get('w')
    mp.setattr(api, 'build', BUILD)
    with TestClient(api.app) as x:
        yield x
    mp.undo()
    if old is not None:
        api.S['w'] = old


def stop(c, q):
    return check(c.get('/stops', params={'q': q}))[0]['stop_id']


@pytest.mark.parametrize('a, b, t', [('Anand Vihar ISBT', 'Connaught Place', '18:00'),
                                     ('Kashmere Gate ISBT', 'Nehru Place', '08:30')])
def test_g4_demo_queries(real, a, b, t):
    q = {'from': stop(real, a), 'to': stop(real, b), 'depart': f'2026-10-28T{t}', 'daytype': 'weekday'}
    ts = []
    for _ in range(3):
        s = time.time()
        r = check(real.get('/journeys', params=q))
        ts.append(time.time() - s)
    assert statistics.median(ts) < 2, ts
    assert 1 <= len(r['options']) <= 3 and len({o['id'] for o in r['options']}) == len(r['options'])
    for o in r['options']:
        assert o['crowding'] and all(l['crowding']['level'] in plan.LV for l in o['legs'] if l['mode'] == 'bus')
    assert r['quiet_hour'] and r['quiet_hour']['time'] == '11:00'


def test_real_privacy_scan(real):
    for u in ['/stops/all', '/stops?q=anand', '/coverage', '/operator/top?period=pm', '/crowding/heatmap?hour=18',
              '/crowding/route/425/UP?time=08:30']:
        check(real.get(u))
    assert 'route_matched_pct' in json.dumps(check(real.get('/coverage')))
