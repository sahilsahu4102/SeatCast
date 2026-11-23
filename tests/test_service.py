import pandas as pd

from seatcast import service


def stops(rows):
    st = pd.DataFrame(rows, columns=['trip_id', 'stop_id', 'dep'])
    st['stop_sequence'] = st.groupby('trip_id').cumcount()
    return st


H = 3600
ST = stops([('t1', 'A', 8 * H), ('t1', 'B', 8 * H + 300), ('t1', 'C', 8 * H + 600), ('t1', 'D', 8 * H + 900),
            ('t2', 'B', 8 * H + 600), ('t2', 'C', 8 * H + 840),
            ('t3', 'A', 8 * H + 2400), ('t3', 'B', 8 * H + 2700), ('t3', 'C', 8 * H + 3000), ('t3', 'D', 8 * H + 3300),
            ('t4', 'A', 24 * H + 600), ('t4', 'B', 24 * H + 900)])
TR = pd.DataFrame({'trip_id': ['t1', 't2', 't3', 't4'], 'route_id': 'R', 'service_id': '1'})
A = pd.DataFrame({'service_id': ['1'], 'daytype': ['weekday']})


def test_n_counts_every_pattern_on_the_segment():
    n = service.segs(ST, TR, A).set_index(['s0', 's1', 'slot'])
    assert n.loc[('B', 'C', 16), 'n'] == 2  # full trip t1 + short trip t2
    assert n.loc[('B', 'C', 17), 'n'] == 1
    assert n.loc[('B', 'C', 16), 'sec'] == 270  # median of 300 and 240
    assert n.loc[('A', 'B', 0), 'n'] == 1  # 24:10 runs in slot 0


def test_offsets_by_hour_and_all_day():
    tp = pd.DataFrame({'trip_id': ['t1', 't3'], 'pattern_id': 'R:0', 'first': [8 * H, 8 * H + 2400]})
    o = service.offsets(ST, tp).set_index(['k', 'h'])['cum']
    assert o.loc[(3, 8)] == 900 and o.loc[(3, -1)] == 900 and o.loc[(0, 8)] == 0
