"""Kernel unit tests (DESIGN §4.5 item 1): fills, gaps, stop-before-target, time exits, bar-close events, 1 R."""
import numpy as np
import pytest

from engine import kernel as K

MIN = 60_000


def ticks(rows):
    """rows: (t_ms, bid, ask)"""
    a = np.array(rows, dtype=float)
    return a[:, 0].astype(np.int64), a[:, 1], a[:, 2]


def mk(n_bars, i, side=1, **kw):
    """Intent arrays: one intent at bar i; a dict value {bar: x} sets per-bar arrays (trail / exit flags)."""
    out = {"side": np.zeros(n_bars, int)}
    out["side"][i] = side
    for k, v in kw.items():
        is_flag = k.startswith("exit")
        arr = np.zeros(n_bars, bool) if is_flag else np.full(n_bars, np.nan)
        for b, x in (v.items() if isinstance(v, dict) else [(i, v)]):
            arr[b] = x
        out[k] = np.nan_to_num(arr, nan=0).astype(int) if k == "otype" else arr
    return out


# bars: 1-minute bars opening at 0, 1, 2 ... minutes -> closes at 1, 2, 3 ... minutes
CLOSES = K.bar_closes(np.arange(10) * MIN, MIN)


def test_market_fills_at_first_tick_at_or_after_close():
    t, b, a = ticks([(59_999, 1.0000, 1.0002), (60_000, 1.0010, 1.0012), (60_500, 1.0020, 1.0022)])
    tr, c = K.run(t, b, a, CLOSES, **mk(10, 0, sl_dist=0.0050))
    assert tr["entry_tick"][0] == 1 and tr["entry_px"][0] == 1.0012          # buy at ask of the tick at the close
    assert tr["entry_t"][0] == 60_000


def test_sell_fills_at_bid_and_stop_on_ask():
    t, b, a = ticks([(60_000, 1.0000, 1.0002), (61_000, 1.0040, 1.0049), (62_000, 1.0050, 1.0052)])
    tr, _ = K.run(t, b, a, CLOSES, **mk(10, 0, side=-1, sl_dist=0.0050))
    assert tr["entry_px"][0] == 1.0000
    # stop = 1.0050; ask 1.0049 doesn't touch; ask 1.0052 crosses -> fills at 1.0052 (gap price)
    assert tr["exit_reason"][0] == 1 and tr["exit_px"][0] == 1.0052
    assert tr["r_gross"][0] == pytest.approx(-1.04)


def test_stop_gap_fills_at_gap_price_and_exact_touch_fills():
    t, b, a = ticks([(60_000, 1.0000, 1.0001), (61_000, 0.9960, 0.9961), (62_000, 0.9900, 0.9901)])
    tr, _ = K.run(t, b, a, CLOSES, **mk(10, 0, sl_dist=0.0041))     # stop 0.9960 -> exact touch on tick 1
    assert tr["exit_tick"][0] == 1 and tr["exit_px"][0] == 0.9960 and tr["exit_reason"][0] == 1
    tr, _ = K.run(t, b, a, CLOSES, **mk(10, 0, sl_dist=0.0030))     # stop 0.9971 -> tick 1 bid 0.9960 gaps through
    assert tr["exit_px"][0] == 0.9960 and tr["r_gross"][0] == pytest.approx(-0.0041 / 0.0030)


def test_target_fills_at_tick_price():
    t, b, a = ticks([(60_000, 1.0000, 1.0001), (61_000, 1.0019, 1.0020), (62_000, 1.0025, 1.0026)])
    tr, _ = K.run(t, b, a, CLOSES, **mk(10, 0, sl_dist=0.0010, tp_dist=0.0020))   # tp 1.0021
    assert tr["exit_reason"][0] == 2 and tr["exit_px"][0] == 1.0025
    assert tr["r_gross"][0] == pytest.approx(2.4)


def test_order_engine_before_bar_events():
    # long at 1.0001, tp 1.0011; bar 1 closes at 120_000 with a trail candidate of 1.0015 (above the target); the tick at
    # 120_000 (bid 1.0012) crosses the target: the order engine fills the target before the cBot's bar-close trail runs.
    # (In tick mode a stop and a target can't both be crossed by one tick: that needs stop >= target, and a trail can only
    # get there on a tick that already crossed the target. The stop is still checked first.)
    t, b, a = ticks([(60_000, 1.0000, 1.0001), (61_000, 1.0005, 1.0006), (120_000, 1.0012, 1.0013)])
    d = mk(10, 0, sl_dist=0.0010, tp_dist=0.0010, trail_long={1: 1.0015})
    tr, _ = K.run(t, b, a, CLOSES, **d)
    assert tr["exit_reason"][0] == 2 and tr["exit_px"][0] == 1.0012


