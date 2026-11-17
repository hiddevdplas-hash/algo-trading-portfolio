"""Pipeline mechanics (DESIGN §6.3, §6.6, §6.6a, §6.7) on synthetic trade logs."""
import numpy as np
import pytest

from engine import pipeline as P
from engine.runner import shift_signals

DAY = 86_400_000


def mklog(entry_t, r, side=None, symbol="EURUSD", session="london", vol="mid", regime="range", gross=None, mid=None):
    n = len(r)
    e = np.asarray(entry_t, np.int64)
    return {"entry_t": e, "exit_t": e + 3_600_000, "side": np.asarray(side if side is not None else np.ones(n, int)),
            "r_gross": np.asarray(gross if gross is not None else r, float), "r_net_ftmo": np.asarray(r, float),
            "r_mid": np.asarray(mid if mid is not None else (gross if gross is not None else r), float),
            "r_net_ic": np.asarray(r, float), "symbol": np.array([symbol] * n), "session": np.array([session] * n),
            "vol_third": np.array([vol] * n), "regime": np.array([regime] * n), "bloc": np.array(["usd"] * n),
            "r_swap_ftmo": np.zeros(n), "news_flags": np.zeros(n, int)}


def spread_times(n, first="2014-11", last="2024-12"):
    return np.linspace(P.month_ms(first), P.month_ms(last, 1) - DAY, n).astype(np.int64)


def test_screen_zones():
    rng = np.random.default_rng(1)
    t = spread_times(400)
    green = mklog(t, rng.normal(0.25, 1.0, 400))
    assert P.screen_zone(green)["zone"] == "green"
    red = mklog(t, rng.normal(-0.2, 1.0, 400))
    assert P.screen_zone(red)["zone"] == "red"
    # costs eat an edge before costs: amber (DESIGN A11.1: judged at mid prices, not after the spread)
    g = rng.normal(0.15, 1.0, 400)
    amber = mklog(t, g - 0.2, gross=g - 0.1, mid=g)
    z = P.screen_zone(amber)
    assert z["zone"] == "amber" and z["t_mid"] >= 1.5 and z["t_gross"] < 1.5
    # t >= 1.5 after the spread but not at mid prices cannot happen for real costs; the rule reads r_mid only
    odd = mklog(t, g - 0.2, gross=g, mid=g - 0.3)
    assert P.screen_zone(odd)["zone"] == "red"
    # a synthetic strategy's planted edge is added to r_mid (the trade file leaves it out)
    flat = mklog(t, g - 0.4, gross=g - 0.2, mid=g - 0.15)
    assert P.screen_zone(flat)["zone"] == "red" and P.screen_zone(flat, edge_r=0.15)["zone"] == "amber"
    # one green slice (asia) inside a flat whole: amber via the slice
    r = np.r_[rng.normal(0.4, 1.0, 200), rng.normal(-0.5, 1.0, 200)]
    lg = mklog(t, r, gross=r - 1.0)
    lg["session"] = np.array(["asia"] * 200 + ["ny"] * 200)
    z = P.screen_zone(lg)
    assert z["zone"] == "amber" and "session=asia" in z["green_slices"]


