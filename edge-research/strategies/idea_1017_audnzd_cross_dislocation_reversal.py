"""IDEA-1017: AUDNZD cross dislocation reversal (card ideas/cards/IDEA-1017-audnzd-cross-dislocation-reversal.md, v1).

h1 bars, London clock. Daily price P = close of the h1 bar ending 00:00 London (only days with that bar count).
r_N = ln(P_d / P_{d-N}); sigma = std of the last 60 daily log returns of P (today's excluded); z = r_N / (sigma * sqrt(N)).
Short if z >= k, long if z <= -k: market order at that bar's close, on bars ending 00:00 London Tuesday-Friday, not on London dates
24 Dec - 1 Jan. Stop 2.0 * sigma * close; no target; time exit H * 24 h after the fill (the class B Friday flat is the engine's).
params: N (5), k (1.5), H (2).
"""
from datetime import date

import numpy as np

from engine.timeutil import local_ms

DEFAULTS = {"N": 5, "k": 1.5, "H": 2}
SYMBOLS = ("AUDNZD",)
ZONE = "Europe/London"
MIN = 60_000
DAY = 86_400_000
CLOCK = 0                  # bar close 00:00 London
VOL_DAYS = 60
STOP_SIG = 2.0
_EPOCH = date(1970, 1, 1).toordinal()


def _empty(n):
    return {"side": np.zeros(n, np.int64), "otype": np.zeros(n, np.int64), "price": np.full(n, np.nan),
            "sl_dist": np.full(n, np.nan), "tp_dist": np.full(n, np.nan), "expiry_ms": np.full(n, np.nan),
            "hold_ms": np.full(n, np.nan)}


def _year_end(d):
    dt = date.fromordinal(int(d) + _EPOCH)
    return (dt.month == 12 and dt.day >= 24) or (dt.month == 1 and dt.day == 1)


def intents(bars, params, ctx):
    p = {**DEFAULTS, **params}
    N, k, H = int(p["N"]), float(p["k"]), int(p["H"])
    if ctx["symbol"] not in SYMBOLS:
        raise ValueError(f"IDEA-1017 trades {SYMBOLS}, not {ctx['symbol']}")
    if ctx.get("timeframe") != "h1":
        raise ValueError(f"IDEA-1017 runs on h1 bars, not {ctx.get('timeframe')}")
    c = np.asarray(bars["c"], float)
    oms = np.asarray(bars["open_ms"], np.int64)
    cms = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    out = _empty(n)
    if n == 0:
        return out
    loc = local_ms(cms, ZONE)
    day, mnt = loc // DAY, (loc % DAY) // MIN
    idx = np.flatnonzero(mnt == CLOCK)          # one bar per London day, in time order
    lp = np.log(c[idx])
    for j in range(len(idx)):
        if j < max(N, VOL_DAYS + 1):            # need N past P's and 60 past returns before today
            continue
        i = idx[j]
        d = int(day[i])
        if not 1 <= (d + 3) % 7 <= 4 or _year_end(d) or oms[i] < ctx["first_ms"]:
            continue
        rets = np.diff(lp[j - VOL_DAYS - 1:j])  # the 60 returns ending at P_{d-1}
        sig = float(np.std(rets, ddof=1))
        if not sig > 0:
            continue
        z = (lp[j] - lp[j - N]) / (sig * np.sqrt(N))
        if abs(z) < k:
            continue
        out["side"][i] = -1 if z > 0 else 1
        out["sl_dist"][i] = STOP_SIG * sig * c[i]
        out["hold_ms"][i] = H * DAY
    return out
