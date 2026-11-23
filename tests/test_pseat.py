import numpy as np
import pytest

from seatcast.load import level, p_seat


@pytest.mark.parametrize('m, want', [(20, 0.96), (35, 0.68), (45, 0.45), (60, 0.22)])
def test_sanity_values(m, want):
    assert p_seat(m, 39, 0.45) == pytest.approx(want, abs=0.01)


def test_empty_bus_and_vector():
    assert p_seat(0, 39, 0.45) == 1.0
    p = p_seat(np.array([0, 20, 60]), 39, 0.45)
    assert p[0] == 1.0 and p[1] > p[2]


def test_levels():
    L = np.array([10, 30, 50, 70, np.nan])
    assert list(level(L, 39, 63)) == ['MANY_SEATS_AVAILABLE', 'FEW_SEATS_AVAILABLE', 'STANDING_ROOM_ONLY',
                                      'CRUSHED_STANDING_ROOM_ONLY', None]