def test_stop_entry_and_limit_entry():
    t, b, a = ticks([(60_000, 1.0000, 1.0001), (61_000, 1.0004, 1.0005), (62_000, 1.0010, 1.0011),
                     (63_000, 0.9990, 0.9991), (200_000, 0.9900, 0.9901)])
    d = mk(10, 0, otype=K.STOP, price=1.0008, sl_dist=0.0050)
    tr, _ = K.run(t, b, a, CLOSES, **d)
    assert tr["entry_tick"][0] == 2 and tr["entry_px"][0] == 1.0011             # gap past the level: tick's ask
    assert tr["sl0"][0] == pytest.approx(1.0011 - 0.0050)                       # stop around the actual fill
    d = mk(10, 0, otype=K.LIMIT, price=0.9995, sl_dist=0.0050)
    tr, _ = K.run(t, b, a, CLOSES, **d)
    assert tr["entry_tick"][0] == 3 and tr["entry_px"][0] == 0.9991


def test_pending_expiry_and_default_lifetime():
    t, b, a = ticks([(60_000, 1.0000, 1.0001), (61_000, 1.0004, 1.0005), (95_000, 1.0005, 1.0006), (125_000, 1.0020, 1.0021)])
    d = mk(10, 0, otype=K.STOP, price=1.0010, sl_dist=0.0050, expiry_ms=30_000)     # ends at 90_000: cancelled on the 95_000 tick
    tr, c = K.run(t, b, a, CLOSES, **d)
    assert len(tr["bar"]) == 0 and c["expired"] == 1
    d = mk(10, 0, otype=K.STOP, price=1.0010, sl_dist=0.0050, expiry_ms=100_000)
    tr, c = K.run(t, b, a, CLOSES, **d)
    assert tr["entry_tick"][0] == 3


def test_pending_can_fill_on_the_tick_that_ends_it():
    # no expiry: lives until the next bar's close (120_000). The first tick at or after it (125_000) is seen by the order engine
    # before the cBot cancels the order, so it fills there (cTrader-Bots/CONVENTIONS.md).
    t, b, a = ticks([(60_000, 1.0000, 1.0001), (61_000, 1.0004, 1.0005), (125_000, 1.0020, 1.0021)])
    tr, c = K.run(t, b, a, CLOSES, **mk(10, 0, otype=K.STOP, price=1.0010, sl_dist=0.0050))
    assert tr["entry_tick"][0] == 2 and tr["entry_px"][0] == 1.0021
    t, b, a = ticks([(60_000, 1.0000, 1.0001), (121_000, 1.0004, 1.0005), (125_000, 1.0020, 1.0021)])
    tr, c = K.run(t, b, a, CLOSES, **mk(10, 0, otype=K.STOP, price=1.0010, sl_dist=0.0050))
    assert len(tr["bar"]) == 0 and c["expired"] == 1


def test_crossed_pending_level_refused():
    t, b, a = ticks([(60_000, 1.0000, 1.0001), (61_000, 1.0004, 1.0005)])
    tr, c = K.run(t, b, a, CLOSES, **mk(10, 0, otype=K.STOP, price=1.0001, sl_dist=0.0050))   # ask already at the level
    assert len(tr["bar"]) == 0 and c["refused_crossed"] == 1
    tr, c = K.run(t, b, a, CLOSES, **mk(10, 0, side=-1, otype=K.LIMIT, price=0.9999, sl_dist=0.0050))  # bid above a sell limit
    assert len(tr["bar"]) == 0 and c["refused_crossed"] == 1


def test_exit_and_reverse_on_one_tick():
    t, b, a = ticks([(60_000, 1.0000, 1.0001), (150_000, 1.0010, 1.0011), (180_000, 1.0020, 1.0021), (190_000, 1.0030, 1.0031)])
    side = np.zeros(10, int); side[0] = 1; side[2] = -1
    ex = np.zeros(10, bool); ex[2] = True
    tr, c = K.run(t, b, a, CLOSES, side=side, sl_dist=np.full(10, 0.0050), exit_long=ex)
    assert len(tr["bar"]) == 2 and c["dropped_busy"] == 0
    assert tr["exit_reason"][0] == 4 and tr["exit_tick"][0] == 2 and tr["exit_px"][0] == 1.0020
    assert tr["side"][1] == -1 and tr["entry_tick"][1] == 2 and tr["entry_px"][1] == 1.0020


