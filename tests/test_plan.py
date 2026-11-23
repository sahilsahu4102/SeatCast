import datetime as dtm
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from seatcast import plan, raptor

TOY = Path(__file__).parent / 'fixtures' / 'toy_net'
H = 3600
M, F, S, X, NO = plan.LV
# route, from, to, slot, p_seat, LF, level[, flag]. Seats 40, total 60. The R1 08:00 bus is seated but busy on A-C;
# the R2 + R3 transfer is faster and packed; the R1 08:30 bus is emptier.
CELLS = [('R1', 'A', 'B', 16, .9, .55, F), ('R1', 'B', 'C', 16, .6, .9, F), ('R1', 'C', 'D', 17, .9, .3, M),
         ('R1', 'A', 'B', 17, .9, .3, M), ('R1', 'B', 'C', 17, .9, .3, M),
         ('R2', 'A', 'B', 16, 0, 1.2, S), ('R3', 'B', 'D', 16, 0, 1.6, X),
         ('R2', 'A', 'B', 17, np.nan, np.nan, NO, 'absurd')]


def cells_df(rows=CELLS):
    out = []
    for r, a, b, s, p, lf, lv, *fl in rows:
        out.append({'route_id': r, 'from_stop': a, 'to_stop': b, 'slot': s, 'daytype': 'weekday', 'n': 20.0, 'N_sched': 2.0,
                    'L_low': lf * 28, 'L': lf * 40, 'L_high': lf * 44, 'LF': lf, 'p_seat': p, 'level_low': lv,
                    'level': lv, 'level_high': lv, 'flag': fl[0] if fl else None,
                    'confidence': None if fl else 'medium', 'seats': 40.0, 'total': 60.0,
                    'f': 1.0, 'scale': 1.0, 'ndata': 3})
    return pd.DataFrame(out)


def toy(w):
    net = raptor.load(TOY, rebuild=True, w=w)
    return plan.World(net, plan.Cells(cells_df(), net), plan.route_meta(TOY), plan.headsigns(TOY))


@pytest.fixture(scope='module')
def W(tmp_path_factory):
    return toy(tmp_path_factory.mktemp('work'))


def pt(W, s):
    i = W.sid[s]
    return {'name': W.names[i], 'lat': float(W.net.lat[i]), 'lon': float(W.net.lon[i])}


def go(W, a='A', b='D', t=dtm.datetime(2026, 10, 28, 8, 0), pref='balanced', dt=None):
    return plan.plan(W, pt(W, a), pt(W, b), t, dt, pref)


def ix(W, s):
    return W.sid[s]


def leg(W, a, b, t, ban=()):
    j = raptor.query(W.net, [(ix(W, a), 0)], [(ix(W, b), 0)], t, 'weekday', ban=ban)
    return next(l for l in j[0]['legs'] if l['mode'] == 'bus')


def routes(o):
    return [l['route'] for l in o['legs'] if l['mode'] == 'bus']


def test_cells_lookup(W):
    C = W.cells
    a, b = [ix(W, 'A'), ix(W, 'B')], [ix(W, 'B'), ix(W, 'C')]
    i = C.find('R1', a, b, 'weekday', [16, 16])
    assert (i >= 0).all() and C.p_seat[i].round(2).tolist() == [.9, .6]
    assert C.find('R1', a, b, 'sunday', [16, 16]).tolist() == [-1, -1]
    assert C.find('NOPE', a, b, 'weekday', [16, 16]).tolist() == [-1, -1]
    assert not hasattr(C, 'f') and not hasattr(C, 'scale') and not hasattr(C, 'ndata')


def test_crowding_per_leg(W):
    c, segs, mins, mult = plan.crowd(W, leg(W, 'A', 'D', 8 * H, ban={'R2'}), 'weekday')  # R1 08:00
    assert [g['level'] for g in segs] == [F, F, M] and [g['min'] for g in segs] == [20, 20, 20]
    assert c['level'] == F and c['p_seat'] == .9 and c['crowded_between'] is None
    assert c['stand_min'] == pytest.approx(6.0)  # seat kept once found: 3 x 20 min x (1 - 0.9)
    assert c['text'] == 'Seats on 9 of 10 trips' and c['confidence'] == 'medium' and c['n'] == 20
    assert c['range'] == [F, F]
    c, segs, *_ = plan.crowd(W, leg(W, 'B', 'D', 8 * H), 'weekday')  # R3, packed
    assert c['level'] == X and c['crowded_between'] == ['Bravo', 'Delta']
    assert c['text'] == 'Seat unlikely at boarding (0 of 10 trips) · crowded Bravo to Delta' and c['stand_min'] == 20


