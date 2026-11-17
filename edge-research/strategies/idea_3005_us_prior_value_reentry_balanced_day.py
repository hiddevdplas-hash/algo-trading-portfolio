"""IDEA-3005: US index re-entry into the prior day's value area after a balanced day
(card v1, ideas/cards/IDEA-3005-us-prior-value-reentry-balanced-day.md).

Rebuilt from the card's description of the idea source (TradingView "Volume Profile Anatomies (D / B / P / Double Zone)" by
kingshukghosh71); no code copied.
- m15 bars, NY clock. Cash bars open 09:30 ... 15:45. A full session: first bar opens 09:30 and the last cash bar closes 16:00.
- Prior profile = the last earlier full session: 40 rows over [L, H]; each bar adds 1 / (rows overlapped) to each row it touches.
  POC = largest row (ties: nearest the middle); value area grows from the POC by the larger neighbour (ties: above) to >= 70%.
- Balanced if |p - 0.5| <= w, p = (POC row centre - L) / (H - L).
- Today (needs a 09:30 bar): O < VAL -> long setup, O > VAH -> short setup. The first bar opening 09:30 ... 12:45 that completes
  k consecutive closes inside [VAL, VAH] (counted from 09:30) enters at its close: long target VAH, stop VAL - s x VAW;
  short target VAL, stop VAH + s x VAW. No trade if the close is at or past the target. One trade a day.
- Exit flag at the close of the bar ending 16:00 NY.
params (card defaults): k = 4, w = 0.25, s = 0.25. Class A rules, news modes and caps are applied by the engine.
"""
import numpy as np

from engine.timeutil import local_ms

_TZ = "America/New_York"
_OPEN_MIN = 9 * 60 + 30
_CLOSE_MIN = 16 * 60
_LAST_ENTRY_OPEN_MIN = 12 * 60 + 45
_ROWS = 40
_VA_SHARE = 0.70
_DAY = 86_400_000
_MIN = 60_000


def _profile(h, l):
    """Time-at-price profile of one session's bars -> (VAL, VAH, p) or None."""
    lo = float(l.min())
    hi = float(h.max())
    rng = hi - lo
    if not rng > 0:
        return None
    step = rng / _ROWS
    cnt = np.zeros(_ROWS)
    for bh, bl in zip(h, l):
        a = int(np.floor((bl - lo) / step))
        b = int(np.floor((bh - lo) / step))
        a = min(max(a, 0), _ROWS - 1)
        b = min(max(b, 0), _ROWS - 1)
        cnt[a:b + 1] += 1.0 / (b - a + 1)
    centre = (np.arange(_ROWS) + 0.5) / _ROWS
    top = cnt.max()
    cand = np.flatnonzero(cnt == top)
    poc = int(cand[np.argmin(np.abs(centre[cand] - 0.5))])
    total = cnt.sum()
    lo_r = hi_r = poc
    acc = cnt[poc]
    while acc < _VA_SHARE * total and (lo_r > 0 or hi_r < _ROWS - 1):
        up = cnt[hi_r + 1] if hi_r < _ROWS - 1 else -1.0
        dn = cnt[lo_r - 1] if lo_r > 0 else -1.0
        if up >= dn:
            hi_r += 1
            acc += up
        else:
            lo_r -= 1
            acc += dn
    val = lo + lo_r * step
    vah = lo + (hi_r + 1) * step
    return val, vah, float(centre[poc])


def intents(bars, params, ctx):
    k = int(params.get("k", 4))
    w = float(params.get("w", 0.25))
    s = float(params.get("s", 0.25))
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

    prof = None  # profile of the last full session before the current day
    for d, a, b in zip(days, starts, ends):
        ii = cash_idx[a:b]
        opens_930 = lmin[ii[0]] == _OPEN_MIN
        full = opens_930 and lcmin[ii[-1]] == _CLOSE_MIN
        if opens_930 and prof is not None:
            val, vah, p = prof
            vaw = vah - val
            O = o[ii[0]]
            setup = 1 if O < val else (-1 if O > vah else 0)
            if setup != 0 and abs(p - 0.5) <= w and vaw > 0:
                run = 0
                for i in ii:
                    if lmin[i] > _LAST_ENTRY_OPEN_MIN:
                        break
                    run = run + 1 if (val <= c[i] <= vah) else 0
                    if run >= k:
                        if om[i] >= first_ms:
                            if setup == 1 and vah > c[i]:
                                side[i] = 1
                                sl[i] = c[i] - (val - s * vaw)
                                tp[i] = vah - c[i]
                            elif setup == -1 and val < c[i]:
                                side[i] = -1
                                sl[i] = (vah + s * vaw) - c[i]
                                tp[i] = c[i] - val
                        break
        if full:
            prof = _profile(h[ii], l[ii])
    return out
