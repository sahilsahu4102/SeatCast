from datetime import datetime, timedelta

import duckdb
import pandas as pd
import pytest

from seatcast import checks


K = {'min_hw_s': 60, 'max_hw_s': 3600, 'ticket_window_s': 600, 'min_passes': 30, 'deciles': 10,
     'proportional_slope': [0.75, 1.25]}


def test_tickets_vs_headway_finds_proportional_toy():
    con = duckdb.connect()
    utc = datetime(2026, 10, 14, 4, 30)
    ticket_time = utc + timedelta(hours=5, minutes=30)
    tix, od, passes = [], [], []
    tid = 0
    pass_t = pd.Timestamp(utc, tz='UTC').timestamp()
    for i in range(1, 31):
        v = f'bus-{i}'
        hw = i * 100
        passes.append({'route_id': 7, 'stop_id': 's', 'v': v, 't': pass_t, 'hw': hw,
                       'daytype': 'weekday', 'band': 7})
        for _ in range(i):
            tid += 1
            tix.append({'tid': tid, 'v': v, 'pc': 1, 'ts': ticket_time})
            od.append({'tid': tid, 'route_id': 7})
    con.register('ticket_rows', pd.DataFrame(tix))
    con.register('ticket_routes', pd.DataFrame(od))

    r = checks.tickets_vs_headway(con, pd.DataFrame(passes), K)

    assert r['status'] == 'ok'
    assert r['finding'] == 'supports'
    assert r['passes_used'] == 30
    assert r['tickets_used'] == 465
    assert r['ticket_pass_matches'] == 465
    assert r['share_passes_with_ticket'] == 1
    assert r['slope'] == pytest.approx(1.0)
    assert len(r['deciles']) == 10
    assert all(x['mean_x'] == pytest.approx(x['mean_y']) for x in r['deciles'])
