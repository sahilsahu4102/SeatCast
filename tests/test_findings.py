import pandas as pd

from seatcast.findings import standees, tms_profile, tms_story


def toy():
    names = ['A', 'Maharani Bagh', 'Lajpat Nagar', 'AIIMS', 'x', 'Satya Niketan', 'Dhaula Kuan', 'y', 'COD Ring']
    flow = [1, 5, 6, 9, 7, 4, 5, 6, 7]  # per-slot f; each stretch is pooled over 3 slots in the cells
    rows = [('TMS(+)', 'UP', i, n, 'z', slot, 'weekday', v) for i, (n, v) in enumerate(zip(names, flow)) for slot in range(3)]
    rows += [('TMS(+)', 'UP', 0, 'A', 'z', 5, 'saturday', 99), ('TMS(-)', 'DOWN', 1, 'Maharani Bagh', 'z', 0, 'weekday', 99)]
    return pd.DataFrame(rows, columns=['base', 'dir', 'k', 'from_name', 'to_name', 'slot', 'daytype', 'f'])


def test_profile_is_weekday_up_only_and_undoes_slot_pooling():
    p = tms_profile(toy(), 10, {'slot_window': 1})
    assert list(p['k']) == list(range(9))
    assert p.loc[3, 'riders'] == 9 * 3 * 10 / 3  # f summed over 3 slots, divided by 3, times E


def test_story_finds_peak_low_and_rise():
    st = tms_story(tms_profile(toy(), 10, {'slot_window': 1}))
    assert st['pk_name'] == 'AIIMS' and st['lo_name'] == 'Satya Niketan'
    assert st['hi'] == 70 and st['lo_r'] == 40


def test_standees_with_near_zero_variation():
    assert standees(20, 39, 1e-12) == 0
    assert standees(45, 39, 1e-12) == 6
