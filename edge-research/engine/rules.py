"""Rules layer (DESIGN §4.2, §3.6): turns the card's class, the symbol's trading hours and the news calendar into the kernel's
rule inputs. Same rules for every strategy; nothing here is tuned. Times are real time zones per date (Amsterdam and New York
change clocks on different dates).

  class A   flat at 22:45 Amsterdam every day, earlier (close - 5 min) when the symbol's session closes before that into a break
            of >= 2 h (DESIGN A8)
  class B   flat on the last session before every break of >= 2 h except the symbol's regular daily break (weekends, holiday
            closures, early closes): 22:45 Amsterdam or close - 5 min, whichever is earlier (DESIGN A8.2, A8.6)
  class C   no flat
  entries   blocked 22:45 -> 00:15 Amsterdam, and in the 2 h before a market close starting a break of >= 2 h
  closes    the end of trading before each break: the exported scheduled close, or the last tick + 1 min when trading stopped
            earlier. The exported hours are one fixed weekly schedule: they miss the weeks when only the US is on summer time,
            holiday early closes and holiday closures (A8.5).
  news      modes M0-M3 (§3.6): tier 1 -> flatten (far-stop exemption) in M1-M3; tier 2 -> hold without target in M2,
            flatten in M3, free in M1; nothing in M0. Windows: releases T-6 -> T+6 min; speeches, press conferences, testimony
            T-6 -> end + 5 min; events without a fixed time cover their whole release range.
  caps      <= 10 entries per Amsterdam day; <= 2 order events (entries going live, exits) per 60 s.
The look-ahead rule "no strategy may enter because news is coming" is checked by the look-ahead reviewer, not here.
"""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np

AMS = ZoneInfo("Europe/Amsterdam")
MIN = 60_000
HOUR = 3_600_000
CLASSES = ("A", "B", "C")
MODES = ("M0", "M1", "M2", "M3")
MAX_PER_DAY = 10
MAX_ORDERS_60S = 2
PRE = 6 * MIN                       # window opens T - 6 min
POST_RELEASE = 6 * MIN              # ... closes T + 6 min (DESIGN A6: talks with an official start too)
POST_TALK = 5 * MIN                 # ... and end + 5 min for talks without an official start (whole usual range, A5.2 / A6.2)
FLAT_BEFORE_CLOSE = 5 * MIN         # A8: class A / B flat 5 min before a close that starts a break of >= 2 h
MIN_BREAK = 2 * HOUR
# A8.6 regular daily break: starts Mon-Thu (Amsterdam) and matches the symbol's own recent daily breaks: at least DAILY_MIN_MATCH
# gaps of >= DAILY_REF_GAP that started Mon-Thu in the previous DAILY_LOOKBACK, with a close within DAILY_TOL (Amsterdam time of
# day) and a length within DAILY_TOL. Only the past is used; the reference follows schedule changes and clock changes.
DAILY_REF_GAP = 30 * MIN
DAILY_TOL = 61 * MIN                # "within 1 h"; + 1 min because a close from the ticks carries up to 1 min of rounding
DAILY_LOOKBACK = 14 * 24 * HOUR
DAILY_MIN_MATCH = 3
TALK_KINDS = ("speech", "press_conference", "testimony")
# FundingPips' whole-event rule (DESIGN A6.4), for the FundingPips firm simulation and live cBot only: T-6 -> end + 5 min, the official
# end where known, else these assumed lengths. Research windows (event_window) no longer use an event's end.
FP_ASSUMED_END = {"speech": 90 * MIN, "press_conference": 90 * MIN, "testimony": 210 * MIN}

# DESIGN §3.6 item 4: which symbols an event of a currency blocks (besides that currency's FX pairs). Store names.
EXTRA = {"USD": ("XAUUSD", "XAGUSD", "US30", "US500", "USTEC"), "EUR": ("DE40", "STOXX50"), "GBP": ("UK100",), "JPY": ("JP225",),
         "OIL": ("XTIUSD", "XBRUSD")}
