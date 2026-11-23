import pytest

from seatcast.checks import fill as render, table


def test_render():
    v = {'a': {'b': 0.621, 'n': 2753606, 'l': [{'x': 3}]}}
    assert render('{{a.b:.0%}} of {{ a.n:, }} / {{a.l.0.x}}', v) == '62% of 2,753,606 / 3'
    with pytest.raises(KeyError):  # a missing number fails loudly
        render('{{a.missing}}', v)


def test_table():
    t = table([{'k': 'a', 'n': 1200}], [('rule', 'k'), ('tickets', 'n')], {'n': ','})
    assert t.splitlines() == ['| rule | tickets |', '|---|---|', '| a | 1,200 |']
