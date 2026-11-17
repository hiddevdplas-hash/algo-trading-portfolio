"""IDEA-1021: autocallable dealer-gamma fade in the Nikkei and Euro Stoxx cash sessions
(card ideas/cards/IDEA-1021-autocall-dealer-gamma-session-fade.md, v1).

m15 bars, local exchange clock (DST by zone):
  JP225:   open = open of the bar starting 09:00 Tokyo; decisions on bars closing 10:00-14:00 Tokyo; time exit 15:00 Tokyo.
  STOXX50: open = open of the bar starting 09:00 Frankfurt; decisions on bars closing 10:00-15:00 Frankfurt; time exit 15:30 Frankfurt.
A session exists when its 09:00 bar exists. R20 = mean of the previous 20 sessions' ranges (high - low of the bars from the session
open to the time exit; today excluded). Barrier proxy: no trade on a day whose open < 0.80 x the highest session close of the previous
250 sessions (session close = close of the last session bar ending at or before the time exit). At a decision bar's close,
d = close - session open; if |d| >= k * R20: market order against d, stop s * R20, target |d| (back to the open), time exit at the
session's exit. First trigger only, one trade per symbol per day. Closed bars only: everything at bar i uses bars <= i.
params: k (0.55), s (0.45).
"""
import numpy as np

from engine.timeutil import local_ms

DEFAULTS = {"k": 0.55, "s": 0.45}
SESSIONS = {  # zone, open (local minutes, bar open), first / last decision (bar close), time exit (local minutes)
    "JP225": ("Asia/Tokyo", 9 * 60, 10 * 60, 14 * 60, 15 * 60),
    "STOXX50": ("Europe/Berlin", 9 * 60, 10 * 60, 15 * 60, 15 * 60 + 30),
}
MIN = 60_000
DAY = 86_400_000
LOOKBACK = 20
BARRIER_N = 250
BARRIER_FRAC = 0.80


def _empty(n):
    return {"side": np.zeros(n, np.int64), "otype": np.zeros(n, np.int64), "price": np.full(n, np.nan),
            "sl_dist": np.full(n, np.nan), "tp_dist": np.full(n, np.nan), "expiry_ms": np.full(n, np.nan),
            "hold_ms": np.full(n, np.nan)}


def intents(bars, params, ctx):
    p = {**DEFAULTS, **params}
    k, s = float(p["k"]), float(p["s"])
    sym = ctx["symbol"]
    if sym not in SESSIONS:
        raise ValueError(f"IDEA-1021 trades {tuple(SESSIONS)}, not {sym}")
    zone, open_min, dec_lo, dec_hi, exit_min = SESSIONS[sym]
    o = np.asarray(bars["o"], float)
    h = np.asarray(bars["h"], float)
    l = np.asarray(bars["l"], float)
    c = np.asarray(bars["c"], float)
    oms = np.asarray(bars["open_ms"], np.int64)
    cms = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    out = _empty(n)
    if n == 0:
        return out
    lo = local_ms(oms, zone)
    lc = local_ms(cms, zone)
    off = lc - cms                                   # local UTC offset at each bar's close
    oday, omin = lo // DAY, (lo % DAY) // MIN
    cday, cmin = lc // DAY, (lc % DAY) // MIN
    first_ms = ctx["first_ms"]

    ranges, closes = [], []                          # completed sessions only
    cur = None                                       # state of today's session
    for i in range(n):
        d = int(oday[i])
        if cur is not None and d != cur["day"]:      # a new local day: close out the previous session
            ranges.append(cur["hi"] - cur["lo"])
            closes.append(cur["close"])
            cur = None
        if cur is None:
            if omin[i] != open_min:
                continue
            cur = {"day": d, "open": o[i], "hi": -np.inf, "lo": np.inf, "close": np.nan, "done": False,
                   "ok": True}
            if len(closes) >= 1:
                ref = max(closes[-BARRIER_N:])
                cur["ok"] = o[i] >= BARRIER_FRAC * ref
        # bars of the session: from the open to the time exit (bar closing at or before the exit, same local day)
        if not (cday[i] == cur["day"] and cmin[i] <= exit_min and omin[i] >= open_min):
            continue
        cur["hi"] = max(cur["hi"], h[i])
        cur["lo"] = min(cur["lo"], l[i])
        cur["close"] = c[i]
        if cur["done"] or not cur["ok"] or len(ranges) < LOOKBACK or oms[i] < first_ms:
            continue
        if not (dec_lo <= cmin[i] <= dec_hi):
            continue
        r20 = float(np.mean(ranges[-LOOKBACK:]))
        dv = c[i] - cur["open"]
        if r20 <= 0 or dv == 0 or abs(dv) < k * r20:
            continue
        exit_utc = cur["day"] * DAY + exit_min * MIN - int(off[i])
        hold = exit_utc - int(cms[i])
        if hold <= 0:
            continue
        out["side"][i] = -1 if dv > 0 else 1
        out["sl_dist"][i] = s * r20
        out["tp_dist"][i] = abs(dv)
        out["hold_ms"][i] = hold
        cur["done"] = True
    return out