FX_CCYS = ("EUR", "USD", "GBP", "JPY", "CHF", "AUD", "NZD", "CAD")


def _days(first_ms, end_ms):
    d = datetime.fromtimestamp(first_ms / 1000, timezone.utc).date() - timedelta(days=1)
    last = datetime.fromtimestamp(end_ms / 1000, timezone.utc).date() + timedelta(days=1)
    while d <= last:
        yield d
        d += timedelta(days=1)


def ams_ms(d: date, hh, mm):
    return int(datetime(d.year, d.month, d.day, hh, mm, tzinfo=AMS).timestamp() * 1000)


def class_flats(cls, first_ms, end_ms, breaks=()):
    """Flat times of a strategy class within [first_ms, end_ms). breaks: (close, reopen, regular_daily) from market_breaks.
    DESIGN §5 + A8: A flat daily at 22:45 Amsterdam, and at close - 5 min where that is earlier, before every break of >= 2 h;
    B before every break of >= 2 h that is not the symbol's regular daily break, at the same time."""
    if cls not in CLASSES:
        raise ValueError(cls)
    if cls == "C":
        return np.zeros(0, np.int64)
    out = {ams_ms(d, 22, 45) for d in _days(first_ms, end_ms)} if cls == "A" else set()
    for c, _, regular in breaks:
        if cls == "B" and regular:
            continue
        x = int(c) - FLAT_BEFORE_CLOSE
        d = datetime.fromtimestamp(x / 1000, AMS).date()
        out.add(min(x, ams_ms(d, 22, 45)))
    return np.asarray(sorted(x for x in out if first_ms <= x < end_ms), np.int64)


def nightly_blocks(first_ms, end_ms):
    """[22:45, 00:15 next day) Amsterdam, every day."""
    out = [(ams_ms(d, 22, 45), ams_ms(d + timedelta(days=1), 0, 15)) for d in _days(first_ms, end_ms)]
    return [(s, e) for s, e in out if e > first_ms and s < end_ms]


def _close_at(t, close_ms, k):
    """End of trading before the gap after tick k (A8.5): the scheduled close when it falls within 1 min after the last tick, else
    the last tick + 1 min."""
    c = int(t[k]) + MIN
    if close_ms is not None and t[k] <= close_ms[k] < c:
        c = int(close_ms[k])
    return c


def market_breaks(t, close_ms, min_break=MIN_BREAK):
    """(close, reopen, regular_daily) of every market break of >= 2 h (DESIGN §5, A8). close: _close_at (trading stopped before the
    scheduled close in US-only summer time weeks, holiday early closes and closures, data holes: the exported hours are one fixed
    weekly schedule). The reopening is the next tick. regular_daily (A8.6): see DAILY_* above."""
    t = np.asarray(t, np.int64)
    if len(t) < 2:
        return []
    ks = np.flatnonzero(np.diff(t) >= min(DAILY_REF_GAP, min_break))
    if not len(ks):
        return []
    c = np.asarray([_close_at(t, close_ms, k) for k in ks], np.int64)
    return breaks_from_gaps(c, t[ks + 1], min_break)


def breaks_from_gaps(c, r, min_break=MIN_BREAK):
    """market_breaks on the gaps of >= DAILY_REF_GAP already found: c = closes (_close_at), r = reopenings, both sorted."""
    c, r = np.asarray(c, np.int64), np.asarray(r, np.int64)
    dur = r - c
    loc = [datetime.fromtimestamp(x / 1000, AMS) for x in c]
    tod = np.asarray([d.hour * 60 + d.minute + d.second / 60 for d in loc]) * MIN
    wkday = np.asarray([d.weekday() <= 3 for d in loc])
    out = []
    for i in np.flatnonzero(dur >= min_break):
        regular = False
        if wkday[i]:
            j0 = int(np.searchsorted(c, c[i] - DAILY_LOOKBACK))
            dt = np.abs(tod[j0:i] - tod[i])
            dt = np.minimum(dt, 24 * HOUR - dt)
            m = wkday[j0:i] & (dur[j0:i] >= DAILY_REF_GAP) & (dt <= DAILY_TOL) & (np.abs(dur[j0:i] - dur[i]) <= DAILY_TOL)
            regular = int(m.sum()) >= DAILY_MIN_MATCH
        out.append((int(c[i]), int(r[i]), bool(regular)))
    return out


