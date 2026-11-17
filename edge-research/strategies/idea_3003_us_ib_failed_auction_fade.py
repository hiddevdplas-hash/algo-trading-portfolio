"""IDEA-3003: US initial-balance failed-auction fade (card v1, ideas/cards/IDEA-3003-us-ib-failed-auction-fade.md).

Rebuilt from the card's description of the idea source (TradingView "Initial Balance Auction Intelligence by DGT" by dgtrd); no code copied.
- m15 bars, NY clock. A day counts only if a bar opens at 09:30. IB = bars opening in [09:30, 09:30 + ib min); IBW = IBH - IBL.
- Test bar: the first bar after the IB (opening before 14:00 NY) whose high > IBH or low < IBL; only that bar decides the day.
- Failed above: high >= IBH + e x IBW, close < IBH, low >= IBL -> sell at its close; stop distance = high + 0.1 x IBW - close;
  target level IBH - f x IBW (skipped unless below the close). Failed below mirrors.
- Exit flag at the close of the bar ending 16:00 NY.
params (card defaults): ib = 60, e = 0.1, f = 0.5. Class A rules, news modes and caps are applied by the engine.
"""
import numpy as np

from engine.timeutil import local_ms

_TZ = "America/New_York"
_OPEN_MIN = 9 * 60 + 30
_LAST_TEST_MIN = 14 * 60
_CLOSE_MIN = 16 * 60
_BUF = 0.1
_DAY = 86_400_000
_MIN = 60_000


def intents(bars, params, ctx):
    ib = int(params.get("ib", 60))
    e = float(params.get("e", 0.1))
    f = float(params.get("f", 0.5))
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
    at_close = in_cash & (lcmin == _CLOSE_MIN)
    exl[at_close] = True
    exs[at_close] = True

    cash_idx = np.flatnonzero(in_cash)
    if cash_idx.size == 0:
        return out
    days, starts = np.unique(lday[cash_idx], return_index=True)
    ends = np.r_[starts[1:], cash_idx.size]
    first_ms = int(ctx["first_ms"])
    ib_end = _OPEN_MIN + ib

    for d, a, b in zip(days, starts, ends):
        ii = cash_idx[a:b]
        if lmin[ii[0]] != _OPEN_MIN:
            continue
        ib_bars = ii[lmin[ii] < ib_end]
        post = ii[(lmin[ii] >= ib_end) & (lmin[ii] < _LAST_TEST_MIN)]
        if ib_bars.size == 0 or post.size == 0:
            continue
        # the IB must be complete: its last bar must close at ib_end
        if lcmin[ib_bars[-1]] != ib_end:
            continue
        ibh = float(h[ib_bars].max())
        ibl = float(l[ib_bars].min())
        ibw = ibh - ibl
        if ibw <= 0:
            continue
        brk = post[(h[post] > ibh) | (l[post] < ibl)]
        if brk.size == 0:
            continue
        i = brk[0]
        if om[i] < first_ms:
            continue
        up = h[i] > ibh
        dn = l[i] < ibl
        if up and not dn and h[i] >= ibh + e * ibw and c[i] < ibh:
            tgt = ibh - f * ibw
            if tgt < c[i]:
                side[i] = -1
                sl[i] = h[i] + _BUF * ibw - c[i]
                tp[i] = c[i] - tgt
        elif dn and not up and l[i] <= ibl - e * ibw and c[i] > ibl:
            tgt = ibl + f * ibw
            if tgt > c[i]:
                side[i] = 1
                sl[i] = c[i] - (l[i] - _BUF * ibw)
                tp[i] = tgt - c[i]
    return out