def test_partial_and_missing_data(W):
    c, segs, *_ = plan.crowd(W, leg(W, 'A', 'D', 8 * H + 1800), 'weekday')  # R1 08:30: C-D slot 18 not published
    assert c['level'] == M and [g['level'] for g in segs] == [M, M, NO] and segs[2]['n'] is None
    c, *_ = plan.crowd(W, leg(W, 'A', 'D', 24 * H + 1200), 'weekday')  # 24:30: nothing published
    assert c['level'] == NO and c['reason'] == 'low_n' and c['p_seat'] is None and c['text'] == 'Limited data'
    l = dict(leg(W, 'A', 'B', 8 * H), times=[8 * H + 1800, 8 * H + 2100], dep=8 * H + 1800, arr=8 * H + 2100)
    c, *_ = plan.crowd(W, l, 'weekday')  # R2 at slot 17 is flagged absurd
    assert c['level'] == NO and c['reason'] == 'implausible'


def test_gt_ranking_flips(W):
    f, c, b = go(W, pref='fastest'), go(W, pref='comfort'), go(W, pref='balanced')
    # the 08:30 R1 is no calmer than the 08:00 R1 (seat chance not +0.2), so it is not offered as a third option
    assert [routes(o) for o in f['options']] == [['R2', 'R3'], ['R1']]
    assert [o['depart'] for o in f['options']] == ['08:05', '08:00']
    assert routes(c['options'][0]) == ['R1'] and c['options'][0]['depart'] == '08:00'
    assert routes(b['options'][0]) == ['R2', 'R3']
    gt = [o['generalised_min'] for o in c['options']]
    assert gt == sorted(gt)
    lab = {o['id']: o['label'] for o in c['options']}
    assert sorted(lab.values()) == ['comfort', 'fastest']
    assert lab[f['options'][0]['id']] == 'fastest'
    assert len({o['id'] for o in f['options']}) == 2 and {o['id'] for o in f['options']} == set(lab)


def test_option_shape(W):
    r = go(W)
    o = next(o for o in r['options'] if routes(o) == ['R2', 'R3'])
    assert o['transfers'] == 1 and o['total_min'] == 30 and o['arrive'] == '08:35'
    assert o['crowding']['level'] == X and o['crowding']['p_seat'] == 0
    b = [l for l in o['legs'] if l['mode'] == 'bus']
    assert [l['dir'] for l in b] == ['UP', 'UP'] and b[0]['headsign'] == 'Bravo' and b[0]['arrive'] == '08:10'
    assert [s['name'] for s in b[1]['stops']] == ['Bravo', 'Delta']
    assert r['query']['from_point']['name'] == 'Alpha' and r['query']['daytype'] == 'weekday'
    assert r['quiet_hour'] is None or r['quiet_hour']['time'] == '11:00'
    assert not any(k.startswith('_') for o in r['options'] for k in o)


def test_leave_later(W):
    r = go(W, pref='comfort')
    o = r['options'][0]
    s = [x for x in r['suggestions'] if x['type'] == 'leave_later']
    assert s == [{'type': 'leave_later', 'for': o['id'], 'depart': '08:30', 'p_seat': .9, 'extra_min': 30, 'level': M,
                  'route': 'R1'}]


def opt(dep, arr, p, lv, r='R1', gt=0, conf='medium', n=20):
    c = {'level': lv, 'p_seat': p, 'confidence': conf, 'n': n}
    return {'id': f'{r}{dep}', '_dep': dep, '_arr': arr, '_seq': (r,), '_gt': gt, '_gth': gt, 'transfers': 0, 'depart': plan.hm(dep),
            'crowding': c, 'legs': [{'mode': 'bus', 'route': r, 'crowding': c}]}