def preclose_blocks(t, close_ms, min_close=MIN_BREAK, before=2 * HOUR):
    """[close - 2 h, close) before every market break of >= 2 h (closes from market_breaks), daily ones included."""
    return [(c - before, c) for c, _, _ in market_breaks(t, close_ms, min_close)]


def merge(intervals):
    """Union of [start, end) intervals -> sorted, non-overlapping (start, end) arrays."""
    iv = sorted((int(s), int(e)) for s, e in intervals if e > s)
    out = []
    for s, e in iv:
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    a = np.asarray(out, np.int64).reshape(-1, 2)
    return a[:, 0].copy(), a[:, 1].copy()


def blocks_symbol(ccy, symbol):
    """DESIGN §3.6 item 4."""
    if ccy in EXTRA and symbol in EXTRA[ccy]:
        return True
    return len(symbol) == 6 and symbol[:3] in FX_CCYS and symbol[3:] in FX_CCYS and ccy in (symbol[:3], symbol[3:])


def event_window(ev):
    """[open, close) of one event in the research modes. ev: dict with start_ms, kind, tier, ccy, type_id, optional end_ms and
    'range' (True when the event has no official start and start_ms / end_ms span its usual range: engine/news.py).
    DESIGN A6: every event with an official start is blocked T-6 -> T+6 around that start, talks included (their end is not used);
    events without one keep the whole range: talks to end + 5 min (A5.2), releases (BoJ decisions) to end + 6 min (§3.6)."""
    s = int(ev["start_ms"])
    if ev.get("range"):
        end = int(ev.get("end_ms") or s)
        return s - PRE, end + (POST_TALK if ev["kind"] in TALK_KINDS else POST_RELEASE)
    return s - PRE, s + POST_RELEASE


def event_window_fundingpips(ev):
    """FundingPips' whole-event window (DESIGN A6.4) for its firm simulation and live cBot, not for research: talks T-6 -> end + 5 min
    (official end, else FP_ASSUMED_END); everything else as event_window."""
    if ev["kind"] not in TALK_KINDS or ev.get("range"):
        return event_window(ev)
    s = int(ev["start_ms"])
    end = ev.get("end_ms")
    end = int(end) if end is not None else s + FP_ASSUMED_END[ev["kind"]]
    return s - PRE, end + POST_TALK


def news_windows(events, symbol, mode, far=None, price_at=None):
    """Kernel news windows for one symbol and mode. far: {(symbol, type_id): threshold} for the far-stop exemption (1.5 x the 99th
    percentile high-low range in that window, measured 2014-11 -> 2024-12; engine/news.py); a missing entry = no exemption. With
    price_at (UTC ms -> price) the thresholds are bp of price, converted at each window's opening; without it, price units.
    Overlapping windows are merged: flatten wins over hold; the far-stop threshold of a merged window is the largest of its
    flatten events, or none if any of them has none."""
    if mode not in MODES:
        raise ValueError(mode)
    far = far or {}
    raw = []
    for ev in events or ():
        if not blocks_symbol(ev["ccy"], symbol):
            continue
        tier = int(ev["tier"])
        if mode == "M0" or (mode == "M1" and tier == 2):
            continue
        kind = 1 if (tier == 1 or mode == "M3") else 2
        o, c = event_window(ev)
        f = far.get((symbol, ev["type_id"]), np.nan)
        if price_at is not None and f == f:
            f = f / 1e4 * float(price_at(o))
        raw.append((o, c, kind, f))
    raw.sort()
    out = []
    for o, c, kind, f in raw:
        if out and o < out[-1][1]:
            w = out[-1]
            w[1] = max(w[1], c)
            if kind == 1:
                w[3] = f if w[2] == 2 else (np.nan if (np.isnan(w[3]) or np.isnan(f)) else max(w[3], f))
                w[2] = 1
        else:
            out.append([o, c, kind, f])
    if not out:
        z = np.zeros(0, np.int64)
        return z, z.copy(), z.copy(), np.zeros(0)
    a = np.asarray([(o, c, k) for o, c, k, _ in out], np.int64)
    return a[:, 0].copy(), a[:, 1].copy(), a[:, 2].copy(), np.asarray([w[3] for w in out], float)