def test_stop_hit_on_a_bar_close_tick_lets_the_new_intent_in():
    t, b, a = ticks([(60_000, 1.0000, 1.0001), (180_000, 0.9940, 0.9941), (190_000, 0.9950, 0.9951)])
    side = np.zeros(10, int); side[[0, 2]] = 1
    tr, c = K.run(t, b, a, CLOSES, side=side, sl_dist=np.full(10, 0.0050))
    assert tr["exit_reason"][0] == 1 and tr["exit_tick"][0] == 1
    assert tr["entry_tick"][1] == 1 and tr["entry_px"][1] == 0.9941


def test_flat_on_the_fill_tick_closes_at_once():
    t, b, a = ticks([(60_000, 1.0000, 1.0001), (90_000, 1.0010, 1.0011), (95_000, 1.0012, 1.0013)])
    tr, c = K.run(t, b, a, CLOSES, flat_ms=[90_000], **mk(10, 0, otype=K.STOP, price=1.0005, sl_dist=0.0050))
    assert tr["entry_tick"][0] == 1 and tr["exit_tick"][0] == 1 and tr["exit_reason"][0] == 5


def test_trail_min_step_ignores_float_noise():
    t, b, a = ticks([(60_000, 1.0000, 1.0001), (120_000, 1.0005, 1.0006), (130_000, 0.9970, 0.9971)])
    sl0 = 1.0001 - 0.0020
    d = mk(10, 0, sl_dist=0.0020, trail_long={1: sl0 + 1e-12})
    tr, _ = K.run(t, b, a, CLOSES, min_step=0.000005, **d)
    assert tr["exit_reason"][0] == 1                                   # not counted as a trail
    tr, _ = K.run(t, b, a, CLOSES, **d)
    assert tr["exit_reason"][0] == 7


def test_no_bar_events_on_the_fill_tick():
    t, b, a = ticks([(60_000, 1.0000, 1.0001), (120_000, 1.0010, 1.0011), (150_000, 1.0006, 1.0007), (200_000, 1.0000, 1.0001)])
    d = mk(10, 0, otype=K.STOP, price=1.0008, sl_dist=0.0050, trail_long={1: 1.0007})
    tr, _ = K.run(t, b, a, CLOSES, **d)
    # filled on the bar-1 close tick: bar 1's trail (1.0007) is not applied, so 1.0006 at 150_000 does not stop it out
    assert tr["entry_tick"][0] == 1 and tr["exit_reason"][0] == 6


def test_time_exit():
    t, b, a = ticks([(60_000, 1.0000, 1.0001), (100_000, 1.0003, 1.0004), (120_000, 1.0004, 1.0005)])
    tr, _ = K.run(t, b, a, CLOSES, **mk(10, 0, sl_dist=0.0050, hold_ms=60_000))
    assert tr["exit_reason"][0] == 3 and tr["exit_tick"][0] == 2 and tr["exit_px"][0] == 1.0004


def test_exit_signal_only_for_positions_filled_before_that_close():
    t, b, a = ticks([(60_000, 1.0000, 1.0001), (119_000, 1.0002, 1.0003), (120_000, 1.0004, 1.0005),
                     (180_000, 1.0006, 1.0007)])
    d = mk(10, 0, sl_dist=0.0050, exit_long={0: True, 1: True})     # bar 0's flag closes before the fill: ignored
    tr, _ = K.run(t, b, a, CLOSES, **d)
    assert tr["exit_reason"][0] == 4 and tr["exit_tick"][0] == 2


def test_trail_tightens_only():
    t, b, a = ticks([(60_000, 1.0000, 1.0001), (120_000, 0.9985, 0.9986), (180_000, 0.9975, 0.9976)])
    d = mk(10, 0, sl_dist=0.0020, trail_long={1: 0.9950, 2: 0.9980})  # 0.9950 looser: ignored
    tr, _ = K.run(t, b, a, CLOSES, **d)
    assert tr["exit_reason"][0] == 1 and tr["exit_tick"][0] == 2       # original stop 0.9981 hit at 0.9975


def test_trailed_stop_already_beaten_closes_on_that_tick():
    t, b, a = ticks([(60_000, 1.0000, 1.0001), (120_000, 1.0010, 1.0011)])
    d = mk(10, 0, sl_dist=0.0020, trail_long={1: 1.0012})
    tr, _ = K.run(t, b, a, CLOSES, **d)
    assert tr["exit_reason"][0] == 7 and tr["exit_px"][0] == 1.0010 and tr["sl_exit"][0] == 1.0012


def test_flat_time_closes_and_cancels():
    t, b, a = ticks([(60_000, 1.0000, 1.0001), (90_000, 1.0003, 1.0004), (95_000, 1.0006, 1.0007)])
    tr, c = K.run(t, b, a, CLOSES, flat_ms=[90_000], **mk(10, 0, sl_dist=0.0050))
    assert tr["exit_reason"][0] == 5 and tr["exit_tick"][0] == 1
    d = mk(10, 0, otype=K.STOP, price=1.0005, sl_dist=0.0050)
    tr, c = K.run(t, b, a, CLOSES, flat_ms=[90_000], **d)
    assert len(tr["bar"]) == 0 and c["cancelled_flat"] == 1


