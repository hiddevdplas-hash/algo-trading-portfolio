"""IDEA-3013: US opening-range acceptance retest (card v1, ideas/cards/IDEA-3013-us-open-range-acceptance-retest.md).

Rebuilt from the card's description of the idea source (TradingView "Myth Busting E05 - ORB One-Candle Retest [PyneSys]" by PyneSys,
MPL-2.0); no code copied.
- m15 bars, NY clock. A day counts only if a bar opens at 09:30 and the opening range (bars opening in [09:30, 09:30 + R)) is complete.
  ORH / ORL = its high / low, W = ORH - ORL.
- Long side: armed by the first later bar closing above ORH (that bar never enters). After it, a bar closing <= ORH cancels the side for
  the day; the first bar with low <= ORH + tol x W, close > ORH and close > open buys at its close. Short side mirrors. Signals only on
  bars opening before 12:00 NY; at most one trade per side per day.
- Stop level: min(signal bar low, ORH - 0.25 x W) - 1 tick (long; mirror for short); target T x stop distance.
- Exit flag at the close of the bar ending 16:00 NY.
params (card defaults): R = 30, tol = 0.10, T = 2.0. Class A rules, news modes and caps are applied by the engine.
"""
import numpy as np

from engine.timeutil import local_ms

_TZ = "America/New_York"
_OPEN_MIN = 9 * 60 + 30
_LAST_SIG_MIN = 12 * 60
_CLOSE_MIN = 16 * 60
_B = 0.25
_DAY = 86_400_000
_MIN = 60_000


def intents(bars, params, ctx):
    R = int(params.get("R", 30))
    tol = float(params.get("tol", 0.10))
    T = float(params.get("T", 2.0))
    tick = float(ctx.get("tick", 0.0) or 0.0)
    o = np.asarray(bars["o"], float)
    h = np.asarray(bars["h"], float)
    l = np.asarray(bars["l"], float)
    c = np.asarray(bars["c"], float)
    om = np.asarray(bars["open_ms"], np.int64)
    cm = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    side = np.zeros(n, np.int64)
    sl = np.full(n, np.nan)
    tp = np.full(n, np.nan)
    exl = np.zeros(n, bool)
    exs = np.zeros(n, bool)
    out = {"side": side, "sl_dist": sl, "tp_dist": tp, "exit_long": exl, "exit_short": exs}
    if n == 0:
        return out

    lo = local_ms(om, _TZ)
    lday = lo // _DAY
    lmin = (lo % _DAY) // _MIN
    lcmin = (local_ms(cm, _TZ) % _DAY) // _MIN
    in_cash = (lmin >= _OPEN_MIN) & (lmin < _CLOSE_MIN)
    at_close = in_cash & (lcmin == _CLOSE_MIN)
    exl[at_close] = True
    exs[at_close] = True

    cash_idx = np.flatnonzero(in_cash)
    if cash_idx.size == 0:
        return out
    days, starts = np.unique(lday[cash_idx], return_index=True)
    ends = np.r_[starts[1:], cash_idx.size]
    first_ms = int(ctx["first_ms"])
    or_end = _OPEN_MIN + R

    for d, a, b in zip(days, starts, ends):
        ii = cash_idx[a:b]
        if lmin[ii[0]] != _OPEN_MIN:
            continue
        orb = ii[lmin[ii] < or_end]
        post = ii[(lmin[ii] >= or_end) & (lmin[ii] < _LAST_SIG_MIN)]
        if orb.size == 0 or post.size == 0 or lcmin[orb[-1]] != or_end:
            continue
        orh = float(h[orb].max())
        orl = float(l[orb].min())
        w = orh - orl
        if w <= 0:
            continue
        ls = 0   # long side: 0 waiting for a break, 1 broken (waiting for the retest), 2 done / cancelled
        ss = 0
        for j in post:
            if ls == 0:
                if c[j] > orh:
                    ls = 1
            elif ls == 1:
                if c[j] <= orh:
                    ls = 2
                elif l[j] <= orh + tol * w and c[j] > o[j]:
                    ls = 2
                    if om[j] >= first_ms:
                        lvl = min(l[j], orh - _B * w) - tick
                        side[j] = 1
                        sl[j] = c[j] - lvl
                        tp[j] = T * sl[j]
            if ss == 0:
                if c[j] < orl:
                    ss = 1
            elif ss == 1:
                if c[j] >= orl:
                    ss = 2
                elif h[j] >= orl - tol * w and c[j] < o[j]:
                    ss = 2
                    if om[j] >= first_ms and side[j] == 0:
                        lvl = max(h[j], orl + _B * w) + tick
                        side[j] = -1
                        sl[j] = lvl - c[j]
                        tp[j] = T * sl[j]
    return out
