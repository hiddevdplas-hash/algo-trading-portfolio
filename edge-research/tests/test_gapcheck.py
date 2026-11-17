"""DESIGN A8.8 guard tool: break kinds and the flag on trades flattened before an unscheduled gap."""
from datetime import date, datetime

import numpy as np
from dateutil.easter import easter

from engine import rules as RU
from tools.gapcheck import unscheduled_flats as UF


def ams(*a):
    return int(datetime(*a, tzinfo=RU.AMS).timestamp() * 1000)


def test_easter_and_calendar():
    for y in range(2014, 2026):
        assert UF._easter(y) == easter(y)
    assert date(2024, 3, 29) in UF.HOLIDAYS and date(2024, 11, 28) in UF.HOLIDAYS and date(2024, 7, 4) in UF.HOLIDAYS


def test_break_kinds():
    assert UF.kind(ams(2024, 3, 15, 22, 0), ams(2024, 3, 17, 23, 0), False) == "weekend"
    assert UF.kind(ams(2024, 2, 6, 22, 0), ams(2024, 2, 7, 8, 0), True) == "regular"
    assert UF.kind(ams(2024, 12, 24, 19, 15), ams(2024, 12, 26, 0, 0), False) == "holiday"
    assert UF.kind(ams(2024, 7, 3, 19, 15), ams(2024, 7, 4, 0, 0), False) == "holiday"
    assert UF.kind(ams(2015, 4, 28, 2, 36), ams(2015, 4, 28, 8, 24), False) == "unscheduled"       # feed outage, a Tuesday


def test_flag_trades_at_unscheduled_flat():
    br = [(ams(2015, 4, 28, 2, 36), ams(2015, 4, 28, 8, 24), False),             # outage: flat 02:31
          (ams(2015, 4, 24, 22, 57), ams(2015, 4, 26, 23, 1), False),            # weekend
          (ams(2015, 4, 29, 18, 0), ams(2015, 4, 30, 4, 0), False)]              # unscheduled, flat 17:55
    w = UF.unscheduled_flat_windows(br)
    assert [tuple(x) for x in w] == [(ams(2015, 4, 28, 2, 31), ams(2015, 4, 28, 2, 36)), (ams(2015, 4, 29, 17, 55), ams(2015, 4, 29, 18, 0))]
    exit_t = [ams(2015, 4, 28, 2, 32), ams(2015, 4, 28, 2, 32), ams(2015, 4, 24, 22, 45), ams(2015, 4, 29, 17, 55), ams(2015, 4, 29, 18, 1)]
    name = np.array(["flat", "stop", "flat", "flat", "flat"])
    assert list(UF.flag(exit_t, name, w)) == [True, False, False, True, False]
