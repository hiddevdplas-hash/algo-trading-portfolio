"""Inputs a strategy reads besides its own bars (DESIGN A14): context symbols (§1), later outside series (§2).

Context symbols (A14.1)
  A card declares up to 3 store symbols as inputs (`| context symbols | US500, STOXX50 |`, or `none`); the job's "context" list must
  equal the card's. They are never traded and never a grid axis. The runner hands the module, per context symbol, that symbol's bars
  of the job's timeframe ALIGNED to the traded bars:
      ctx["context"][SYM] = {"open_ms", "close_ms", "age_ms", "o", "h", "l", "c"}      (arrays of len(bars["c"]))
  element i = the last context bar whose close_ms <= the traded bar i's close_ms (the moment bar i's decision is made); age_ms =
  bars["close_ms"][i] - that close_ms. No interpolation, no bar that closes later. Where the context market is shut on schedule
  (other sessions, weekends, holidays) the value is the stale last closed bar and age_ms says how old it is. close_ms is the bar's
  nominal close (open + timeframe), so a bar cut short by its market's close becomes visible at its nominal close, never earlier.
  NaN prices and close_ms / open_ms / age_ms -1 (DESIGN A14.1.2): before the context history starts (e.g. DE40 2021-09, oil 2017-07)
  and inside its data holes, from the hole's start until the first context bar after it has closed. A data hole = a break of
  >= 2 h that is no weekend, holiday or regular daily break (the A8.8 classification, as in tools/gapcheck; copied here so the
  engine hash covers it), or any silence over 3.5 days that spans no holiday (e.g. 10-19 Oct 2014). Breaks are found on the context
  symbol's m1 bars. Asian holidays are not in the holiday list, so HK50 / JP225 / AUS200 holidays count as holes (NaN): conservative.
  An FX context bar inside the FX quarantine (May-Jul 2015, DESIGN §3.3) is NaN too.
  No tick volume (DESIGN §5, A13) and no raw (unaligned) context bars are handed over.
"""
import re
from datetime import date, datetime, timedelta
from functools import lru_cache

import numpy as np

from engine import data, rules as RU, store

MAX_CONTEXT = 3
CARD_ROW = "context symbols"
SERIES_ROW = "outside series"


def card_context(text):
    """The card's declared context symbols: None if the card has no `| context symbols |` row, [] for `none`, else the list.
    A row given twice, an unknown store symbol or more than MAX_CONTEXT symbols is refused (ValueError)."""
    found = None
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 2:
            continue
        key = cells[0].lower()
        if key != CARD_ROW and not key.startswith(CARD_ROW + " ("):
            continue
        if found is not None:
            raise ValueError(f"card: '{CARD_ROW}' is given twice")
        v = cells[1].strip()
        found = [] if v.lower() == "none" else [x for x in re.split(r"[,\s]+", v) if x]
    if found:
        check_context(found)
    return found


def card_series(text):
    """The card's declared outside series (A14 §2): None without a `| outside series |` row, [] for `none`, else the names
    (separated by ';'), each a known series (engine.series.parse_name). A row given twice is refused."""
    from engine import series as SR
    found = None
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 2:
            continue
        key = cells[0].lower()
        if key != SERIES_ROW and not key.startswith(SERIES_ROW + " ("):
            continue
        if found is not None:
            raise ValueError(f"card: '{SERIES_ROW}' is given twice")
        v = cells[1].strip().strip("`")
        found = [] if v.lower() == "none" else [x.strip().strip("`") for x in v.split(";") if x.strip()]
    for n in found or []:
        SR.parse_name(n)
    if found and len(set(found)) != len(found):
        raise ValueError(f"card: outside series repeat: {found}")
    return found


def check_context(syms, traded=()):
    if not isinstance(syms, list) or not all(isinstance(s, str) for s in syms):
        raise ValueError(f"context must be a list of store symbol names, not {syms!r}")
    if len(syms) > MAX_CONTEXT:
        raise ValueError(f"at most {MAX_CONTEXT} context symbols (A14.1), not {len(syms)}")
    if len(set(syms)) != len(syms):
        raise ValueError(f"context symbols repeat: {syms}")
    both = sorted(set(syms) & set(traded))
    if both:
        raise ValueError(f"{both}: a context symbol is never traded (A14.1); it is also a traded symbol of the job")
    for s in syms:
        try:
            store.store_meta(s)
        except (FileNotFoundError, OSError):
            raise ValueError(f"context symbol {s!r} is not in the research store (key on the store's names, e.g. STOXX50)")
    return syms


