"""IDEA-3001: European cash-open breakaway gap (card v1, ideas/cards/IDEA-3001-eu-cash-open-breakaway-gap.md).

Rebuilt from the card's description of the idea source (TradingView "Gap Filling Strategy" by alexgrover, invert mode); no code copied.
- m15 bars, London clock. Cash session = bars with local open in [08:00, 16:30). A day counts only if its first cash bar opens at 08:00.
- PH / PL = high / low of the previous counted session; R20 = mean (high - low) of the previous 20 counted sessions.
- Up gap: open of the 08:00 bar > PH + g x R20 (down: < PL - g x R20). Hold test: the first w cash bars never trade back to PH (PL).
- Entry at the close of the w-th cash bar in the gap's direction; stop distance = close - PH + 0.1 x R20 (short: PL + 0.1 x R20 - close).
- Target t x stop distance when t > 0; exit flag at the close of the bar ending 16:30 London.
params (card defaults): g = 0.1, w = 2, t = 0. Class A rules, news modes and caps are applied by the engine.
"""
import numpy as np

from engine.timeutil import local_ms

_TZ = "Europe/London"
_OPEN_MIN = 8 * 60
_CLOSE_MIN = 16 * 60 + 30
_R_N = 20
_BUF = 0.1
_DAY = 86_400_000
_MIN = 60_000


def intents(bars, params, ctx):
    g = float(params.get("g", 0.1))
    w = int(params.get("w", 2))
    t = float(params.get("t", 0))
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
    lcm = local_ms(cm, _TZ)
    lcmin = (lcm % _DAY) // _MIN
    in_cash = (lmin >= _OPEN_MIN) & (lmin < _CLOSE_MIN)
    # exit flag at the close of the bar ending 16:30 London
    at_close = (lcmin == _CLOSE_MIN) & in_cash
    exl[at_close] = True
    exs[at_close] = True

    cash_idx = np.flatnonzero(in_cash)
    if cash_idx.size == 0:
        return out
    days, starts = np.unique(lday[cash_idx], return_index=True)
    ends = np.r_[starts[1:], cash_idx.size]

    first_ms = int(ctx["first_ms"])
    hist_ph, hist_pl, ranges = None, None, []
    for d, a, b in zip(days, starts, ends):
        ii = cash_idx[a:b]
        counted = lmin[ii[0]] == _OPEN_MIN
        if not counted:
            continue
        if hist_ph is not None and len(ranges) >= _R_N and len(ii) >= w:
            r20 = float(np.mean(ranges[-_R_N:]))
            op = o[ii[0]]
            ent = ii[w - 1]
            if r20 > 0 and om[ent] >= first_ms:
                if op > hist_ph + g * r20 and l[ii[:w]].min() > hist_ph:
                    dist = c[ent] - hist_ph + _BUF * r20
                    side[ent] = 1
                elif op < hist_pl - g * r20 and h[ii[:w]].max() < hist_pl:
                    dist = hist_pl + _BUF * r20 - c[ent]
                    side[ent] = -1
                else:
                    dist = np.nan
                if side[ent] != 0:
                    sl[ent] = dist
                    if t > 0:
                        tp[ent] = t * dist
        # this session becomes the "previous" one only once complete (used from the next day on)
        hist_ph = float(h[ii].max())
        hist_pl = float(l[ii].min())
        ranges.append(hist_ph - hist_pl)
    return out
