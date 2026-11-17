"""IDEA-1027: key-reversal day follow-through (card v1, ideas/cards/IDEA-1027-key-reversal-day-follow-through.md). Open slot.

- h1 bars, New York clock (America/New_York, daylight saving via engine.timeutil). Day d = bars closing after 17:00 New York of the
  previous calendar day and at or before 16:00 New York of day d; bars closing in (16:00, 17:00] belong to no day. The bar closing at
  16:00 is the decision bar. A day counts if it has its decision bar and >= 16 bars. Yesterday = the previous counted day.
- Bullish: L(d) < L(y), H(d) > H(y), the first bar reaching L(d) is earlier than the first reaching H(d),
  C(d) >= L(d) + q x (H(d) - L(d)), C(d) > C(y). Bearish: the mirror. C(d) = close of the decision bar.
- Entry: market order at the decision bar's close (no entry when the decision bar's New York weekday is Friday). Stop at the day's
  extreme (long C - L, short H - C). No target; time exit H x 24 h after the fill.
- Closed bars only: every value at bar i uses bars <= i.
params (card defaults): q = 0.75, H = 2. Class B rules, news modes and caps are applied by the engine.
"""
import numpy as np

from engine.timeutil import local_ms

DEFAULTS = {"q": 0.75, "H": 2}
SYMBOLS = ("XAGUSD", "XTIUSD", "GBPUSD")
ZONE = "America/New_York"
DECISION = 16 * 60              # close of the bar ending 16:00 New York
DAY_START = 17 * 60             # bars closing after 17:00 belong to the next day
MIN_BARS = 16
MIN = 60_000
DAY = 86_400_000


def _empty(n):
    return {"side": np.zeros(n, np.int64), "otype": np.zeros(n, np.int64), "price": np.full(n, np.nan),
            "sl_dist": np.full(n, np.nan), "tp_dist": np.full(n, np.nan), "expiry_ms": np.full(n, np.nan),
            "hold_ms": np.full(n, np.nan)}


def intents(bars, params, ctx):
    p = {**DEFAULTS, **params}
    q, hold_days = float(p["q"]), int(p["H"])
    sym = ctx["symbol"]
    if sym not in SYMBOLS:
        raise ValueError(f"IDEA-1027 trades {SYMBOLS}, not {sym}")
    if ctx.get("timeframe", "h1") != "h1":
        raise ValueError("IDEA-1027 is defined on h1 bars")
    if not (0.0 < q < 1.0) or hold_days < 1:
        raise ValueError("IDEA-1027: q must be in (0, 1) and H >= 1")
    h = np.asarray(bars["h"], float)
    l = np.asarray(bars["l"], float)
    c = np.asarray(bars["c"], float)
    oms = np.asarray(bars["open_ms"], np.int64)
    cms = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    out = _empty(n)
    if n == 0:
        return out
    lc = local_ms(cms, ZONE)
    cday, cmin = lc // DAY, (lc % DAY) // MIN
    first_ms = ctx["first_ms"]
    hold = float(hold_days * DAY)

    cur = None                  # day key of the bars being collected
    hi = lo = None
    hi_i = lo_i = -1
    cnt = 0
    prev = None                 # (H, L, C) of the previous counted day
    for i in range(n):
        m = int(cmin[i])
        if m > DAY_START:
            d = int(cday[i]) + 1
        elif m <= DECISION:
            d = int(cday[i])
        else:
            continue            # closes in (16:00, 17:00]: no day
        if d != cur:
            cur, cnt = d, 0
            hi, lo = h[i], l[i]
            hi_i = lo_i = i
        else:
            if h[i] > hi:
                hi, hi_i = h[i], i
            if l[i] < lo:
                lo, lo_i = l[i], i
        cnt += 1
        if m != DECISION:
            continue
        # decision bar: day d is complete
        if cnt < MIN_BARS:
            cur = None          # not counted; a later bar with the same key cannot exist
            continue
        C = c[i]
        if prev is not None and oms[i] >= first_ms and (d + 3) % 7 != 4:    # 1970-01-01 was a Thursday: 4 = Friday
            pH, pL, pC = prev
            rng = hi - lo
            if lo < pL and hi > pH and rng > 0:
                if lo_i < hi_i and C >= lo + q * rng and C > pC and C - lo > 0:
                    out["side"][i] = 1
                    out["sl_dist"][i] = C - lo
                    out["hold_ms"][i] = hold
                elif hi_i < lo_i and C <= hi - q * rng and C < pC and hi - C > 0:
                    out["side"][i] = -1
                    out["sl_dist"][i] = hi - C
                    out["hold_ms"][i] = hold
        prev = (hi, lo, C)
        cur = None
    return out