# ------------------------------------------------------------------ data holes (A8.8 classification, from tools/gapcheck)
def _easter(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    n = h + l_ - 7 * m + 114
    return date(y, n // 31, n % 31 + 1)


def _nth(y, m, wd, n):
    d = date(y, m, 1)
    return d + timedelta((wd - d.weekday()) % 7 + 7 * (n - 1))


def _last(y, m, wd):
    d = (date(y, m + 1, 1) if m < 12 else date(y + 1, 1, 1)) - timedelta(1)
    return d - timedelta((d.weekday() - wd) % 7)


def _holidays(y0=2010, y1=2025):
    out = set()
    for y in range(y0, y1 + 1):
        e = _easter(y)
        out |= {date(y, 1, 1), date(y, 1, 2), date(y, 12, 24), date(y, 12, 25), date(y, 12, 26), date(y, 12, 27), date(y, 12, 28),
                date(y, 12, 31), e - timedelta(2), e + timedelta(1), date(y, 5, 1),
                _nth(y, 1, 0, 3), _nth(y, 2, 0, 3), _last(y, 5, 0), date(y, 7, 3), date(y, 7, 4), date(y, 7, 5), _nth(y, 9, 0, 1),
                _nth(y, 11, 3, 4), _nth(y, 11, 3, 4) + timedelta(1), _nth(y, 5, 0, 1), _last(y, 8, 0)}
        if y >= 2022:
            out |= {date(y, 6, 19), date(y, 6, 20)}
    out |= {date(2018, 12, 5), date(2025, 1, 9), date(2020, 5, 8), date(2022, 6, 2), date(2022, 6, 3), date(2022, 9, 19),
            date(2023, 5, 8), date(2016, 6, 24)}
    return out


HOLIDAYS = _holidays()
HOLE_DAYS = 3.5


def gap_kind(close, reopen, regular):
    d0 = datetime.fromtimestamp(close / 1000, RU.AMS).date()
    d1 = datetime.fromtimestamp(reopen / 1000, RU.AMS).date()
    days = [d0 + timedelta(i) for i in range((d1 - d0).days + 1)]
    hol = any(d in HOLIDAYS for d in days)
    if reopen - close > HOLE_DAYS * 86_400_000 and not hol:
        return "hole"
    if d0.weekday() == 4 or any(d.weekday() == 5 for d in days[:-1]):
        return "weekend"
    if regular:
        return "regular"
    return "holiday" if hol else "hole"


@lru_cache(maxsize=None)
def holes(symbol):
    """(start, end) of the symbol's data holes, from its m1 bars: start = the end of the last minute with data, end = the next
    bar's open."""
    b = data.bars(symbol, "m1")
    o = np.asarray(b["open_ms"], np.int64)
    k = np.flatnonzero(np.diff(o) - RU.MIN >= RU.DAILY_REF_GAP)
    c, r = o[k] + RU.MIN, o[k + 1]
    out = [(cc, rr) for cc, rr, reg in RU.breaks_from_gaps(c, r) if gap_kind(cc, rr, reg) == "hole"]
    return np.asarray(out, np.int64).reshape(-1, 2)


def align(ctx_bars, close_ms, hole_list=None):
    """ctx_bars: a context symbol's bars (data.bars), close_ms: the traded bars' close times. Returns the aligned dict; inside a
    hole (hole_list rows (start, end)) the value is NaN until the first context bar after the hole has closed."""
    cc = np.asarray(ctx_bars["close_ms"], np.int64)
    co = np.asarray(ctx_bars["open_ms"], np.int64)
    close_ms = np.asarray(close_ms, np.int64)
    idx = np.searchsorted(cc, close_ms, side="right") - 1
    ok = idx >= 0
    if hole_list is not None and len(hole_list) and len(cc):
        for start, _ in hole_list:
            k = int(np.searchsorted(co, start, side="left")) - 1          # last context bar with data before the hole
            if k >= 0:
                ok &= ~((idx == k) & (close_ms > start))
    j = np.where(ok, idx, 0)
    out = {"close_ms": np.where(ok, cc[j] if len(cc) else -1, -1).astype(np.int64),
           "open_ms": np.where(ok, co[j] if len(cc) else -1, -1).astype(np.int64)}
    out["age_ms"] = np.where(ok, close_ms - out["close_ms"], -1).astype(np.int64)
    for k in ("o", "h", "l", "c"):
        v = np.asarray(ctx_bars[k], float)
        out[k] = np.where(ok, v[j] if len(v) else np.nan, np.nan)
    return out


def context(symbols, tf, close_ms, end_ms):
    """{SYM: aligned bars} for the job's context symbols; context bars that close after end_ms are never used."""
    out = {}
    for s in symbols:
        b = data.bars(s, tf)
        keep = b["close_ms"] <= end_ms
        a = align({k: v[keep] for k, v in b.items()}, close_ms, holes(s))
        q = data.quarantine_mask(s, a["open_ms"]) & (a["open_ms"] >= 0)        # FX May-Jul 2015 (DESIGN §3.3): suspect, NaN
        if q.any():
            for k in ("o", "h", "l", "c"):
                a[k] = np.where(q, np.nan, a[k])
            for k in ("open_ms", "close_ms", "age_ms"):
                a[k] = np.where(q, -1, a[k])
        out[s] = a
    return out
