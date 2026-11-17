"""Kernel rule mechanics (DESIGN §4.2, §3.6): entry blocks, news windows (flatten, far-stop, hold without target), day cap, order rate."""
import numpy as np

from engine import kernel as K
from tests.test_kernel import CLOSES, MIN, mk, ticks


def test_entry_block_drops_intent_and_cancels_pending():
    t, b, a = ticks([(60_000, 1.0000, 1.0001), (70_000, 1.0002, 1.0003), (90_000, 1.0004, 1.0005), (95_000, 1.0012, 1.0013)])
    tr, c = K.run(t, b, a, CLOSES, blk_start=[50_000], blk_end=[65_000], **mk(10, 0, sl_dist=0.0050))
    assert len(tr["bar"]) == 0 and c["blocked_entry"] == 1
    d = mk(10, 0, otype=K.STOP, price=1.0010, sl_dist=0.0050, expiry_ms=60_000)
    tr, c = K.run(t, b, a, CLOSES, blk_start=[90_000], blk_end=[100_000], **d)     # cancelled on the 90_000 tick, before the cross
    assert len(tr["bar"]) == 0 and c["cancelled_block"] == 1
    tr, c = K.run(t, b, a, CLOSES, blk_start=[92_000], blk_end=[100_000], **d)     # first tick past the block start crosses:
    assert tr["entry_tick"][0] == 3                                               # the order engine fills before the cancel


def test_news_flatten_without_far_stop():
    t, b, a = ticks([(60_000, 1.0000, 1.0001), (90_000, 1.0005, 1.0006), (100_000, 1.0004, 1.0005)])
    tr, c = K.run(t, b, a, CLOSES, win_start=[90_000], win_end=[120_000], win_kind=[1], **mk(10, 0, sl_dist=0.0050))
    assert tr["exit_reason"][0] == 8 and tr["exit_tick"][0] == 1 and tr["news_flags"][0] == 4 and c["news_flattened"] == 1


def test_far_stop_exemption_then_past_target_closes_after_window():
    # long 1.0001, stop 0.9951 (50 points), target 1.0011. Window 90_000-120_000 with far threshold 0.0040: at 90_000 the stop is
    # 1.0005 - 0.9951 = 0.0054 away > 0.0040 -> exempt; target removed (1.0015 inside the window doesn't fill); at 125_000 price is
    # past the target -> closed at market (reason 9).
    t, b, a = ticks([(60_000, 1.0000, 1.0001), (90_000, 1.0005, 1.0006), (100_000, 1.0015, 1.0016), (125_000, 1.0013, 1.0014)])
    kw = dict(win_start=[90_000], win_end=[120_000], win_kind=[1], win_far=[0.0040])
    tr, c = K.run(t, b, a, CLOSES, **kw, **mk(10, 0, sl_dist=0.0050, tp_dist=0.0010))
    assert tr["exit_reason"][0] == 9 and tr["exit_tick"][0] == 3 and tr["news_flags"][0] == 2 | 4 and c["far_stop_used"] == 1
    # same but price back below the target after the window: target restored, filled later
    t, b, a = ticks([(60_000, 1.0000, 1.0001), (90_000, 1.0005, 1.0006), (100_000, 1.0015, 1.0016), (125_000, 1.0008, 1.0009),
                     (130_000, 1.0012, 1.0013)])
    tr, c = K.run(t, b, a, CLOSES, **kw, **mk(10, 0, sl_dist=0.0050, tp_dist=0.0010))
    assert tr["exit_reason"][0] == 2 and tr["exit_tick"][0] == 4 and tr["tp"][0] == 1.0001 + 0.0010
    # far threshold not met -> flattened
    tr, c = K.run(t, b, a, CLOSES, win_start=[90_000], win_end=[120_000], win_kind=[1], win_far=[0.0060],
                  **mk(10, 0, sl_dist=0.0050, tp_dist=0.0010))
    assert tr["exit_reason"][0] == 8


def test_hold_without_target_keeps_stop_pauses_trail_defers_signal():
    t, b, a = ticks([(60_000, 1.0000, 1.0001), (90_000, 1.0005, 1.0006), (120_000, 1.0015, 1.0016), (150_000, 1.0006, 1.0007),
                     (185_000, 1.0004, 1.0005)])
    d = mk(10, 0, sl_dist=0.0050, tp_dist=0.0010, trail_long={1: 1.0010}, exit_long={1: True})
    tr, c = K.run(t, b, a, CLOSES, win_start=[90_000], win_end=[180_000], win_kind=[2], **d)
    # bar 1 closes at 120_000 inside the window: trail 1.0010 paused (else 1.0006 at 150_000 would stop it), exit deferred;
    # 1.0015 inside the window doesn't hit the removed target; window ends -> price 1.0004 not past target -> deferred signal exit
    assert tr["exit_reason"][0] == 4 and tr["exit_tick"][0] == 4 and tr["news_flags"][0] == 1 and c["news_held"] == 1
    # the stop still works inside a window
    t, b, a = ticks([(60_000, 1.0000, 1.0001), (90_000, 1.0005, 1.0006), (100_000, 0.9940, 0.9941)])
    tr, c = K.run(t, b, a, CLOSES, win_start=[90_000], win_end=[180_000], win_kind=[2], **mk(10, 0, sl_dist=0.0050))
    assert tr["exit_reason"][0] == 1 and tr["exit_tick"][0] == 2


def test_window_without_ticks_is_skipped():
    t, b, a = ticks([(60_000, 1.0000, 1.0001), (130_000, 1.0005, 1.0006), (200_000, 0.9940, 0.9941)])
    tr, c = K.run(t, b, a, CLOSES, win_start=[90_000], win_end=[120_000], win_kind=[1], **mk(10, 0, sl_dist=0.0050))
    assert tr["exit_reason"][0] == 1 and c["news_flattened"] == 0


def test_day_cap_and_order_rate():
    rows = [(m * MIN, 1.0000, 1.0001) for m in range(1, 12)]
    t, b, a = ticks(rows)
    closes = K.bar_closes(np.arange(12) * MIN, MIN)
    side = np.zeros(12, int); side[:10] = 1
    kw = dict(side=side, sl_dist=np.full(12, 0.0050), hold_ms=np.full(12, 1.0))   # each trade closes on the next tick
    tr, c = K.run(t, b, a, closes, day_start=[0], max_per_day=2, **kw)
    assert len(tr["bar"]) == 2 and c["dropped_day_cap"] > 0
    tr, c = K.run(t, b, a, closes, day_start=[0, 4 * MIN + 30_000], max_per_day=2, **kw)   # a new day lets two more in
    assert len(tr["bar"]) == 4
    # order rate: bars and ticks every 20 s, each trade exits on the next tick, where the next entry goes live. At 40 s the
    # window (-20 s, 40 s] holds the entry at 20 s and the exit at 40 s: a third event is dropped.
    t, b, a = ticks([(m * 20_000, 1.0000, 1.0001) for m in range(1, 12)])
    closes = K.bar_closes(np.arange(12) * 20_000, 20_000)
    tr, c = K.run(t, b, a, closes, max_orders_60s=2, **kw)
    assert c["dropped_order_rate"] > 0 and np.all(np.diff(tr["entry_t"]) >= 40_000)
    tr, c = K.run(t, b, a, closes, **kw)
    assert c["dropped_order_rate"] == 0 and len(tr["bar"]) == 10
