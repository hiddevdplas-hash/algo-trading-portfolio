"""IDEA-1014: oil trend-follower flow after a fresh channel break (card ideas/cards/IDEA-1014-oil-cta-breakout-flow.md, v2).

h1 bars, New York clock. Daily price P = close of the h1 bar ending 15:00 New York for XTIUSD, 14:00 New York for XBRUSD (v2: XBRUSD
closes 16:58-16:59 New York, so its 15:00 entry fell in the engine's 2-h pre-close block; only days with that bar count).
Fresh upside break on day d: P_d > max(P over the previous N days) and P_prev <= max(P over the N days before P_prev);
downside the mirror with min. D = mean |P / P_prev - 1| over the previous 20 days (today excluded). Entry: market at that bar's
close in the break's direction, Monday-Thursday only, one a day. Stop s * D * close; no target; time exit H * 24 h after the fill
(the class B Friday flat is applied by the engine).
params: N (20), H (2), s (1.5).
"""
import numpy as np

from engine.timeutil import local_ms

DEFAULTS = {"N": 20, "H": 2, "s": 1.5}
SYMBOLS = ("XTIUSD", "XBRUSD")
ZONE = "America/New_York"
MIN = 60_000
DAY = 86_400_000
CLOCK = {"XTIUSD": 15 * 60, "XBRUSD": 14 * 60}   # bar close, New York minutes (v2: Brent one hour earlier)
VOL_DAYS = 20


def _empty(n):
    return {"side": np.zeros(n, np.int64), "otype": np.zeros(n, np.int64), "price": np.full(n, np.nan),
            "sl_dist": np.full(n, np.nan), "tp_dist": np.full(n, np.nan), "expiry_ms": np.full(n, np.nan),
            "hold_ms": np.full(n, np.nan)}


def intents(bars, params, ctx):
    p = {**DEFAULTS, **params}
    N, H, s = int(p["N"]), int(p["H"]), float(p["s"])
    if ctx["symbol"] not in SYMBOLS:
        raise ValueError(f"IDEA-1014 trades {SYMBOLS}, not {ctx['symbol']}")
    c = np.asarray(bars["c"], float)
    oms = np.asarray(bars["open_ms"], np.int64)
    cms = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    out = _empty(n)
    if n == 0:
        return out
    loc = local_ms(cms, ZONE)
    day, mnt = loc // DAY, (loc % DAY) // MIN
    idx = np.flatnonzero(mnt == CLOCK[ctx["symbol"]])       # one bar per New York day, in time order
    P = c[idx]
    for j in range(len(idx)):
        i = idx[j]
        if j < N + 1 or j < VOL_DAYS + 1:    # need P_prev's own N-day channel and 20 past returns
            continue
        wd = (int(day[i]) + 3) % 7           # 0 = Monday
        if wd > 3 or oms[i] < ctx["first_ms"]:
            continue
        hi_now, lo_now = P[j - N:j].max(), P[j - N:j].min()
        hi_prev, lo_prev = P[j - 1 - N:j - 1].max(), P[j - 1 - N:j - 1].min()
        up = P[j] > hi_now and P[j - 1] <= hi_prev
        dn = P[j] < lo_now and P[j - 1] >= lo_prev
        if not (up or dn):
            continue
        rets = np.abs(P[j - VOL_DAYS:j] / P[j - VOL_DAYS - 1:j - 1] - 1.0)   # the 20 returns ending at P_prev
        D = float(rets.mean())
        if D <= 0:
            continue
        out["side"][i] = 1 if up else -1
        out["sl_dist"][i] = s * D * P[j]
        out["hold_ms"][i] = H * DAY
    return out
