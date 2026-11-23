import pytest

from seatcast.clean import norm


@pytest.mark.parametrize('s,e', [
    ('Sabha Pur X-Ing', 'sabha pur crossing'), ('Rohini Sec21', 'rohini sector 21'),
    ('Old Delhi Railway Station (T)', 'old delhi railway station terminal'),
    ('Kalindi Kunj Bdr', 'kalindi kunj border'),
    ('Rohini Sec 24 / Dear Satguru Sewaram Crossing&#34;', 'rohini sector 24 dear satguru sewaram crossing')])
def test_norm(s, e):
    assert norm(s) == e


def test_same():
    assert norm('Ito-Agcr') == norm('Ito Agcr')


def test_govt():
    assert norm('Govt. Press') == norm('Government Press') == 'government press'
