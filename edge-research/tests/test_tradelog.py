"""Trade log costs (DESIGN §4.3, §3.5): rollovers and the triple day, commission and spread lines, slippage near releases."""
from datetime import datetime, timezone

import numpy as np
import pytest

from engine import costs as C, tradelog as TL
from engine.data import FillTicks


def ms(*a):
    return int(datetime(*a, tzinfo=timezone.utc).timestamp() * 1000)


def test_rollovers_ny_17h_and_triple_day():
    wed = 2   # Monday = 0
    # Tue 10:00 UTC -> Thu 10:00 UTC (summer): rollovers Tue 21:00 UTC and Wed 21:00 UTC (triple) = 4 nights
    n, d = TL.rollovers([ms(2024, 7, 2, 10)], [ms(2024, 7, 4, 10)], wed)
    assert n[0] == 4 and [m for _, m in d[0]] == [1, 3]
    # Fri 20:00 UTC -> Mon 10:00 UTC in winter: Fri 22:00 UTC rollover only (weekend days have none)
    n, _ = TL.rollovers([ms(2024, 1, 5, 20)], [ms(2024, 1, 8, 10)], wed)
    assert n[0] == 1
    n, _ = TL.rollovers([ms(2024, 1, 5, 20)], [ms(2024, 1, 5, 21, 59)], wed)      # closed before 17:00 NY (22:00 UTC)
    assert n[0] == 0


def _ticks(t, bid, ask, half):
    t = np.asarray(t, np.int64); bid = np.asarray(bid, float); ask = np.asarray(ask, float)
    return FillTicks("EURUSD", "ftmo", t, bid, ask, (bid + ask) / 2, 0, 0, np.full(len(t), -1), None, None, np.asarray(half, float))


def _trade(entry_tick, exit_tick, t, side, entry_px, exit_px, risk, reason=1, otype=0):
    return {"bar": np.array([0]), "side": np.array([side]), "otype": np.array([otype]), "live_tick": np.array([entry_tick]),
            "entry_tick": np.array([entry_tick]), "entry_t": np.array([t[entry_tick]]), "exit_tick": np.array([exit_tick]),
            "exit_t": np.array([t[exit_tick]]), "exit_reason": np.array([reason]), "news_flags": np.array([0]),
            "entry_px": np.array([entry_px]), "sl0": np.array([entry_px - risk]), "tp": np.array([np.nan]), "risk": np.array([risk]),
            "exit_px": np.array([exit_px]), "sl_exit": np.array([entry_px - risk]), "mfe_r": np.array([0.0]), "mae_r": np.array([0.0]),
            "r_gross": np.array([(exit_px - entry_px) * side / risk])}


def test_costs_lines_eurusd():
    c = C.load()
    t = [ms(2024, 7, 2, 10), ms(2024, 7, 2, 11)]
    # FTMO ticks: IC spread 0.2 pip + add-on 0.4 pip (half 0.2 pip each side)
    tk = _ticks(t, [1.07996, 1.07996 + 0.0010], [1.08002, 1.08002 + 0.0010], [0.00002, 0.00002])
    tr = _trade(0, 1, tk.t, 1, 1.08002, 1.08096, 0.0010)
    log = TL.build(tr, tk, "EURUSD", c, context=False)
    assert log["r_mid"][0] == pytest.approx(1.0)
    assert log["r_spread_ftmo"][0] == pytest.approx(-0.06)                    # 0.6 pip paid on a 10-pip stop
    assert log["r_spread_ic"][0] == pytest.approx(-0.02)                      # without FTMO's 0.4 pip add-on
    assert log["r_comm_ftmo"][0] == pytest.approx(-0.05)                      # $5 per lot = 0.5 pip
    assert log["r_comm_ic"][0] == pytest.approx(-6e-5 * 1.08 / 0.0010, rel=1e-3)
    assert log["r_swap_ftmo"][0] == 0 and log["r_slip_ftmo"][0] == 0
    assert log["r_net_ftmo"][0] == pytest.approx(1.0 - 0.06 - 0.05)
    # a stop exit 1 min after a USD release pays one extra spread
    ev = [dict(start_ms=t[1] - 60_000, kind="release", tier=1, ccy="USD", type_id="US_CPI")]
    log = TL.build(tr, tk, "EURUSD", c, events=ev, context=False)
    assert log["r_slip_ftmo"][0] == pytest.approx(-0.06) and log["r_slip_ic"][0] == pytest.approx(-0.02) and log["news_day"][0]


def test_swap_sign_and_stress():
    c = C.load()
    t = [ms(2023, 10, 2, 10), ms(2023, 10, 3, 10)]          # one rollover (Mon), ECB 4.00 vs Fed 5.50
    tk = _ticks(t, [1.05, 1.05], [1.05, 1.05], [0, 0])
    tr = _trade(0, 1, tk.t, 1, 1.05, 1.05, 0.0050)
    log = TL.build(tr, tk, "EURUSD", c, context=False)
    rate = C.swap_rate_pct(c, "EURUSD", "ftmo", "long", np.array([np.datetime64("2023-10-02")]))[0]
    assert rate < 0 and log["r_swap_ftmo"][0] == pytest.approx(rate / 100 * 1.05 / 365 / 0.0050)
    log2 = TL.build(tr, tk, "EURUSD", c, context=False, swap_mult=1.5)
    assert log2["r_swap_ftmo"][0] == pytest.approx(1.5 * log["r_swap_ftmo"][0])
    trs = _trade(0, 1, tk.t, -1, 1.05, 1.05, 0.0050)
    pos = TL.build(trs, tk, "EURUSD", c, context=False)["r_swap_ftmo"][0]
    zero = TL.build(trs, tk, "EURUSD", c, context=False, zero_positive_swap=True)["r_swap_ftmo"][0]
    assert zero == min(pos, 0.0)
