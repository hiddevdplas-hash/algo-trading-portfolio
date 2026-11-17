"""IDEA-1022: PBoC fixing repricing of AUD and NZD
(card ideas/cards/IDEA-1022-pboc-fix-repricing-aud-nzd.md, v1).

m15 bars, Beijing clock (Asia/Shanghai, no daylight saving). Monday-Friday Beijing dates on which the bar starting 09:15 exists.
Fix-window move d = close of the bar ending 09:30 - open of the bar starting 09:15 (that one bar).
Scales over the previous 20 days with a window (today excluded): D = mean |d|; W = mean range (high - low) of the bars from
09:30 to 11:30 Beijing (bars opening >= 09:30 and closing <= 11:30). No trade until 20 days exist.
At the close of the bar ending 09:30 Beijing: if |d| >= k * D, market order in the direction of d, stop 0.75 * W, no target,
time exit at X Beijing. One trade per symbol per day. Closed bars only: everything at bar i uses bars <= i
(today's W is added to the history only after its window is complete, and is never used for today's trade).
params: k (1.5), X (690 = 11:30 Beijing, minutes after midnight; grid 690, 810, 930).
"""
import numpy as np

from engine.timeutil import local_ms

DEFAULTS = {"k": 1.5, "X": 11 * 60 + 30}
SYMBOLS = ("AUDUSD", "NZDUSD")
ZONE = "Asia/Shanghai"
FIX_OPEN = 9 * 60 + 15          # bar starting 09:15 Beijing (the fix)
DECIDE = 9 * 60 + 30            # its close
W_END = 11 * 60 + 30            # end of the W window
STOP_W = 0.75
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
        raise ValueError(f"IDEA-1022 trades {SYMBOLS}, not {sym}")
    if not DECIDE < X < 24 * 60:
        raise ValueError("IDEA-1022: the exit clock X must be after 09:30 Beijing, same day")
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
    lo = local_ms(oms, ZONE)
    lc = local_ms(cms, ZONE)
    oday, omin = lo // DAY, (lo % DAY) // MIN
    cday, cmin = lc // DAY, (lc % DAY) // MIN
    wday = (oday + 3) % 7                            # 1970-01-01 was a Thursday: 0 = Monday
    first_ms = ctx["first_ms"]
    hold = (X - DECIDE) * MIN

    dhist, whist = [], []                            # completed days only
    cur = None                                       # today's window state
    for i in range(n):
        d = int(oday[i])
        if cur is not None and d != cur["day"]:      # new Beijing day: store yesterday's scales
            if cur["d"] is not None:
                dhist.append(abs(cur["d"]))
                if np.isfinite(cur["hi"]) and np.isfinite(cur["lo"]):
                    whist.append(cur["hi"] - cur["lo"])
            cur = None
        if cur is None:
            if omin[i] != FIX_OPEN or wday[i] > 4:
                continue
            cur = {"day": d, "fo": o[i], "d": None, "hi": -np.inf, "lo": np.inf}
        # the fix bar itself: decide at its close
        if omin[i] == FIX_OPEN and oday[i] == cur["day"] and cmin[i] == DECIDE and cday[i] == cur["day"]:
            dv = c[i] - cur["fo"]
            cur["d"] = dv
            if len(dhist) < LOOKBACK or len(whist) < LOOKBACK or oms[i] < first_ms:
                continue
            D = float(np.mean(dhist[-LOOKBACK:]))
            W = float(np.mean(whist[-LOOKBACK:]))
            if D <= 0 or W <= 0 or dv == 0 or abs(dv) < k * D:
                continue
            out["side"][i] = 1 if dv > 0 else -1
            out["sl_dist"][i] = STOP_W * W
            out["hold_ms"][i] = hold
            continue
        # bars of the W window (09:30-11:30 Beijing, same day)
        if cday[i] == cur["day"] and omin[i] >= DECIDE and cmin[i] <= W_END and oday[i] == cur["day"]:
            cur["hi"] = max(cur["hi"], h[i])
            cur["lo"] = min(cur["lo"], l[i])
    return out
