"""IDEA-2008: RSI(2) pullback in an uptrend, bought at the US cash close (card v2,
ideas/cards/IDEA-2008-rsi2-pullback-us-indices.md).

Rule rebuilt from the card (Connors & Alvarez 2008 as stated by Krueger Algorithms, 2026 pages); no code copied.
- h1 bars, New York clock. Cash close of a day = close of the h1 bar ending 16:00 ET (weekdays that have one).
  Day high / low = extremes of the h1 bars after the previous cash close up to and including this one.
- On the cash-close series: RSI(2) Wilder, SMA(200), SMA(5), ATR(10) Wilder (day high / low, previous cash close).
- Entry: buy at market at the 16:00 ET bar's close when RSI(2) < rsi_lo and cash close > SMA(200).
- Stop: k x ATR(10). No target. Exit flag (long) at a later 16:00 ET bar whose cash close > SMA(5). Time exit 28 calendar days.
params (card defaults): rsi_lo = 10, k = 3.0.
Class C rules, entry blocks, news modes and caps are applied by the engine, not here.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np

_TZ = "America/New_York"
_CASH_CLOSE = 16 * 60
_RSI_N, _SMA_LONG, _SMA_EXIT, _ATR_N = 2, 200, 5, 10
_HOLD_MS = 28 * 86_400_000
_HOUR = 3_600_000
_DAY = 86_400_000


def _local_ms(ms, tzname):
    """Local wall-clock ms for UTC ms (offset looked up once per UTC hour)."""
    tz = ZoneInfo(tzname)
    hours = ms // _HOUR
    uh, inv = np.unique(hours, return_inverse=True)
    off = np.array([int(datetime.fromtimestamp(int(h) * 3600, timezone.utc).astimezone(tz).utcoffset().total_seconds() * 1000)
                    for h in uh], dtype=np.int64)
    return ms + off[inv]


def _wilder(x, n, first):
    """Wilder average of x with the seed = mean of x[first:first+n]; NaN before."""
    out = np.full(len(x), np.nan)
    if len(x) < first + n:
        return out
    out[first + n - 1] = x[first:first + n].mean()
    for j in range(first + n, len(x)):
        out[j] = out[j - 1] + (x[j] - out[j - 1]) / n
    return out


def _sma(x, n):
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        cs = np.r_[0.0, np.cumsum(x)]
        out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def intents(bars, params, ctx):
    rsi_lo = float(params.get("rsi_lo", 10))
    k = float(params.get("k", 3.0))
    n = len(bars["c"])
    side = np.zeros(n, np.int64)
    sl = np.full(n, np.nan)
    hold = np.full(n, np.nan)
    exl = np.zeros(n, bool)
    out = {"side": side, "sl_dist": sl, "hold_ms": hold, "exit_long": exl}
    if n == 0:
        return out
    loc = _local_ms(bars["close_ms"].astype(np.int64), _TZ)
    mod = (loc // 60_000) % 1440
    weekday = ((loc // _DAY) + 3) % 7 < 5
    cc = np.nonzero(weekday & (mod == _CASH_CLOSE))[0]
    m = len(cc)
    if m < 2:
        return out
    c = np.asarray(bars["c"], float)
    C = c[cc]
    starts = np.r_[0, cc[:-1] + 1]
    H = np.maximum.reduceat(np.asarray(bars["h"], float)[: cc[-1] + 1], starts)
    L = np.minimum.reduceat(np.asarray(bars["l"], float)[: cc[-1] + 1], starts)
    # RSI(2), Wilder, on cash closes
    d = np.r_[np.nan, np.diff(C)]
    up = np.where(d > 0, d, 0.0)
    dn = np.where(d < 0, -d, 0.0)
    ag = _wilder(up, _RSI_N, 1)
    al = _wilder(dn, _RSI_N, 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        rsi = np.where(al == 0, 100.0, 100.0 - 100.0 / (1.0 + ag / al))
    rsi[np.isnan(ag)] = np.nan
    # ATR(10), Wilder, on the day bars
    pc = np.r_[np.nan, C[:-1]]
    tr = np.maximum(H - L, np.maximum(np.abs(H - pc), np.abs(L - pc)))
    atr = _wilder(tr, _ATR_N, 1)
    sma_long = _sma(C, _SMA_LONG)
    sma_exit = _sma(C, _SMA_EXIT)
    live = bars["open_ms"][cc] >= ctx["first_ms"]
    entry = live & (rsi < rsi_lo) & (C > sma_long) & np.isfinite(atr) & (atr > 0)
    ei = cc[entry]
    side[ei] = 1
    sl[ei] = k * atr[entry]
    hold[ei] = _HOLD_MS
    exl[cc[C > sma_exit]] = True   # v2: an exit and an entry on the same close: the old trade exits, the new one enters
    return out
