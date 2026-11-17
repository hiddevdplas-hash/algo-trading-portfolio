"""IDEA-2000: last-half-hour intraday momentum on index CFDs (card v3, ideas/cards/IDEA-2000-last-half-hour-index-momentum.md).

Rules rebuilt from the card (Baltussen, Da, Lammers, Martens 2021, ROD signal); no code copied.
- m15 bars, each index in its own cash-session clock: US500 / USTEC New York (close 16:00), STOXX50 Frankfurt time (close 17:30).
- S = return from the prior cash close (close of the m15 bar ending at the cash close on the previous trading day that has one) to the
  close of the bar ending 30 min before today's cash close. z = S / sd(S over the previous 60 trading days; today excluded).
- Entry at that bar's close: long if z >= q, short if z <= -q (market). Stop k x Wilder ATR(14) of m15 bars at the entry bar.
- Exit at the close of the m15 bar ending at today's cash close (exit flag). No target.
params (card defaults): q = 0.5, k = 1.5.
Class A flat times, entry blocks, news modes and caps are applied by the engine, not here.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np

_SESSIONS = {  # symbol -> (time zone, cash close minute of day)
    "US500": ("America/New_York", 16 * 60),
    "USTEC": ("America/New_York", 16 * 60),
    "STOXX50": ("Europe/Berlin", 17 * 60 + 30),
}
_SIGMA_DAYS = 60
_ATR_N = 14
_LEAD_MIN = 30


def _local_ms(ms, tzname):
    """Local wall-clock ms for UTC ms (offset looked up once per UTC hour)."""
    tz = ZoneInfo(tzname)
    hours = ms // 3_600_000
    uh, inv = np.unique(hours, return_inverse=True)
    off = np.array([int(datetime.fromtimestamp(int(h) * 3600, timezone.utc).astimezone(tz).utcoffset().total_seconds() * 1000)
                    for h in uh], dtype=np.int64)
    return ms + off[inv]


def _atr(h, l, c, n=_ATR_N):
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    out = np.full(len(c), np.nan)
    if len(c) >= n:
        out[n - 1] = tr[:n].mean()
        a = 1.0 / n
        for i in range(n, len(c)):
            out[i] = out[i - 1] + a * (tr[i] - out[i - 1])
    return out


def intents(bars, params, ctx):
    q = float(params.get("q", 0.5))
    k = float(params.get("k", 1.5))
    c = bars["c"]
    n = len(c)
    side = np.zeros(n, np.int64)
    sl = np.full(n, np.nan)
    ex = np.zeros(n, bool)
    out = {"side": side, "sl_dist": sl, "exit_long": ex, "exit_short": ex.copy()}
    if ctx["symbol"] not in _SESSIONS or n == 0:
        return out
    tzname, close_min = _SESSIONS[ctx["symbol"]]
    loc = _local_ms(bars["close_ms"].astype(np.int64), tzname)
    day = loc // 86_400_000
    mod = (loc // 60_000) % 1440
    atr = _atr(bars["h"], bars["l"], c)

    sig_idx = {int(day[i]): i for i in np.nonzero(mod == close_min - _LEAD_MIN)[0]}
    cls_idx = {int(day[i]): i for i in np.nonzero(mod == close_min)[0]}

    prev_close = None   # close price of the most recent cash-close bar before the current day
    hist = []           # past S values, one per trading day, oldest first
    for d in sorted(set(sig_idx) | set(cls_idx)):
        i = sig_idx.get(d)
        j = cls_idx.get(d)
        if i is not None and prev_close is not None and (j is None or j > i):
            s = c[i] / prev_close - 1.0
            if len(hist) >= _SIGMA_DAYS:
                sd = float(np.std(hist[-_SIGMA_DAYS:], ddof=1))
                if sd > 0 and bars["open_ms"][i] >= ctx["first_ms"] and not np.isnan(atr[i]):
                    z = s / sd
                    if z >= q:
                        side[i] = 1
                    elif z <= -q:
                        side[i] = -1
                    if side[i] != 0:
                        sl[i] = k * atr[i]
            hist.append(s)
        if j is not None:
            out["exit_long"][j] = True
            out["exit_short"][j] = True
            prev_close = c[j]
    return out