def test_wf_select_and_stitch():
    # neighbourhood averages over a 1-D grid of 5: p3 (0.2) has the best neighbourhood (0.3, 0.2, 0.25 -> 0.25)
    t = spread_times(2000)
    logs = [{m: mklog(t, np.full(2000, v)) for m in ("M0", "M2", "M3")} for v in (-0.5, -0.5, 0.3, 0.2, 0.25)]
    ch = P.wf_select(logs, (5,), default=2)
    assert set(ch) == {3}
    st = P.wf_stitch(logs, ch, "M0")
    assert np.all(st["r_net_ftmo"] == 0.2) and st["entry_t"].min() >= P.month_ms("2016-11")
    # worst of modes: a point great in M0 but bad in M3 loses to a steady one
    logs2 = [{"M0": mklog(t, np.full(2000, 1.0)), "M2": mklog(t, np.full(2000, 1.0)), "M3": mklog(t, np.full(2000, -0.5))},
             {m: mklog(t, np.full(2000, 0.1)) for m in ("M0", "M2", "M3")}, {m: mklog(t, np.full(2000, 0.1)) for m in ("M0", "M2", "M3")}]
    assert set(P.wf_select(logs2, (3,), default=0)) == {2}
    # neighbourhood average beats a spike
    vals = (0.0, 0.0, 0.3, 0.0, 0.0, 0.15, 0.15, 0.15)
    logs3 = [{m: mklog(t, np.full(2000, v)) for m in ("M0", "M2", "M3")} for v in vals]
    assert set(P.wf_select(logs3, (8,), default=0)) == {6}
    # DESIGN A11.2: a training window without trades picks the card's default point, not grid point 0
    late = P.month_ms("2019-01")
    logs4 = [{m: mklog(t[t >= late], np.full(int((t >= late).sum()), v)) for m in ("M0", "M2", "M3")} for v in (0.5, 0.0, 0.0)]
    ch4 = P.wf_select(logs4, (3,), default=1)
    w = P.wf_windows()
    for (a, b, _), c in zip(w, ch4):
        assert c == (1 if b <= late else 0)                             # windows trained before 2019 have no trades at all
    with pytest.raises(TypeError):
        P.wf_select(logs4, (3,))                                        # the default must be stated
    with pytest.raises(ValueError):
        P.wf_select(logs4, (3,), default=3)


def test_g1_bars_and_near_miss():
    rng = np.random.default_rng(3)
    t = spread_times(600, first="2016-11")
    good = mklog(t, rng.normal(0.15, 0.5, 600))
    g = P.g1(good, k=None)
    assert g["pass"] and g["values"]["trades"] == 600
    few = P.take(good, np.arange(600) < 180)
    g = P.g1(few, k=None)
    assert g["failed"] == ["trades"] or "trades" in g["failed"]


def test_a9_drawdown_is_not_a_g1_bar():
    """DESIGN A9: a real edge with a deep drawdown passes G1; the drawdown is reported as each firm's fit risk."""
    rng = np.random.default_rng(11)
    n = 3000
    t = spread_times(n, first="2016-11")
    r = np.where(rng.random(n) < 0.36, 2.0, -1.0)                 # +0.08 R per trade, long losing runs: mc95 DD far above 9.3 R
    g = P.g1(mklog(t, r), k=None)
    mc = g["values"]["mc95_dd_r"]
    assert mc > P.dd_bar_r("FTMO")                                # it would have failed the pre-A9 bar
    assert g["pass"] and g["failed"] == [] and "mc95_dd" not in g["failed"]
    fr = g["fit_risk_pct"]["FTMO"]
    assert abs(fr - 7.0 / mc) < 1e-3 and fr < 0.75                # 70% of 10% max loss over the drawdown in R; below funded risk
    assert P.eligible_modes({"M1": g, "M2": g, "M3": g}) == ["M1", "M2", "M3"]
    # the bars that remain still fail, and a single near miss is still a near miss
    few = P.g1(mklog(t[:180], r[:180]), k=None)
    assert "trades" in few["failed"]
    assert P.fit_risk_pct(0.0) is None and P.fit_risk_pct(9.333) == round(7.0 / 9.333, 4)
    assert "mc95_dd" not in P.SAFETY


def test_g2_and_verdict():
    rng = np.random.default_rng(5)
    t = spread_times(600, first="2016-11")
    r = rng.normal(0.2, 0.5, 600)
    base = mklog(t, r, side=np.where(np.arange(600) % 2, 1, -1))
    same = {"noise": base, "cost": base}
    res = P.g2(base, "M3", "A", False, same, [base], lambda lg: P.g1(lg, k=None))
    assert res["pass"]
    half = mklog(t, r * 0.72, side=base["side"])                          # keeps 72% under noise: near miss (>= 70%)
    res = P.g2(base, "M3", "A", False, {"noise": half, "cost": base}, [base], lambda lg: P.g1(lg, k=None))
    assert res["failed"] == ["noise"] and P.verdict(P.g1(base, k=None), res) == "near_miss"
    bad_side = mklog(t, np.where(np.arange(600) % 2, 0.6, -0.2), side=base["side"])   # shorts lose 0.2 R a trade: safety fail
    res = P.g2(bad_side, "M3", "A", False, {"noise": bad_side, "cost": bad_side}, [bad_side], lambda lg: P.g1(lg, k=None))
    assert "short" in res["failed"] and P.verdict(P.g1(bad_side, k=None), res) == "fail"


