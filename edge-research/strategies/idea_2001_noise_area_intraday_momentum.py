"""IDEA-2001: noise-area intraday momentum on US index CFDs (card, ideas/cards/IDEA-2001-noise-area-intraday-momentum.md).

Rules rebuilt from the card (Zarattini, Aziz, Barbon; band-only version, no VWAP); no code copied.
- m15 bars, New York clock. Open = open of the m15 bar starting 09:30 ET. Prior close = close of the bar ending 16:00 ET on the
  previous trading day that has one.
- Decision times t = 10:00, 10:30, ..., 15:30 ET (closes of m15 bars on the 30-min grid).
  sigma(t) = mean over the previous N trading days (today excluded) of |close at t / that day's Open - 1|.
  Upper(t) = max(Open, prior close) * (1 + m sigma(t));  Lower(t) = min(Open, prior close) * (1 - m sigma(t)).
- At a decision bar: close > Upper -> buy intent; close < Lower -> sell intent (dropped by the engine while a position is open).
  A long exits at a decision bar that closes below Upper; a short exits at one that closes above Lower (exit flags). A long whose bar
  closes below Lower exits and the sell intent of the same bar reverses it (exit and entry share a tick, CONVENTIONS.md).
- Stop: s * m * sigma(t) * Open from the fill. Exit flags at the close of the bar ending 16:00 ET.
params (card defaults): N = 14, m = 1.0, s = 1.0.
Class A flat times, entry blocks, news modes and the daily trade cap are applied by the engine, not here.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np

_TZ = "America/New_York"
_OPEN_MIN = 9 * 60 + 30
_CLOSE_MIN = 16 * 60
_DECISION_MINS = tuple(range(10 * 60, 15 * 60 + 31, 30))  # 10:00 .. 15:30 (bar close times)


def _local_ms(ms, tzname):
    """Local wall-clock ms for UTC ms (offset looked up once per UTC hour)."""
    tz = ZoneInfo(tzname)
    hours = ms // 3_600_000
    uh, inv = np.unique(hours, return_inverse=True)
    off = np.array([int(datetime.fromtimestamp(int(h) * 3600, timezone.utc).astimezone(tz).utcoffset().total_seconds() * 1000)
                    for h in uh], dtype=np.int64)
    return ms + off[inv]


def intents(bars, params, ctx):
    N = int(params.get("N", 14))
    m = float(params.get("m", 1.0))
    s = float(params.get("s", 1.0))
    o, c = bars["o"], bars["c"]
    n = len(c)
    side = np.zeros(n, np.int64)
    sl = np.full(n, np.nan)
    exl = np.zeros(n, bool)
    exs = np.zeros(n, bool)
    out = {"side": side, "sl_dist": sl, "exit_long": exl, "exit_short": exs}
    if n == 0:
        return out
    open_loc = _local_ms(bars["open_ms"].astype(np.int64), _TZ)
    close_loc = _local_ms(bars["close_ms"].astype(np.int64), _TZ)
    oday = open_loc // 86_400_000
    omin = (open_loc // 60_000) % 1440
    cday = close_loc // 86_400_000
    cmin = (close_loc // 60_000) % 1440

    open_idx = {int(oday[i]): i for i in np.nonzero(omin == _OPEN_MIN)[0]}
    close_idx = {int(cday[i]): i for i in np.nonzero(cmin == _CLOSE_MIN)[0]}
    dec_idx = {}
    for i in np.nonzero(np.isin(cmin, _DECISION_MINS))[0]:
        dec_idx.setdefault(int(cday[i]), {})[int(cmin[i])] = i

    prev_close = None
    moves = {t: [] for t in _DECISION_MINS}  # per time of day: past |close_t / Open - 1|, oldest first
    for d in sorted(set(open_idx) | set(close_idx)):
        io = open_idx.get(d)
        jc = close_idx.get(d)
        decs = dec_idx.get(d, {})
        if io is not None:
            day_open = o[io]
            for t in _DECISION_MINS:
                i = decs.get(t)
                if i is None or i < io:
                    continue
                past = moves[t]
                if prev_close is not None and len(past) >= N and bars["open_ms"][i] >= ctx["first_ms"]:
                    sig = float(np.mean(past[-N:]))
                    up = max(day_open, prev_close) * (1.0 + m * sig)
                    lo = min(day_open, prev_close) * (1.0 - m * sig)
                    x = c[i]
                    exl[i] = x < up
                    exs[i] = x > lo
                    if x > up:
                        side[i] = 1
                    elif x < lo:
                        side[i] = -1
                    if side[i] != 0:
                        sl[i] = s * m * sig * day_open
            for t in _DECISION_MINS:  # today's moves join the history only after today's decisions
                i = decs.get(t)
                if i is not None and i >= io:
                    moves[t].append(abs(c[i] / day_open - 1.0))
        if jc is not None:
            exl[jc] = True
            exs[jc] = True
            prev_close = c[jc]
    return out
