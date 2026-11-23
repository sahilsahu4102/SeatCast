import datetime as dtm
import json
import math
import re
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Literal

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from seatcast import OUT, ROOT, cfg, plan
from seatcast.load import level

Day = Literal['weekday', 'saturday', 'sunday']
HHMM = r'^([01]\d|2[0-3]):[0-5]\d$'
PT = re.compile(r'^\s*(-?\d{1,3}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$')
IST = dtm.timezone(dtm.timedelta(hours=5, minutes=30))
HIDE = re.compile(r'vehicle|series|plate', re.I)  # coverage keys never served
S = {}


def build():
    W = plan.world()
    W.op = pd.read_parquet(OUT / 'operator.parquet')
    W.cov = {k: json.loads((OUT / f'{k}.json').read_text(encoding='utf-8')) if (OUT / f'{k}.json').exists() else {}
             for k in ['coverage', 'gps_checks']}
    return W


@asynccontextmanager
async def life(app):
    W = build()
    net = W.net
    pad = 5000 / 111320
    lon = pad / math.cos(math.radians(float(np.mean(net.lat))))
    W.box = (net.lat.min() - pad, net.lat.max() + pad, net.lon.min() - lon, net.lon.max() + lon)
    W.all = [{'stop_id': str(s), 'name': n, 'lat': round(float(a), 5), 'lon': round(float(b), 5)}
             for s, n, a, b in zip(net.stop_id, W.names, net.lat, net.lon)]
    S['w'] = W
    yield
    S.clear()


app = FastAPI(title='SeatCast Delhi', lifespan=life,
              description='Crowding-aware bus journeys for Delhi from pooled Oct 2026 app e-tickets.')
app.add_middleware(GZipMiddleware, minimum_size=1000)


def bad(status, code, msg):
    raise HTTPException(status, {'code': code, 'message': msg})


@app.exception_handler(RequestValidationError)
async def invalid(request, e):
    msg = '; '.join(f"{'.'.join(str(x) for x in r['loc'][1:])}: {r['msg']}" for r in e.errors())
    return JSONResponse({'detail': {'code': 'invalid_input', 'message': msg}}, status_code=422)


def where(W, s):
    m = PT.match(s)
    if m:
        a, b = float(m[1]), float(m[2])
        y0, y1, x0, x1 = W.box
        if not (y0 <= a <= y1 and x0 <= b <= x1):
            bad(422, 'outside_area', f'{s} is outside the Delhi bus network')
        return {'name': f'{a:.5f},{b:.5f}', 'lat': a, 'lon': b}
    i = W.sid.get(s.strip())
    if i is None:
        bad(422, 'unknown_stop', f'{s!r} is neither "lat,lng" nor a known stop_id')
    return {'name': W.names[i], 'lat': round(float(W.net.lat[i]), 6), 'lon': round(float(W.net.lon[i]), 6), 'stop_id': s.strip()}


@app.get('/health')
def health():
    return {'ok': True}


@app.get('/stops')
def stops(q: str = Query(min_length=1, max_length=64)):
    W = S['w']
    return [W.all[i] for i in plan.find(W, q, 10)]


@app.get('/stops/all')
def stops_all():
    return S['w'].all


@app.get('/journeys')
def journeys(frm: str = Query(alias='from', min_length=1, max_length=64), to: str = Query(min_length=1, max_length=64),
             depart: str | None = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$'),
             daytype: Day | None = None, pref: Literal['fastest', 'balanced', 'comfort'] = 'balanced'):
    W = S['w']
    try:
        t = dtm.datetime.strptime(depart, '%Y-%m-%dT%H:%M') if depart else dtm.datetime.now(IST).replace(tzinfo=None)
    except ValueError:
        bad(422, 'bad_depart', f'{depart} is not a valid date and time')
    a, b = where(W, frm), where(W, to)
    if frm.strip() == to.strip() or (a['lat'], a['lon']) == (b['lat'], b['lon']):
        bad(400, 'same_stop', 'from and to are the same place')
    return plan.plan(W, a, b, t, daytype, pref)


