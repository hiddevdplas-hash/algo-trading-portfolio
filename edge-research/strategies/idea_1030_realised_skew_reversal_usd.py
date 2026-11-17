"""IDEA-1030: realised-skewness reversal in USD pairs, held two days (open slot)
(card ideas/cards/IDEA-1030-realised-skew-reversal-usd.md, v1).

h1 bars, New York clock (America/New_York, daylight saving via engine.timeutil).
Decision bar = the h1 bar whose close is 16:00 New York, Monday to Friday (New York weekday of that close); entries only
Monday to Thursday (a Friday decision bar records its RSkew and range, no entry).
At a decision bar i:
  returns r_j = ln c_j - ln c_{j-1} for the bars j in the window of the last 24 * N bars ending at i, counting only
  returns between adjacent bars (open_ms[j] == close_ms[j-1]): a return across a market break (weekend, holiday) is left out.
  If fewer than 0.8 * 24 * N such returns exist -> no value.
  RSkew = sqrt(m) * sum(r^3) / sum(r^2)^1.5 (m = number of returns used).
  P = share of the previous 250 decision bars' RSkew values (decision bars with a value, the current one excluded) that are
      strictly below the current RSkew. No trade until 250 exist.
  P >= 1 - q -> sell; P <= q -> buy (only on decision bars with open_ms >= first_ms).
  Stop = D, D = mean over the previous 20 decision bars (current one included) of max(h) - min(l) of the 24 bars ending at each.
  No target; time exit HOLD (48 h) after the fill; class B weekend flat by the engine.
Closed bars only: every value at bar i uses bars <= i; the percentile uses only earlier decision bars.
params: N (10; grid 5, 10, 20), q (0.10; grid 0.05, 0.10, 0.20).
"""
import numpy as np

from engine.timeutil import local_ms

DEFAULTS = {"N": 10, "q": 0.10}
SYMBOLS = ("USDJPY", "AUDUSD", "USDCAD")
ZONE = "America/New_York"
DECISION = 16 * 60          # close of the bar ending 16:00 New York
RANK_LOOKBACK = 250
RANGE_DAYS = 20
MIN_SHARE = 0.8
HOLD = 48 * 3_600_000
MIN = 60_000
DAY = 86_400_000


def _empty(n):
    return {"side": np.zeros(n, np.int64), "otype": np.zeros(n, np.int64), "price": np.full(n, np.nan),
            "sl_dist": np.full(n, np.nan), "tp_dist": np.full(n, np.nan), "expiry_ms": np.full(n, np.nan),
            "hold_ms": np.full(n, np.nan)}


def intents(bars, params, ctx):
    p = {**DEFAULTS, **params}
    N, q = int(p["N"]), float(p["q"])
    sym = ctx["symbol"]
    if sym not in SYMBOLS:
        raise ValueError(f"IDEA-1030 trades {SYMBOLS}, not {sym}")
    if ctx.get("timeframe") not in (None, "h1"):
        raise ValueError("IDEA-1030 is an h1 strategy")
    if N < 1 or not 0.0 < q < 0.5:
        raise ValueError("IDEA-1030: N >= 1 and 0 < q < 0.5")
    c = np.asarray(bars["c"], float)
    h = np.asarray(bars["h"], float)
    lo = np.asarray(bars["l"], float)
    oms = np.asarray(bars["open_ms"], np.int64)
    cms = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    out = _empty(n)
    if n < 2:
        return out
    lc = local_ms(cms, ZONE)
    cday, cmin = lc // DAY, (lc % DAY) // MIN
    wday = (cday + 3) % 7                              # 1970-01-01 was a Thursday: 0 = Monday
    first_ms = ctx["first_ms"]

    r = np.full(n, np.nan)                             # r[j]: return into bar j, only between adjacent bars
    adj = oms[1:] == cms[:-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        rr = np.log(c[1:]) - np.log(c[:-1])
    r[1:] = np.where(adj & np.isfinite(rr), rr, np.nan)

    w = 24 * N
    need = int(np.ceil(MIN_SHARE * w))
    skews = []                                         # RSkew of earlier decision bars, in time order
    ranges = []                                        # 24-bar range of decision bars, in time order
    for i in range(n):
        if int(cmin[i]) != DECISION:
            continue
        if i >= 23:
            ranges.append(float(np.max(h[i - 23:i + 1]) - np.min(lo[i - 23:i + 1])))
        if i < w or int(wday[i]) > 4:                  # weekend decision bars never occur; guard anyway
            continue
        seg = r[i - w + 1:i + 1]
        seg = seg[np.isfinite(seg)]
        m = len(seg)
        if m < need:
            continue
        s2 = float(np.sum(seg * seg))
        if s2 <= 0:
            continue
        rs = float(np.sqrt(m) * np.sum(seg ** 3) / s2 ** 1.5)
        prev = skews[-RANK_LOOKBACK:]
        skews.append(rs)
        if int(wday[i]) > 3 or len(prev) < RANK_LOOKBACK or len(ranges) < RANGE_DAYS:
            continue                                   # Friday: value recorded, no entry
        if oms[i] < first_ms:
            continue
        P = float(np.mean(np.asarray(prev) < rs))
        D = float(np.mean(ranges[-RANGE_DAYS:]))
        if not np.isfinite(D) or D <= 0:
            continue
        if P >= 1.0 - q:
            out["side"][i] = -1
        elif P <= q:
            out["side"][i] = 1
        else:
            continue
        out["sl_dist"][i] = D
        out["hold_ms"][i] = HOLD
    return out
