import datetime as dt

import pandas as pd

from seatcast.clean import anomalies, daytype, fare_class


def test_fare_class():
    assert fare_class(9, True) == 'std' and fare_class(4.5, False) == 'std'
    assert fare_class(26.5, True) == 'ncr' and fare_class(10, True) == 'full'
    assert fare_class(0, True) == 'other' and fare_class(4.5, True) == 'other'


def test_daytype():
    assert daytype(dt.date(2026, 10, 2)) == 'sunday'
    assert daytype(dt.date(2026, 10, 20)) == 'sunday'
    assert daytype(dt.date(2026, 10, 3)) == 'saturday'
    assert daytype(dt.date(2026, 10, 4)) == 'sunday'
    assert daytype(dt.date(2026, 10, 7)) == 'weekday'


def test_anomalies():
    d = [dt.date(2026, 10, 5) + dt.timedelta(days=7 * i) for i in range(5)]
    a = anomalies(pd.DataFrame({'date': d, 'pax': [100, 100, 100, 100, 40]}))
    assert a['flag'].tolist() == [False] * 4 + [True]
