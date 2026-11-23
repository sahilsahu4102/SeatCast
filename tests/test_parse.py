import pytest

from seatcast.clean import parse_route


@pytest.mark.parametrize('c,e', [
    ('8UP', ('8', 'UP', '')), ('8ADOWN', ('8A', 'DOWN', '')), ('724BDOWN3', ('724B', 'DOWN', '3')),
    ('OMSEV(-)BH', ('OMSEVBH', 'CCW', '')), ('YMSMINUS', ('YMS', 'CCW', '')), ('D-7702UP', ('D-7702', 'UP', '')),
    ('D-5509(-)', ('D-5509', 'CCW', '')), ('DS CIRCULAR', None)])
def test_parse(c, e):
    assert parse_route(c) == e
