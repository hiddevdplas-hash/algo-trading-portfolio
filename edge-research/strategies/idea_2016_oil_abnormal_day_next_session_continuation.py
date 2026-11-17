"""IDEA-2016: oil next-session continuation after an abnormal open-to-close day (card v1,
ideas/cards/IDEA-2016-oil-abnormal-day-next-session-continuation.md).

Rule rebuilt from the card (Caporale & Plastun, FMPM 2021, Strategy 2 for oil); no code copied.
- m15 bars, New York clock. Trading day key = New York date of (bar open + 7 h): bars opening 17:00 NY of the previous date
  to before 17:00 NY of date D belong to day D. Day open = open of its first bar, day close = close of its last bar.
  A day counts if its last bar closes at or after 16:45 NY and its first bar opens at or before 21:00 NY the evening before.
- R_D = C_D / O_D - 1. Mean / sigma over the 250 counted days before D (D excluded). Positive abnormal: R_D > mean + k sigma;
  negative: R_D < mean - k sigma.
- Entry in the next trading day in the data (the day directly after D, D counted), at market at the close of its first bar
  closing at or after 19:30 NY on the evening that opens it: buy after positive, sell after negative. Stop 1.5 x sigma x entry close. No target.
- Exit flags on the bar of that day closing at exit_ny (NY minutes); backstop time exit 24 h.
params (card defaults): k = 2.0, exit_ny = 990.
Class A flat, entry blocks, news modes and caps are applied by the engine, not here.
"""
import numpy as np

from engine.timeutil import local_ms

DEFAULTS = {"k": 2.0, "exit_ny": 990}
MIN = 60_000
HOUR = 3_600_000
DAY = 86_400_000
LOOKBACK = 250
K_STOP = 1.5
ENTRY_MIN = 19 * 60 + 30        # first bar closing at or after 19:30 NY
LAST_CLOSE_MIN = 16 * 60 + 45   # full day: last bar closes at or after 16:45 NY
FIRST_OPEN_MAX = 21 * 60        # full day: first bar opens at or before 21:00 NY the evening before
HOLD_MS = 24 * HOUR


def intents(bars, params, ctx):
    p = {**DEFAULTS, **params}
    k = float(p["k"])
    exit_ny = int(p["exit_ny"])
    o = np.asarray(bars["o"], float)
    c = np.asarray(bars["c"], float)
    oms = np.asarray(bars["open_ms"], np.int64)
    cms = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    side = np.zeros(n, np.int64)
    sl = np.full(n, np.nan)
    hold = np.full(n, np.nan)
    exl = np.zeros(n, bool)
    exs = np.zeros(n, bool)
    out = {"side": side, "sl_dist": sl, "hold_ms": hold, "exit_long": exl, "exit_short": exs}
    if n == 0:
        return out
    lo = local_ms(oms, "America/New_York")
    lc = local_ms(cms, "America/New_York")
    key = (lo + 7 * HOUR) // DAY                      # trading day of each bar
    o_min = (lo % DAY) // MIN
    c_min = (lc % DAY) // MIN
    c_day = lc // DAY

    # group bars into trading days (bars are in time order)
    starts = np.r_[0, np.nonzero(np.diff(key))[0] + 1]
    ends = np.r_[starts[1:], n] - 1
    days = key[starts]
    m = len(starts)

    # full-session flag and day return (uses only that day's own bars)
    first_ok = (o_min[starts] >= 17 * 60) & (o_min[starts] <= FIRST_OPEN_MAX)
    last_ok = (c_day[ends] == days) & (c_min[ends] >= LAST_CLOSE_MIN)
    counted = first_ok & last_ok
    with np.errstate(invalid="ignore", divide="ignore"):
        R = c[ends] / o[starts] - 1.0

    # trailing mean / sigma over the previous LOOKBACK counted days (day itself excluded)
    sig_side = np.zeros(m, np.int64)
    sig_sd = np.full(m, np.nan)
    hist = []
    for j in range(m):
        if not counted[j] or not np.isfinite(R[j]):
            continue
        if len(hist) >= LOOKBACK:
            w = np.asarray(hist[-LOOKBACK:])
            mu, sd = float(w.mean()), float(w.std(ddof=1))
            if sd > 0:
                if R[j] > mu + k * sd:
                    sig_side[j] = 1
                elif R[j] < mu - k * sd:
                    sig_side[j] = -1
                sig_sd[j] = sd
        hist.append(float(R[j]))

    # entry and exit in the next trading day (directly after a counted signal day)
    first_ms = ctx["first_ms"]
    for j in range(1, m):
        s = sig_side[j - 1]
        if s == 0:
            continue
        a, b = starts[j], ends[j]
        seg = np.arange(a, b + 1)
        t_entry = (days[j] - 1) * DAY + ENTRY_MIN * MIN   # 19:30 NY on the evening that opens day D + 1 (local ms)
        ent = seg[lc[seg] >= t_entry]
        if len(ent) == 0:
            continue
        i = int(ent[0])
        if oms[i] < first_ms:
            continue
        side[i] = s
        sl[i] = K_STOP * sig_sd[j - 1] * c[i]
        hold[i] = HOLD_MS
        xs = seg[(seg > i) & (c_day[seg] == days[j]) & (c_min[seg] == exit_ny)]
        if len(xs):
            if s > 0:
                exl[xs[0]] = True
            else:
                exs[xs[0]] = True
    return out
