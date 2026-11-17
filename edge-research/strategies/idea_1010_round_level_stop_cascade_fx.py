"""IDEA-1010: stop-loss cascade through untouched round levels in London hours (card ideas/cards/IDEA-1010-round-level-stop-cascade-fx.md, v2).

m15 bars, London clock, Monday-Friday. At the close of each bar closing 08:00-16:00 London (inclusive): A = ATR(14) (Wilder, m15);
U / D = nearest 50-pip level above / below the close. A level is untouched if the London day's high so far < U (low so far > D),
counting every bar from 00:00 London up to and including this bar. If U - close <= A and U untouched: buy stop at U + b pips;
else if close - D <= A and D untouched: sell stop at D - b pips (both: the nearer; tie: none). Order lives until the next bar's
close (engine default). Stop = s * A; target = tp * stop; time exit 2 h after the fill.
params: b (2 pips), s (1.5), tp (1.5).
"""
import numpy as np

from engine.timeutil import local_ms

DEFAULTS = {"b": 2, "s": 1.5, "tp": 1.5}
PIP = {"EURUSD": 1e-4, "GBPUSD": 1e-4, "USDJPY": 1e-2}
STEP_PIPS = 50
MIN = 60_000
DAY = 86_400_000
FIRST, LAST = 8 * 60, 16 * 60      # bar close window, London minutes (inclusive)
HOLD = 2 * 60 * MIN
NEAR = 1.0                         # approach distance, x ATR


def _empty(n):
    return {"side": np.zeros(n, np.int64), "otype": np.zeros(n, np.int64), "price": np.full(n, np.nan),
            "sl_dist": np.full(n, np.nan), "tp_dist": np.full(n, np.nan), "expiry_ms": np.full(n, np.nan),
            "hold_ms": np.full(n, np.nan)}


def _atr(h, l, c, n=14):
    """Wilder ATR, causal: value at i uses bars <= i; NaN until n true ranges exist."""
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    tr[0] = h[0] - l[0]
    out = np.full(len(c), np.nan)
    if len(c) >= n:
        out[n - 1] = tr[:n].mean()
        for i in range(n, len(c)):
            out[i] = out[i - 1] + (tr[i] - out[i - 1]) / n
    return out


def intents(bars, params, ctx):
    p = {**DEFAULTS, **params}
    b, s, tp = float(p["b"]), float(p["s"]), float(p["tp"])
    if ctx["symbol"] not in PIP:
        raise ValueError(f"IDEA-1010 trades {tuple(PIP)}, not {ctx['symbol']}")
    if ctx.get("timeframe") != "m15":
        raise ValueError(f"IDEA-1010 runs on m15 bars, not {ctx.get('timeframe')}")
    dg = int(ctx["digits"])
    pip = PIP[ctx["symbol"]]
    step = STEP_PIPS * pip
    h = np.asarray(bars["h"], float)
    l = np.asarray(bars["l"], float)
    c = np.asarray(bars["c"], float)
    oms = np.asarray(bars["open_ms"], np.int64)
    cms = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    out = _empty(n)
    if n == 0:
        return out
    atr = _atr(h, l, c)
    lo = local_ms(oms, "Europe/London")
    lc = local_ms(cms, "Europe/London")
    oday = lo // DAY                      # London day a bar belongs to (by its open)
    cday = lc // DAY
    cmin = (lc % DAY) // MIN
    day_hi = day_lo = np.nan
    cur = None
    for i in range(n):
        if oday[i] != cur:                # new London day: reset the running high / low (bars <= i only)
            cur = oday[i]
            day_hi, day_lo = h[i], l[i]
        else:
            day_hi, day_lo = max(day_hi, h[i]), min(day_lo, l[i])
        if not (FIRST <= cmin[i] <= LAST) or cday[i] != oday[i]:
            continue
        if ((int(cday[i]) + 3) % 7) >= 5 or oms[i] < ctx["first_ms"] or not np.isfinite(atr[i]):
            continue
        a = atr[i]
        up = round(step * np.ceil(c[i] / step), dg)      # v2: levels on the price grid, so an exact touch compares equal
        dn = round(step * np.floor(c[i] / step), dg)
        if up <= c[i]:
            up = round(up + step, dg)
        if dn >= c[i]:
            dn = round(dn - step, dg)
        du, dd = up - c[i], c[i] - dn
        buy = du <= NEAR * a and day_hi < up
        sell = dd <= NEAR * a and day_lo > dn
        if buy and sell:
            if du == dd:
                continue
            buy, sell = du < dd, dd < du
        if buy:
            out["side"][i] = 1
            out["price"][i] = up + b * pip
        elif sell:
            out["side"][i] = -1
            out["price"][i] = dn - b * pip
        else:
            continue
        out["otype"][i] = 1
        out["sl_dist"][i] = s * a
        out["tp_dist"][i] = tp * s * a
        out["hold_ms"][i] = HOLD
    return out
