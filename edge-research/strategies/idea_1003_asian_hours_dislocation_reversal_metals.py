"""IDEA-1003: Asian-hours dislocation reversal in gold and silver (card ideas/cards/IDEA-1003-asian-hours-dislocation-reversal-metals.md, v1).

m15 bars. Signal window: bars closing 00:30 -> 06:00 UTC, Monday-Friday. At bar i: r = c[i] / c[i-W] - 1 over W contiguous bars;
D = mean |c[j] / c[j-4] - 1| over every window bar j (4 contiguous bars behind it) of the previous 20 trading days (days with at least one
such bar). Trade if |r| >= k * D: market, against r, at most one trade per symbol per day. Stop s * D * price; target = c[i-W]
(distance |c[i] - c[i-W]|); time exit at 08:00 London.
params: W (2), k (2.0), s (1.5).
"""
import numpy as np

from engine.timeutil import local_ms

DEFAULTS = {"W": 2, "k": 2.0, "s": 1.5}
SYMBOLS = ("XAUUSD", "XAGUSD")
MIN = 60_000
DAY = 86_400_000
WIN_FIRST, WIN_LAST = 30, 360        # bar close, minutes after 00:00 UTC (00:30 -> 06:00)
D_DAYS, D_BARS = 20, 4
EXIT_LDN = 8 * 60                    # 08:00 London


def _empty(n):
    return {"side": np.zeros(n, np.int64), "otype": np.zeros(n, np.int64), "price": np.full(n, np.nan),
            "sl_dist": np.full(n, np.nan), "tp_dist": np.full(n, np.nan), "expiry_ms": np.full(n, np.nan),
            "hold_ms": np.full(n, np.nan)}


def intents(bars, params, ctx):
    p = {**DEFAULTS, **params}
    W, k, s = int(p["W"]), float(p["k"]), float(p["s"])
    if ctx["symbol"] not in SYMBOLS:
        raise ValueError(f"IDEA-1003 trades {SYMBOLS}, not {ctx['symbol']}")
    c = np.asarray(bars["c"], float)
    oms = np.asarray(bars["open_ms"], np.int64)
    cms = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    out = _empty(n)
    if n == 0:
        return out
    tf = int(cms[0] - oms[0])
    uday = cms // DAY
    umin = (cms % DAY) // MIN
    ldn_min = (local_ms(cms, "Europe/London") % DAY) // MIN
    in_win = (umin >= WIN_FIRST) & (umin <= WIN_LAST) & (((uday + 3) % 7) < 5)

    def contiguous(i, w):
        return i - w >= 0 and oms[i] - oms[i - w] == w * tf

    sums, cnts = [], []                 # per past day: sum and count of the 4-bar moves
    cur_day, cur_sum, cur_cnt, traded = None, 0.0, 0, False
    for i in range(n):
        if not in_win[i]:
            continue
        d = int(uday[i])
        if d != cur_day:
            if cur_day is not None and cur_cnt > 0:
                sums.append(cur_sum)
                cnts.append(cur_cnt)
            cur_day, cur_sum, cur_cnt, traded = d, 0.0, 0, False
        # decision first, from past days only
        if (not traded and oms[i] >= ctx["first_ms"] and len(cnts) >= D_DAYS and contiguous(i, W)):
            D = sum(sums[-D_DAYS:]) / sum(cnts[-D_DAYS:])
            r = c[i] / c[i - W] - 1.0
            hold = (EXIT_LDN - int(ldn_min[i])) * MIN
            if D > 0 and abs(r) >= k * D and hold > 0:
                out["side"][i] = -1 if r > 0 else 1
                out["sl_dist"][i] = s * D * c[i]
                out["tp_dist"][i] = abs(c[i] - c[i - W])
                out["hold_ms"][i] = hold
                traded = True
        # then add this bar's 4-bar move to today's D sample (used from tomorrow on)
        if contiguous(i, D_BARS):
            cur_sum += abs(c[i] / c[i - D_BARS] - 1.0)
            cur_cnt += 1
    return out
