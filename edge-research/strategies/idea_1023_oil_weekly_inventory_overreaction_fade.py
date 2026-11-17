"""IDEA-1023: oil weekly-inventory overreaction fade
(card ideas/cards/IDEA-1023-oil-weekly-inventory-overreaction-fade.md, v1).

m15 bars, New York clock (America/New_York, daylight saving via engine.timeutil). Per New York date (weekdays only):
r = close of the bar ending 14:30 New York - close of the bar ending 10:15 New York (both on that date; missing either -> no r).
A = mean |r| over the previous 20 weekdays with an r (the current day excluded). No trade until 20 exist.
On a Thursday whose previous calendar day (Wednesday) has an r = M: at the close of the bar ending 03:00 New York on that Thursday,
if |M| >= k * A (A as known on the Wednesday, i.e. the 20 weekdays before it), market order against M, stop 0.5 * |M|,
no target, time exit at X New York the same day. One trade per symbol per week.
Closed bars only: everything at bar i uses bars <= i (the Wednesday r is complete at 14:30 Wednesday, long before Thursday 03:00).
params: k (1.5; grid 1.25, 1.5, 2.0), X (660 = 11:00 New York, minutes after midnight; grid 480, 660, 870).
"""
import numpy as np

from engine.timeutil import local_ms

DEFAULTS = {"k": 1.5, "X": 11 * 60}
SYMBOLS = ("XTIUSD", "XBRUSD")
ZONE = "America/New_York"
REF_END = 10 * 60 + 15          # close of the bar ending 10:15 New York (before the 10:30 release)
SETTLE_END = 14 * 60 + 30       # close of the bar ending 14:30 New York (WTI settle)
ENTRY_END = 3 * 60              # Thursday: close of the bar ending 03:00 New York
STOP_M = 0.5
LOOKBACK = 20
MIN = 60_000
DAY = 86_400_000


def _empty(n):
    return {"side": np.zeros(n, np.int64), "otype": np.zeros(n, np.int64), "price": np.full(n, np.nan),
            "sl_dist": np.full(n, np.nan), "tp_dist": np.full(n, np.nan), "expiry_ms": np.full(n, np.nan),
            "hold_ms": np.full(n, np.nan)}


def intents(bars, params, ctx):
    p = {**DEFAULTS, **params}
    k, X = float(p["k"]), int(p["X"])
    sym = ctx["symbol"]
    if sym not in SYMBOLS:
        raise ValueError(f"IDEA-1023 trades {SYMBOLS}, not {sym}")
    if ctx.get("timeframe") not in (None, "m15"):
        raise ValueError("IDEA-1023 is an m15 strategy")
    if not ENTRY_END < X < 24 * 60:
        raise ValueError("IDEA-1023: the exit clock X must be after 03:00 New York, same day")
    c = np.asarray(bars["c"], float)
    oms = np.asarray(bars["open_ms"], np.int64)
    cms = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    out = _empty(n)
    if n == 0:
        return out
    lc = local_ms(cms, ZONE)
    cday, cmin = lc // DAY, (lc % DAY) // MIN
    wday = (cday + 3) % 7                            # 1970-01-01 was a Thursday: 0 = Monday
    first_ms = ctx["first_ms"]
    hold = (X - ENTRY_END) * MIN

    rhist = []                                       # |r| of completed weekdays, in date order
    ref = {}                                         # New York date -> close at 10:15 (that day only)
    wed = None                                       # (date, M, A) of the latest Wednesday with an r and a full A
    for i in range(n):
        d, m, wd = int(cday[i]), int(cmin[i]), int(wday[i])
        if wd > 4:
            continue
        if m == REF_END:
            ref = {d: c[i]}
            continue
        if m == SETTLE_END and d in ref:
            r = c[i] - ref.pop(d)
            if wd == 2:                              # Wednesday: freeze M and the A known before today
                A = float(np.mean(rhist[-LOOKBACK:])) if len(rhist) >= LOOKBACK else np.nan
                wed = (d, r, A)
            rhist.append(abs(r))                     # today's r joins the history only after it is used
            continue
        if m == ENTRY_END and wd == 3 and wed is not None and wed[0] == d - 1:
            _, M, A = wed
            wed = None
            if not np.isfinite(A) or A <= 0 or M == 0 or oms[i] < first_ms:
                continue
            if abs(M) < k * A:
                continue
            out["side"][i] = -1 if M > 0 else 1
            out["sl_dist"][i] = STOP_M * abs(M)
            out["hold_ms"][i] = hold
    return out