def test_busy_drops_and_no_stop_refused():
    t, b, a = ticks([(60_000, 1.0000, 1.0001), (120_000, 1.0002, 1.0003), (180_000, 1.0004, 1.0005),
                     (240_000, 0.9900, 0.9901), (300_000, 0.9900, 0.9901)])
    side = np.zeros(10, int); side[[0, 1, 4]] = 1
    sl = np.full(10, 0.0050); sl[4] = np.nan
    tr, c = K.run(t, b, a, CLOSES, side=side, sl_dist=sl)
    assert len(tr["bar"]) == 1 and c["dropped_busy"] == 1 and c["refused_no_stop"] == 1
    assert tr["exit_tick"][0] == 3                                       # stopped at 240_000


def test_next_trade_can_start_after_exit_and_mfe_mae():
    t, b, a = ticks([(60_000, 1.0000, 1.0001), (70_000, 1.0011, 1.0012), (80_000, 0.9996, 0.9997),
                     (90_000, 0.9990, 0.9991), (120_000, 1.0000, 1.0001), (130_000, 1.0050, 1.0051)])
    side = np.zeros(10, int); side[[0, 1]] = 1
    tr, c = K.run(t, b, a, CLOSES, side=side, sl_dist=np.full(10, 0.0010), tp_dist=np.full(10, 0.0040))
    assert len(tr["bar"]) == 2
    assert tr["exit_reason"][0] == 1 and tr["exit_tick"][0] == 3
    assert tr["mfe_r"][0] == pytest.approx(1.0) and tr["mae_r"][0] == pytest.approx(-1.1)
    assert tr["exit_reason"][1] == 2 and tr["entry_tick"][1] == 4


def test_end_of_data_and_no_tick_after_close():
    t, b, a = ticks([(60_000, 1.0000, 1.0001), (61_000, 1.0003, 1.0004)])
    side = np.zeros(10, int); side[[0, 5]] = 1
    tr, c = K.run(t, b, a, CLOSES, side=side, sl_dist=np.full(10, 0.0050))
    assert tr["exit_reason"][0] == 6 and tr["exit_px"][0] == 1.0003 and c["no_tick_after_close"] == 1


def test_deterministic():
    rng = np.random.default_rng(7)
    n = 50_000
    t = np.cumsum(rng.integers(1, 2_000, n)).astype(np.int64)
    mid = 1.1 + np.cumsum(rng.normal(0, 1e-5, n))
    bid = np.round(mid, 5); ask = bid + 0.00002
    closes = K.bar_closes(np.arange(0, t[-1], MIN), MIN)
    side = rng.choice([-1, 0, 0, 0, 1], len(closes))
    kw = dict(side=side, sl_dist=np.full(len(closes), 0.0005), tp_dist=np.full(len(closes), 0.0010),
              hold_ms=np.full(len(closes), 30 * MIN))
    r1 = K.run(t, bid, ask, closes, **kw)
    r2 = K.run(t, bid, ask, closes, **kw)
    for k in r1[0]:
        assert np.array_equal(r1[0][k], r2[0][k], equal_nan=True)
    assert r1[1] == r2[1]
    # sanity: every trade's R is consistent with its prices
    tr = r1[0]
    assert np.allclose(tr["r_gross"], (tr["exit_px"] - tr["entry_px"]) * tr["side"] / tr["risk"])
    assert np.all(tr["exit_t"] >= tr["entry_t"]) and np.all(tr["entry_t"] >= closes[tr["bar"]])


def test_pip_size_levels_match_ctrader_exact_touch():
    # referee R1, 6 Feb 2024 (fill 1707213600238): short at 1.07291, stop distance 0.0011 -> cTrader stored 1.0740100000000001
    # (entry + (d / pip) * pip in raw doubles), so the ask of exactly 1.07401 did NOT fill it; 1.07405 six seconds later did
    entry, d, pip = 1.07291, 0.0011, 0.0001
    t, b, a = ticks([(60_000, 1.07291, 1.07291), (70_000, 1.07401, 1.07401), (80_000, 1.07405, 1.07405)])
    tr, _ = K.run(t, b, a, CLOSES, pip_size=pip, **mk(10, 0, side=-1, sl_dist=d))
    assert tr["sl0"][0] == 1.0740100000000001 and tr["exit_tick"][0] == 2 and tr["exit_px"][0] == 1.07405