def test_shift_signals_moves_entries_later_only():
    rng = np.random.default_rng(0)
    side = np.zeros(10, int); side[[2, 5, 9]] = [1, -1, 1]
    I = {"side": side, "sl_dist": np.where(side != 0, 0.01, np.nan), "exit_long": np.zeros(10, bool)}
    out = shift_signals(I, rng, 1)
    assert list(np.flatnonzero(out["side"])) == [3, 6] and list(out["side"][[3, 6]]) == [1, -1]   # A4.4; bar 9 falls off the end
    assert np.all(np.isfinite(out["sl_dist"][out["side"] != 0])) and out["exit_long"] is I["exit_long"]


def test_without_best_symbol_bar_and_single_symbol_label():
    rng = np.random.default_rng(9)
    t = spread_times(600, first="2016-11")
    r = np.abs(rng.normal(0.2, 0.3, 600))
    lg = mklog(t, r)
    lg["symbol"] = np.array(["EURUSD", "XAUUSD"] * 300)
    g = P.g2(lg, "M3", "A", False, {}, [], lambda x: P.g1(x, k=None), declared_symbols=["EURUSD", "XAUUSD"])
    assert g["tests"]["without_best_symbol"]["pass"] and g["labels"] == []
    lg2 = dict(lg, r_net_ftmo=np.where(lg["symbol"] == "EURUSD", -0.05, 0.5))           # one symbol carries it, the other loses
    g = P.g2(lg2, "M3", "A", False, {}, [], lambda x: P.g1(x, k=None), declared_symbols=["EURUSD", "XAUUSD"])
    assert "without_best_symbol" in g["failed"] and P.verdict(P.g1(lg2, k=None), g) == "fail"     # a safety bar: never a near miss
    one = mklog(t, r)
    g = P.g2(one, "M3", "A", False, {}, [], lambda x: P.g1(x, k=None), declared_symbols=["EURUSD"])
    assert "without_best_symbol" not in g["tests"] and g["labels"] == ["single symbol"]


def test_daily_sharpe_counts_weekend_exits_on_monday():
    """An exit at the Sunday-evening reopen (Amsterdam) is not dropped: it counts on the next Monday."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from engine import metrics as M
    A = ZoneInfo("Europe/Amsterdam")
    ms = lambda *a: int(datetime(*a, tzinfo=A).timestamp() * 1000)
    first, end = ms(2024, 1, 1), ms(2024, 2, 1)
    sun = ms(2024, 1, 7, 23, 5)                                   # Sunday 23:05, the FX reopen
    mon = ms(2024, 1, 8, 10, 0)
    base_t = np.array([ms(2024, 1, d, 12) for d in (2, 3, 4, 5, 9, 10, 11, 12)], np.int64)
    base_r = np.array([-1.0, 0.5, -0.2, 0.3, -0.4, 0.1, -0.3, 0.2])
    with_sun = M.daily_sharpe(np.r_[base_r, 2.0], np.r_[base_t, sun], first, end)
    with_mon = M.daily_sharpe(np.r_[base_r, 2.0], np.r_[base_t, mon], first, end)
    without = M.daily_sharpe(base_r, base_t, first, end)
    assert with_sun == with_mon and with_sun != without


def test_concat_ignores_empty_parts():
    t = spread_times(10)
    full = mklog(t, np.ones(10))
    empty = {"entry_t": np.zeros(0, np.int64), "exit_t": np.zeros(0, np.int64), "side": np.zeros(0, int), "r_net_ftmo": np.zeros(0)}
    c = P.concat([empty, full, empty])
    assert P.n_of(c) == 10 and "vol_third" in c and "session" in c
    assert P.n_of(P.concat([empty, empty])) == 0
