"""IDEA-2013: MAC(5) multi-day reversal in non-US index CFDs (card v1,
ideas/cards/IDEA-2013-mac5-multiday-reversal-nonus-indices.md).

Rule rebuilt from the card (Baltussen, van Bekkum & Da, "Indexing and stock market serial dependence around the world",
JFE 2019, Eq. (2)); no code copied.
- m15 bars. One daily mark per symbol: the close of the m15 bar ending at the cash close, local clock:
  UK100 16:30 Europe/London, STOXX50 17:30 Europe/Berlin, JP225 15:00 Asia/Tokyo (15:30 from 2024-11-05, TSE session change).
  A day counts if that bar exists (open and close on the same local date). UK100 / STOXX50: 24 and 31 Dec never count.
- r_d = C_d / C_(d-1) - 1 over consecutive counted days. S_d = 4 r_d + 3 r_(d-1) + 2 r_(d-2) + r_(d-3).
  sigma_d = sample SD of the last 60 r (r_d included). z_d = S_d / (sigma_d * sqrt(30)).
- z >= z_min: sell; z <= -z_min: buy (long_only = 1: buys only). Entry at market at the close of the mark bar.
- Stop 3.0 x sigma_d x C_d. No target. Exit at the next counted mark bar (exit flags on every counted mark bar, the new
  signal may enter on the same bar); backstop time exit 6 days.
params (card defaults): z_min = 0.5, long_only = 0.
Class C rules, entry blocks, news modes and caps are applied by the engine, not here.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np

_HOUR = 3_600_000
_DAY = 86_400_000
_SIG_N = 60
_K_STOP = 3.0
_HOLD_MS = 6 * _DAY
_W = np.array([4.0, 3.0, 2.0, 1.0])          # weights on r_d, r_(d-1), r_(d-2), r_(d-3)
_TSE_SWITCH_DAY = (datetime(2024, 11, 5) - datetime(1970, 1, 1)).days   # local day number from which JP close = 15:30

# symbol -> (time zone, close minute of day, skip 24/31 Dec)
_SESS = {
    "UK100": ("Europe/London", 16 * 60 + 30, True),
    "STOXX50": ("Europe/Berlin", 17 * 60 + 30, True),
    "JP225": ("Asia/Tokyo", 15 * 60, False),
}


def _local_ms(ms, tzname):
    """Local wall-clock ms for UTC ms (offset looked up once per UTC hour)."""
    tz = ZoneInfo(tzname)
    hours = ms // _HOUR
    uh, inv = np.unique(hours, return_inverse=True)
    off = np.array([int(datetime.fromtimestamp(int(h) * 3600, timezone.utc).astimezone(tz).utcoffset().total_seconds() * 1000)
                    for h in uh], dtype=np.int64)
    return ms + off[inv]


def intents(bars, params, ctx):
    z_min = float(params.get("z_min", 0.5))
    long_only = int(params.get("long_only", 0))
    n = len(bars["c"])
    side = np.zeros(n, np.int64)
    sl = np.full(n, np.nan)
    hold = np.full(n, np.nan)
    exl = np.zeros(n, bool)
    exs = np.zeros(n, bool)
    out = {"side": side, "sl_dist": sl, "hold_ms": hold, "exit_long": exl, "exit_short": exs}
    sess = _SESS.get(str(ctx.get("symbol", "")))
    if n == 0 or sess is None:
        return out
    tzname, close_min, skip_dec = sess
    open_ms = np.asarray(bars["open_ms"], np.int64)
    close_ms = np.asarray(bars["close_ms"], np.int64)
    lo_open = _local_ms(open_ms, tzname)
    lo_close = _local_ms(close_ms, tzname)
    o_day = lo_open // _DAY
    c_day = lo_close // _DAY
    c_mod = (lo_close // 60_000) % 1440
    want = np.full(n, close_min, np.int64)
    if tzname == "Asia/Tokyo":
        want[c_day >= _TSE_SWITCH_DAY] = 15 * 60 + 30
    mark = (o_day == c_day) & (c_mod == want)
    if skip_dec:
        d64 = c_day.astype("datetime64[D]")
        month = (d64.astype("datetime64[M]").astype(np.int64) % 12) + 1
        dom = (d64 - d64.astype("datetime64[M]")).astype(np.int64) + 1
        mark &= ~((month == 12) & ((dom == 24) | (dom == 31)))
    db = np.nonzero(mark)[0]
    m = len(db)
    if m == 0:
        return out
    exl[db] = True                                   # every counted mark ends the one-day hold
    exs[db] = True
    C = np.asarray(bars["c"], float)[db]
    r = np.full(m, np.nan)
    r[1:] = C[1:] / C[:-1] - 1.0
    S = np.full(m, np.nan)
    sig = np.full(m, np.nan)
    for j in range(_SIG_N, m):                       # r[1..j] exist; window r[j-59..j] uses marks <= j only
        S[j] = _W @ r[j - 3:j + 1][::-1]
        sig[j] = np.std(r[j - _SIG_N + 1:j + 1], ddof=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        z = S / (sig * np.sqrt(30.0))
    live = open_ms[db] >= ctx["first_ms"]
    ok = live & np.isfinite(z) & (sig > 0)
    shorts = ok & (z >= z_min) & (long_only == 0)
    longs = ok & (z <= -z_min)
    side[db[longs]] = 1
    side[db[shorts]] = -1
    ent = longs | shorts
    sl[db[ent]] = _K_STOP * sig[ent] * C[ent]
    hold[db[ent]] = _HOLD_MS
    return out