def day_starts(first_ms, end_ms):
    return np.asarray([ams_ms(d, 0, 0) for d in _days(first_ms, end_ms)], np.int64)


def build(symbol, cls, mode, ticks, events=None, far=None):
    """Kernel keyword arguments for one run (strategy class, news mode) on fill-ready ticks (engine.data.FillTicks), plus info:
    the share of trading time where entries are blocked, per reason."""
    return build_parts(symbol, cls, mode, ticks.t, market_breaks(ticks.t, ticks.close_ms), events, far)


def build_parts(symbol, cls, mode, t, breaks, events=None, far=None, price_at=None):
    """As build(), with the market breaks computed beforehand (the runner computes them once per symbol): the 2-h pre-close entry
    blocks and the class flats both come from them (A8)."""
    first, end = int(t[0]), int(t[-1]) + 1
    night = nightly_blocks(first, end)
    pre = [(c - 2 * HOUR, c) for c, _, _ in breaks if c > first and c - 2 * HOUR < end]
    bs, be = merge(night + pre)
    ws, we, wk, wf = news_windows(events, symbol, mode, far, price_at)
    kw = dict(flat_ms=class_flats(cls, first, end, breaks), blk_start=bs, blk_end=be, win_start=ws, win_end=we, win_kind=wk, win_far=wf,
              day_start=day_starts(first, end), max_per_day=MAX_PER_DAY, max_orders_60s=MAX_ORDERS_60S)
    info = {"class": cls, "mode": mode, "flats": int(len(kw["flat_ms"])), "entry_blocks": int(len(bs)), "news_windows": int(len(ws)),
            "blocked_time_share": {"night_and_preclose": blocked_share(first, end, bs, be), "news": blocked_share(first, end, ws, we)}}
    return kw, info


def blocked_share(first_ms, end_ms, s, e):
    """Share of the period's time inside the intervals (calendar time; cheap: no tick scan)."""
    if not len(s) or end_ms <= first_ms:
        return 0.0
    cov = np.clip(np.minimum(e, end_ms) - np.maximum(s, first_ms), 0, None).sum()
    return round(float(cov / (end_ms - first_ms)), 5)


def blocked_tick_share(t, s, e, step=50):
    """Share of ticks (every step-th) inside [s, e) intervals: the share of active trading time a mode's windows remove."""
    if not len(s) or not len(t):
        return 0.0
    x = np.asarray(t)[::step]
    i = np.searchsorted(e, x, side="right")
    inside = (i < len(s)) & (s[np.minimum(i, len(s) - 1)] <= x)
    return round(float(inside.mean()), 5)


# ---- reporting rules applied to the trade list (DESIGN §4.2) ---------------------------------------------------------------
def hold_report(entry_t, exit_t):
    """Share of trades held under 2 min (> 10% fails) and the median hold (>= 15 min reported)."""
    h = (np.asarray(exit_t) - np.asarray(entry_t)) / MIN
    if not len(h):
        return {"n": 0, "share_under_2min": 0.0, "median_min": None, "fail_under_2min": False}
    share = float((h < 2).mean())
    return {"n": int(len(h)), "share_under_2min": round(share, 4), "median_min": round(float(np.median(h)), 2),
            "fail_under_2min": share > 0.10, "median_below_15min": float(np.median(h)) < 15}
