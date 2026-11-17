"""IDEA-3002: Weekly cash-open range-scaled dip buy (card v2, ideas/cards/IDEA-3002-weekly-open-range-dip-buy.md).

Rebuilt from the card's description of the idea source (TradingView "TASC 2026.03 One Percent A Week" by PineCodersTASC); no code copied.
- m30 bars, NY clock. Valid session = a Monday-Friday NY date that is neither a US exchange closure nor an early close (published
  rules, computed below; no file or calendar access) and has a bar opening at 09:30. Cash bars: local open in [09:30, 16:00).
- D20 = mean (high - low) of the cash bars of the previous 20 valid sessions (a session counts only after it is complete).
- Week anchor: the week's first valid session; O_w = its 09:30 bar's open; level L = O_w - k x D20, both fixed at that bar's close.
- v2 (look-ahead review 2026-11-13): the buy limit at L is armed at the close of the 09:30 bar of the anchor session and of every later
  valid session of the same week (to Friday), each time live until 16:00 NY that day (the engine's nightly block would cancel it
  anyway). Arming stops for the week once any closed bar inside an armed window (bars opening >= 10:00 and closing <= 16:00 on an
  armed day) has low <= L: treated as filled, so at most one trade a week.
- Stop s x D20, target t x D20 from the fill. Exit flag at the close of Friday's bar ending 16:00 NY. Long only.
params (card defaults): k = 0.5, t = 0.5, s = 1.0. Class B rules, news modes and caps are applied by the engine.
"""
from datetime import date, timedelta

import numpy as np

from engine.timeutil import local_ms

_TZ = "America/New_York"
_OPEN_MIN = 9 * 60 + 30
_ARM_MIN = 10 * 60
_CLOSE_MIN = 16 * 60
_R_N = 20
_DAY = 86_400_000
_MIN = 60_000


def intents(bars, params, ctx):
    k = float(params.get("k", 0.5))
    t = float(params.get("t", 0.5))
    s = float(params.get("s", 1.0))
    o = np.asarray(bars["o"], float)
    h = np.asarray(bars["h"], float)
    l = np.asarray(bars["l"], float)
    om = np.asarray(bars["open_ms"], np.int64)
    cm = np.asarray(bars["close_ms"], np.int64)
    n = len(o)
    side = np.zeros(n, np.int64)
    otype = np.zeros(n, np.int64)
    price = np.full(n, np.nan)
    sl = np.full(n, np.nan)
    tp = np.full(n, np.nan)
    expiry = np.full(n, np.nan)
    exl = np.zeros(n, bool)
    exs = np.zeros(n, bool)
    out = {"side": side, "otype": otype, "price": price, "sl_dist": sl, "tp_dist": tp, "expiry_ms": expiry,
           "exit_long": exl, "exit_short": exs}
    if n == 0:
        return out

    lo = local_ms(om, _TZ)
    lday = lo // _DAY
    lmin = (lo % _DAY) // _MIN
    lcm = local_ms(cm, _TZ)
    lcday = lcm // _DAY
    lcmin = (lcm % _DAY) // _MIN
    wday = (lday + 3) % 7            # 1970-01-01 was a Thursday; Monday = 0
    week = (lday + 3) // 7
    in_cash = (lmin >= _OPEN_MIN) & (lmin < _CLOSE_MIN)
    # Friday cash-close exit
    exl[in_cash & (wday == 4) & (lcmin == _CLOSE_MIN) & (lcday == lday)] = True

    cash_idx = np.flatnonzero(in_cash)
    if cash_idx.size == 0:
        return out
    hol = _holiday_days(lday[cash_idx])
    days, starts = np.unique(lday[cash_idx], return_index=True)
    ends = np.r_[starts[1:], cash_idx.size]

    first_ms = int(ctx["first_ms"])
    ranges = []
    cur_week = None
    level = d20 = None
    done = True                      # no live week until an anchor is set
    for d, a, b in zip(days, starts, ends):
        ii = cash_idx[a:b]
        wd = int(wday[ii[0]])
        valid = wd <= 4 and int(d) not in hol and lmin[ii[0]] == _OPEN_MIN
        if not valid:
            continue
        ent = ii[0]
        if week[ent] != cur_week:
            # first valid session of a new week: the anchor
            cur_week = week[ent]
            level = d20 = None
            done = True
            if len(ranges) >= _R_N:
                m = float(np.mean(ranges[-_R_N:]))
                if m > 0:
                    d20 = m
                    level = float(o[ent]) - k * d20
                    done = False
        if not done and om[ent] >= first_ms and lcmin[ent] == _ARM_MIN and lcday[ent] == lday[ent]:
            life = (int(lday[ent]) * _DAY + _CLOSE_MIN * _MIN) - int(lcm[ent])
            if life > 0:
                side[ent] = 1
                otype[ent] = 2
                price[ent] = level
                sl[ent] = s * d20
                tp[ent] = t * d20
                expiry[ent] = float(life)
                # armed window today: bars opening >= 10:00 and closing <= 16:00 (closed bars only, used for later days)
                win = ii[(lmin[ii] >= _ARM_MIN) & (lcmin[ii] <= _CLOSE_MIN) & (lcday[ii] == lday[ii])]
                if win.size and float(l[win].min()) <= level:
                    done = True
        # a session counts for D20 only once complete (used from the next session on)
        ranges.append(float(h[ii].max() - l[ii].min()))
    return out