def test_leave_later_rules():
    o, a = opt, opt(0, 3000, .5, S)
    assert plan.leave_later(a, [o(600, 3600, .7, S)])['depart'] == '00:10'           # p rises by 0.2
    assert plan.leave_later(a, [o(600, 3600, .6, F)])['level'] == F                  # level drops a step
    assert plan.leave_later(a, [o(600, 3600, .6, S)]) is None                        # neither
    assert plan.leave_later(a, [o(600, 3000 + 1860, .9, M)]) is None                 # > 30 min later arrival
    assert plan.leave_later(a, [o(-60, 2900, .9, M)]) is None                        # leaves earlier
    assert plan.leave_later(a, [o(540, 3000, .9, M)]) is None                        # under one 10 min step later
    s = plan.leave_later(a, [o(600, 3600, .9, M, 'R9')])                             # another route counts
    assert (s['route'], s['extra_min'], s['for']) == ('R9', 10, a['id'])
    s = plan.leave_later(a, [o(600, 3600, .7, S), o(1200, 4200, .8, F), o(1800, 4800, .9, F, 'R9')])
    assert (s['depart'], s['level'], s['p_seat']) == ('00:30', F, .9)                # calmest, then best seat
    seated = opt(0, 3000, .9, S)
    assert plan.leave_later(seated, [o(600, 3600, 1.0, X)]) is None                  # a seat in a crushed bus
    assert plan.leave_later(opt(0, 3000, None, NO), [o(600, 3600, .9, M)]) is None   # nothing to compare
    assert plan.leave_later(opt(0, 3000, .9, NO), [o(600, 3600, 1.0, M)]) is None


def test_confidence_tie_break():
    lo, hi = opt(0, 3000, .5, S, 'L', gt=50, conf='low', n=10), opt(0, 3100, .5, S, 'H', gt=52.9, conf='high', n=300)
    assert [x['id'] for x in plan.rank([lo, hi], 'comfort')] == ['H0', 'L0']
    hi['_gt'] = hi['_gth'] = 53.1
    assert [x['id'] for x in plan.rank([lo, hi], 'comfort')] == ['L0', 'H0']                # beyond 3 min: GT wins
    a, b = opt(0, 3000, .5, S, 'A', gt=50, n=10), opt(0, 3100, .5, S, 'B', gt=51, n=40)
    assert [x['id'] for x in plan.rank([a, b], 'balanced')] == ['B0', 'A0']                 # same confidence: larger n
    assert [x['id'] for x in plan.rank([b, a], 'fastest')] == ['A0', 'B0']                  # fastest ignores it


def test_board_upstream(W):
    l = leg(W, 'B', 'D', 8 * H, ban={'R3'})  # R1 08:00 from Bravo: P(seat) 0.6; at Alpha 0.9
    j = {'legs': [{'mode': 'walk', 'from': None, 'to': l['board'], 'sec': 0}, l,
                  {'mode': 'walk', 'from': l['alight'], 'to': None, 'sec': 0}], 'arrive': l['arr'], 'dt': 'weekday', 'off': 0}
    o = plan.option(W, j, 8 * H)
    a = pt(W, 'A')
    s = plan.upstream(W, o, (a['lat'], a['lon']))
    assert s == {'type': 'board_upstream', 'for': o['id'], 'stop': 'Alpha', 'walk_min': 1, 'p_seat': .9, 'depart': '08:00'}
    b = pt(W, 'B')
    assert plan.upstream(W, o, (b['lat'], b['lon'])) is None  # Alpha is a 38 min walk from Bravo


def test_after_midnight_and_daytype(W):
    r = go(W, t=dtm.datetime(2026, 10, 29, 0, 20))  # yesterday's 24:30 trip still runs
    assert r['options'][0]['depart'] == '00:30' and r['options'][0]['arrive'] == '01:30'
    assert go(W, t=dtm.datetime(2026, 10, 2, 8, 0))['query']['daytype'] == 'sunday'  # Gandhi Jayanti
    assert go(W, t=dtm.datetime(2026, 10, 31, 8, 0))['query']['daytype'] == 'saturday'
    assert go(W, t=dtm.datetime(2026, 10, 31, 8, 0), dt='weekday')['query']['daytype'] == 'weekday'


def test_walk_only_and_no_route(W):
    a = pt(W, 'A')
    b = dict(a, name='near Alpha', lat=a['lat'] + .003)
    r = plan.plan(W, a, b, dtm.datetime(2026, 10, 28, 8, 0))
    assert [l['mode'] for o in r['options'] for l in o['legs']] == ['walk'] and r['options'][0]['crowding'] is None
    r = go(W, 'D', 'A')
    assert r['options'] == [] and r['reason'] == 'no_route'
    far = dict(a, lat=a['lat'] - .5)
    assert plan.plan(W, far, a, dtm.datetime(2026, 10, 28, 8, 0))['reason'] == 'no_stop_nearby'


def test_find_stops(W):
    assert W.names[plan.find(W, 'bravo')[0]] == 'Bravo'
    assert W.names[plan.find(W, 'foxtrot co')[0]] == 'Foxtrot & Co'
    assert plan.find(W, '   ') == []
    assert plan.point(W, 'delta')['name'] == 'Delta'
