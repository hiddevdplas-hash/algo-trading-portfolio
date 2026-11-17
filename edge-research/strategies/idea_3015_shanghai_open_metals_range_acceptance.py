"""IDEA-3015: Shanghai-open metals range acceptance (card v1, ideas/cards/IDEA-3015-shanghai-open-metals-range-acceptance.md).

Rebuilt from the card's description of the idea source (TradingView "8PM (MGC 5M)" by Edge-Session); no code copied.
- m15 bars, UTC clock (Shanghai = UTC + 8, no DST). Decision days Monday-Friday UTC.
- Range: bars opening in [01:00 - R, 01:00) UTC; exactly R / 15 bars, first opening at 01:00 - R, last closing at 01:00. RH / RL.
- Entry window: bars opening in [01:00, 03:30) UTC. Long at bar j's close when the last K closes (all inside the window) are > RH;
  short when they are < RL. First trigger of the day only.
- Stop: max(close - RL + tick, 1.0 x ATR14) long; max(RH - close + tick, 1.0 x ATR14) short. ATR14 = simple mean true range, bars <= j.
- No target. Exit at the close of the bar ending at X minutes after 00:00 UTC; a signal on that bar itself is skipped.
params (card defaults): R = 60, K = 2, X = 210. Class A rules, news modes and caps are applied by the engine.
"""
import numpy as np

_DAY = 86_400_000
_MIN = 60_000
_OPEN = 60            # 01:00 UTC, minutes after midnight
_WIN_END = 210        # 03:30 UTC
_ATR_N = 14
_FLOOR = 1.0


def intents(bars, params, ctx):
    R = int(params.get("R", 60))
    K = int(params.get("K", 2))
    X = int(params.get("X", 210))
    tick = float(ctx.get("tick", 0.0) or 0.0)
    h = np.asarray(bars["h"], float)
    l = np.asarray(bars["l"], float)
    c = np.asarray(bars["c"], float)
    om = np.asarray(bars["open_ms"], np.int64)
    cm = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    side = np.zeros(n, np.int64)
    sl = np.full(n, np.nan)
    exl = np.zeros(n, bool)
    exs = np.zeros(n, bool)
    out = {"side": side, "sl_dist": sl, "exit_long": exl, "exit_short": exs}
    if n == 0:
        return out

    # ATR14: simple mean of true range over bars <= i (closed bars only)
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)
    cs = np.cumsum(np.r_[0.0, tr])
    atr = np.full(n, np.nan)
    if n >= _ATR_N:
        atr[_ATR_N - 1:] = (cs[_ATR_N:] - cs[:-_ATR_N]) / _ATR_N

    day = om // _DAY
    omin = (om % _DAY) // _MIN
    cday = cm // _DAY
    cmin = (cm % _DAY) // _MIN
    wday = (day + 3) % 7          # 1970-01-01 was a Thursday -> Monday = 0
    weekday = wday < 5

    # time exit at the close of the bar ending exactly at X (same UTC day as its open)
    at_x = weekday & (cmin == X) & (cday == day)
    exl[at_x] = True
    exs[at_x] = True

    first_ms = int(ctx["first_ms"])
    nr = R // 15
    win = weekday & (omin >= _OPEN) & (omin < _WIN_END)
    win_idx = np.flatnonzero(win)
    if win_idx.size == 0:
        return out
    days, starts = np.unique(day[win_idx], return_index=True)
    ends = np.r_[starts[1:], win_idx.size]
    t_open_ms = days * _DAY + _OPEN * _MIN

    for d, a, b, t0 in zip(days, starts, ends, t_open_ms):
        jj = win_idx[a:b]
        j0 = jj[0]
        # range bars: the nr bars immediately before the first window bar, which must open at 01:00
        if om[j0] != t0 or j0 < nr:
            continue
        rb = np.arange(j0 - nr, j0)
        if om[rb[0]] != t0 - R * _MIN or cm[rb[-1]] != t0:
            continue
        if np.any(np.diff(om[rb]) != 15 * _MIN):
            continue
        rh = float(h[rb].max())
        rl = float(l[rb].min())
        if not rh > rl:
            continue
        for k, j in enumerate(jj):
            if k + 1 < K:
                continue
            if at_x[j]:
                break                       # the exit bar: no entry on it, and none after it
            seq = jj[k + 1 - K:k + 1]
            if np.any(np.diff(om[seq]) != 15 * _MIN):
                continue
            a_ = atr[j]
            if not np.isfinite(a_):
                continue
            if np.all(c[seq] > rh):
                if om[j] >= first_ms:
                    side[j] = 1
                    sl[j] = max(c[j] - rl + tick, _FLOOR * a_)
                break
            if np.all(c[seq] < rl):
                if om[j] >= first_ms:
                    side[j] = -1
                    sl[j] = max(rh - c[j] + tick, _FLOOR * a_)
                break
    return out
