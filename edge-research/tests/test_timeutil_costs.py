"""Time zones (DST gap weeks) and cost arithmetic."""
from datetime import datetime, timezone

import numpy as np
import pytest

from engine import costs, timeutil


def ms(*a):
    return int(datetime(*a, tzinfo=timezone.utc).timestamp() * 1000)


def test_dst_gap_week_spring_2024():
    # US clocks moved 10 Mar 2024, EU 31 Mar 2024: in between, Amsterdam is NY + 5 h, otherwise NY + 6 h
    for t, gap in ((ms(2024, 3, 5, 12), 6), (ms(2024, 3, 20, 12), 5), (ms(2024, 4, 5, 12), 6),
                   (ms(2024, 10, 30, 12), 5), (ms(2024, 11, 5, 12), 6)):
        d = (timeutil.ams_offset_ms([t])[0] - timeutil.ny_offset_ms([t])[0]) / 3_600_000
        assert d == gap, (t, d)


def test_transition_hours_exact():
    # US spring forward 2024-03-10 07:00 UTC; EU 2024-03-31 01:00 UTC
    assert timeutil.ny_offset_ms([ms(2024, 3, 10, 6, 59)])[0] == -5 * 3_600_000
    assert timeutil.ny_offset_ms([ms(2024, 3, 10, 7, 0)])[0] == -4 * 3_600_000
    assert timeutil.ams_offset_ms([ms(2024, 3, 31, 0, 59)])[0] == 1 * 3_600_000
    assert timeutil.ams_offset_ms([ms(2024, 3, 31, 1, 0)])[0] == 2 * 3_600_000


def test_commission_px():
    c = {"symbols": {"EURUSD": {"ftmo": {"commission": {"type": "usd_per_lot_round_trip", "value": 5.0, "lot": 100000}},
                                "ic": {"commission": {"type": "usd_per_million_notional_side", "value": 30.0}}},
                     "USDJPY": {"ftmo": {"commission": {"type": "usd_per_lot_round_trip", "value": 5.0, "lot": 100000}}},
                     "XAUUSD": {"ftmo": {"commission": {"type": "pct_notional_round_trip", "value": 0.0027}}},
                     "US500": {"ftmo": {"commission": {"type": "none", "value": 0.0}}}}}
    assert costs.commission_px(c, "EURUSD", "ftmo", 1.12, 1.0) == pytest.approx(0.00005)          # 0.5 pip
    assert costs.commission_px(c, "EURUSD", "ic", 1.12, 1.0) == pytest.approx(6e-5 * 1.12)       # 0.67 pip
    assert costs.commission_px(c, "USDJPY", "ftmo", 1.0, 1 / 150) == pytest.approx(0.0075)       # 0.75 JPY pip
    assert costs.commission_px(c, "XAUUSD", "ftmo", 4000.0, 1.0) == pytest.approx(0.108)          # $10.8 per 100 oz
    assert costs.commission_px(c, "US500", "ftmo", 5000.0, 1.0) == 0.0


def test_swap_rate_model():
    c = {"symbols": {"EURUSD": {"ftmo": {"swap": {"model": "rate_gap", "base": "EUR", "quote": "USD",
                                                  "markup_long": 1.5, "markup_short": 1.4}}},
                     "XTIUSD": {"ftmo": {"swap": {"model": "fixed_pct", "long_pct": 3.0, "short_pct": -20.0}}}}}
    day = np.datetime64("2023-10-02")            # ECB deposit 4.00, Fed upper 5.50
    assert costs.swap_rate_pct(c, "EURUSD", "ftmo", "long", day) == pytest.approx(4.0 - 5.5 - 1.5)
    assert costs.swap_rate_pct(c, "EURUSD", "ftmo", "short", day) == pytest.approx(1.5 - 1.4)
    assert costs.swap_rate_pct(c, "XTIUSD", "ftmo", "short", day) == -20.0


def test_oil_positive_swap_capped_at_zero():
    # DESIGN A2: today's positive long oil swap is not applied; the negative side stays
    c = {"symbols": {"XBRUSD": {"ftmo": {"swap": {"model": "fixed_pct", "long_pct": 18.4, "short_pct": -84.9, "cap_positive": 0.0}}}}}
    day = np.datetime64("2016-02-01")
    assert costs.swap_rate_pct(c, "XBRUSD", "ftmo", "long", day) == 0.0
    assert costs.swap_rate_pct(c, "XBRUSD", "ftmo", "short", day) == -84.9


def test_engine_hash_stable():
    from engine.hash import engine_hash
    assert engine_hash() == engine_hash() and len(engine_hash()) == 12