# ---- US exchange closures and early closes from their published rules (no file or calendar access); day numbers since 1970-01-01 ----
_EPOCH = date(1970, 1, 1).toordinal()


def _easter(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    g = (8 * b + 13) // 25
    hh = (19 * a + b - d - g + 15) % 30
    i, kk = c // 4, c % 4
    ll = (32 + 2 * e + 2 * i - hh - kk) % 7
    m = (a + 11 * hh + 22 * ll) // 451
    mo = (hh + ll - 7 * m + 114) // 31
    return date(y, mo, (hh + ll - 7 * m + 114) % 31 + 1)


def _nth(y, mo, wd, nth):
    """nth weekday (0 = Monday) of a month; nth = -1 for the last."""
    if nth > 0:
        x = date(y, mo, 1)
        return x + timedelta(days=(wd - x.weekday()) % 7 + 7 * (nth - 1))
    x = date(y + (mo == 12), mo % 12 + 1, 1) - timedelta(days=1)
    return x - timedelta(days=(x.weekday() - wd) % 7)


def _obs(x):
    """US rule: Saturday -> Friday, Sunday -> Monday."""
    return x - timedelta(days=1) if x.weekday() == 5 else x + timedelta(days=1) if x.weekday() == 6 else x


def _us_closed(y):
    out = {_nth(y, 1, 0, 3), _nth(y, 2, 0, 3), _easter(y) - timedelta(days=2), _nth(y, 5, 0, -1), _obs(date(y, 7, 4)),
           _nth(y, 9, 0, 1), _nth(y, 11, 3, 4), _obs(date(y, 12, 25))}
    if date(y, 1, 1).weekday() != 5:          # NYSE does not move a Saturday New Year to Friday
        out.add(_obs(date(y, 1, 1)))
    if y >= 2022:
        out.add(_obs(date(y, 6, 19)))
    if y == 2018:
        out.add(date(2018, 12, 5))            # national day of mourning (President Bush)
    return out


def _us_early(y):
    closed = _us_closed(y)
    out = {_nth(y, 11, 3, 4) + timedelta(days=1)}
    for x in (date(y, 7, 3), date(y, 12, 24)):
        if x.weekday() < 5 and x not in closed:
            out.add(x)
    return out


def _holiday_days(day):
    if len(day) == 0:
        return set()
    y0 = date.fromordinal(int(np.min(day)) + _EPOCH).year - 1
    y1 = date.fromordinal(int(np.max(day)) + _EPOCH).year + 1
    return {x.toordinal() - _EPOCH for y in range(y0, y1 + 1) for fn in (_us_closed, _us_early) for x in fn(y)}
