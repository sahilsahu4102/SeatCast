from seatcast import cfg


def test_config():
    c = cfg()
    assert c['ridership_daily']['central'] < c['ridership_daily']['high']
    assert c['levels']['many'] < c['levels']['few']
    assert {'2026-10-02', '2026-10-20'} <= set(c['holidays'])
