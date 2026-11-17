"""IDEA-3012: hour-open deviation fade in FX majors (card v1, ideas/cards/IDEA-3012-hour-open-deviation-fade-fx.md).

Rebuilt from the card's description of the idea source (TradingView "AlgoRover Bittern Hour-Open Maker Scalper v1.0.0 Visual" by
AlgoRover); no code copied.
- m15 bars. Anchor A = the open of the bar opening at minute 0 of the current UTC hour (the hour's open); a bar without that anchor
  bar inside the same hour decides nothing.
- D = mean true range of the last 96 completed m15 bars (bar i included, never later bars).
- Decisions only at the close of bars opening at minute 0, 15 or 30 of the hour (orders live until the next bar's close, so no order
  outlives its hour).
- Close >= A: sell LIMIT at P = A + k x D; close < A: buy LIMIT at P = A - k x D (one side per bar: the side price leans to).
  Skipped if the close is already beyond P (no chasing).
- Stop s x D from the fill; target = the hour's anchor (tp_dist = k x D); time exit H minutes after the fill.
params (card defaults): k = 2.0, s = 2.0, H = 120. Class A rules, news modes and caps are applied by the engine.
"""
import numpy as np

_HOUR = 3_600_000
_MIN = 60_000
_ND = 96


def intents(bars, params, ctx):
    k = float(params.get("k", 2.0))
    s = float(params.get("s", 2.0))
    hold = float(params.get("H", 120))
    o = np.asarray(bars["o"], float)
    h = np.asarray(bars["h"], float)
    l = np.asarray(bars["l"], float)
    c = np.asarray(bars["c"], float)
    om = np.asarray(bars["open_ms"], np.int64)
    n = len(c)
    side = np.zeros(n, np.int64)
    otype = np.zeros(n, np.int64)
    price = np.full(n, np.nan)
    sl = np.full(n, np.nan)
    tp = np.full(n, np.nan)
    hold_ms = np.full(n, np.nan)
    out = {"side": side, "otype": otype, "price": price, "sl_dist": sl, "tp_dist": tp, "hold_ms": hold_ms}
    if n <= _ND:
        return out

    # true range on closed bars; D[i] = mean of TR[i-95 .. i]
    tr = h - l
    tr[1:] = np.maximum(h[1:], c[:-1]) - np.minimum(l[1:], c[:-1])
    cs = np.r_[0.0, np.cumsum(tr)]
    D = np.full(n, np.nan)
    D[_ND - 1:] = (cs[_ND:] - cs[:-_ND]) / _ND

    hour = om // _HOUR
    minute = (om % _HOUR) // _MIN
    # anchor index: the latest bar at or before i that opens at minute 0
    is_anchor = minute == 0
    last_anchor = np.where(is_anchor, np.arange(n), -1)
    last_anchor = np.maximum.accumulate(last_anchor)

    first_ms = int(ctx["first_ms"])
    cand = np.flatnonzero((minute == 0) | (minute == 15) | (minute == 30))
    for i in cand:
        if om[i] < first_ms:
            continue
        a = last_anchor[i]
        if a < 0 or hour[a] != hour[i]:
            continue
        d = D[i]
        if not np.isfinite(d) or d <= 0:
            continue
        A = o[a]
        if c[i] >= A:
            P = A + k * d
            if c[i] >= P:
                continue
            side[i] = -1
        else:
            P = A - k * d
            if c[i] <= P:
                continue
            side[i] = 1
        otype[i] = 2
        price[i] = P
        sl[i] = s * d
        tp[i] = k * d
        hold_ms[i] = hold * _MIN
    return out