@app.get('/crowding/route/{base}/{dir}')
def route(base: str = Path(max_length=32, pattern=r'^[A-Za-z0-9()+\-_. ]+$'), dir: Literal['UP', 'DOWN', 'CW', 'CCW'] = Path(),
          daytype: Day = 'weekday', time: str = Query('08:00', pattern=HHMM)):
    W = S['w']
    C, net = W.cells, W.net
    ids = [r for r, (_, b, d) in W.routes.items() if b.upper() == base.upper() and d == dir]
    n = np.bincount(C.r, minlength=len(C.rid)) if len(C.r) else np.zeros(len(C.rid))
    ids = sorted(ids, key=lambda r: -n[C.rid[r]] if r in C.rid else 0)
    rp = None
    for r in ids:
        h = np.flatnonzero(net.pid == f'{r}:0')
        h = h if len(h) else np.flatnonzero(net.route == r)
        if len(h):
            rp = int(h[0])
            break
    if rp is None:
        bad(404, 'unknown_route', f'no route {base} {dir} in the timetable')
    r = str(net.route[rp])
    st = plan.pstops(net, rp, 0, net.pat_ptr[rp + 1] - net.pat_ptr[rp] - 1)
    sl = (int(time[:2]) * 60 + int(time[3:])) // cfg()['slot_min']
    i = C.find(r, st[:-1], st[1:], daytype, np.full(len(st) - 1, sl))
    why = C.get('why', i, 3)
    segs = []
    for k, x in enumerate(i):
        g = {'k': k, 'from': W.names[st[k]], 'to': W.names[st[k + 1]], 'L': None, 'L_low': None, 'L_high': None,
             'LF': None, 'level': plan.NO, 'p_seat': None, 'confidence': None, 'n': None}
        if x >= 0:
            g['n'] = int(C.n[x])
        if why[k] == 0:
            g.update({c: plan.rnd(getattr(C, c)[x], 1) for c in ['L', 'L_low', 'L_high']})
            g.update(LF=plan.rnd(C.LF[x]), level=plan.LV[C.lv[x]], p_seat=plan.rnd(C.p_seat[x]),
                     confidence=plan.CONF[C.conf[x]])
        else:
            g['reason'] = plan.WHY[why[k]]
        segs.append(g)
    m = W.routes[r]
    return {'route': m[0], 'base': m[1], 'dir': m[2], 'daytype': daytype, 'time': time,
            'variants': [W.routes[x][0] for x in ids], 'segments': segs}


@lru_cache(maxsize=96)
def heat(W, dt, h):
    # one line per stop pair: passengers over seats across every route's buses in the hour
    C, k = W.cells, cfg()
    m = (C.d == plan.DT.index(dt)) & (C.s // (60 // k['slot_min']) == h) & (C.why == 0)
    df = pd.DataFrame({'a': C.a[m], 'b': C.b[m], 'r': C.r[m], 'LN': C.L[m] * C.N_sched[m],
                       'SN': C.seats[m] * C.N_sched[m], 'TN': C.total[m] * C.N_sched[m]})
    g = df.groupby(['a', 'b']).agg(LN=('LN', 'sum'), SN=('SN', 'sum'), TN=('TN', 'sum'), routes=('r', 'nunique'))
    g = g[g['SN'] > 0]
    g['lv'] = level(g['LN'], g['SN'], g['TN'])
    shp = pairs(W)
    sid, net = W.net.stop_id, W.net
    out = []
    for (a, b), x in g.iterrows():
        line = shp.get((sid[a], sid[b])) or [[round(float(net.lon[a]), 5), round(float(net.lat[a]), 5)],
                                             [round(float(net.lon[b]), 5), round(float(net.lat[b]), 5)]]
        out.append({'type': 'Feature', 'geometry': {'type': 'LineString', 'coordinates': line},
                    'properties': {'from': W.names[a], 'to': W.names[b], 'LF': round(x['LN'] / x['SN'], 2),
                                   'level': x['lv'], 'routes': int(x['routes'])}})
    return {'type': 'FeatureCollection', 'features': out}


@lru_cache(maxsize=4)
def pairs(W):
    out = {}
    for (_, a, b), v in W.shapes.items():
        out.setdefault((a, b), v)
    return out


@app.get('/crowding/heatmap')
def heatmap(daytype: Day = 'weekday', hour: int = Query(8, ge=0, le=23)):
    return heat(S['w'], daytype, hour)


OPS = ['route', 'base', 'dir', 'daytype', 'hour', 'P_max', 'F_req', 'F_sched', 'gap', 'standee_min', 'plus1_benefit',
       'LF_max', 'max_from', 'max_to']


@app.get('/operator/top')
def top(daytype: Day = 'weekday', period: Literal['am', 'pm', 'all'] = 'all'):
    o = S['w'].op
    o = o[o['daytype'] == daytype]
    if period != 'all':
        a, b = cfg()['periods'][period]
        o = o[(o['hour'] >= a) & (o['hour'] < b)]
    o = o.nlargest(20, 'plus1_benefit')[OPS].round({'P_max': 0, 'F_sched': 1, 'gap': 1, 'standee_min': 0,
                                                     'plus1_benefit': 0, 'LF_max': 2})
    return {'daytype': daytype, 'period': period, 'rows': json.loads(o.to_json(orient='records'))}


def clean(x):
    # coverage aggregates minus anything about vehicles; rung label f renamed so no field is called f
    if isinstance(x, dict):
        return {('rung_f' if k == 'f' else k): clean(v) for k, v in x.items() if not HIDE.search(k)}
    return [clean(v) for v in x] if isinstance(x, list) else x


@app.get('/coverage')
def coverage():
    c = S['w'].cov
    return clean({**c['coverage'], 'gps': c['gps_checks'], 'notes': [plan.NOTE]})


def serve():
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8000)


app.mount('/', StaticFiles(directory=ROOT / 'web', html=True), name='web')
