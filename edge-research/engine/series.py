"""Outside data series (DESIGN A14 §2, draft): values with a public release time, visible to a module only from the first bar that
closes after that release; cut at the research end (release <= 2024-12-31 23:59:59 UTC). Rule-derived calendars need no download.

COT (CFTC Commitments of Traders; Legacy, Disaggregated, TFF; futures only)
  Values are as of a Tuesday (a Monday in weeks whose Tuesday is a federal holiday) and released at 15:30 New York time. Release
  date: the Friday of the as-of week, moved later by one business day for every federal holiday or federal closure on the
  Wednesday, Thursday or Friday of that week (the processing days). That rule is never earlier than CFTC's published schedules
  (checked against 2014-12 -> 2015-12 and 2026: it equals them, except weeks where a mid-week holiday did not delay CFTC, e.g.
  Veterans Day 2015; there it is later, the A14 "later candidate"). Explicit overrides, from cftc.gov:
    - shutdown 2013 (PR 6745-13): first catch-up 2013-10-25, two in the week of 28 Oct, two in the week of 4 Nov, schedule
      resumed 2013-11-08; the later end of each week is used;
    - shutdown 2018-19 (PR 7864-19): from 2019-02-01 one report each Tuesday and Friday in date order until current (2019-03-08);
    - ION cyber incident 2023 (COT Historical Special Announcements): the delayed reports' actual dates;
    - weeks CFTC revised after release (Historical Special Announcements): release = the revision date, since the files hold the
      revised values (current vintage, not point-in-time: A14 §2).
  Values in the files are CFTC's current vintage, not as first published (A14 §2).

Calendars (rule-derived, known in advance)
  third Friday of each month (US equity index options expiry; the Thursday before when the exchange is shut that Friday),
  quarterly expiry / S&P index rebalance (March, June, September, December third Fridays), and the equity index futures roll
  date (8 calendar days before the quarterly expiry, a Thursday).
"""
import datetime as dt
import glob
import hashlib
import os
import re
from functools import lru_cache

import numpy as np

from engine.timeutil import NY

RESEARCH_END_MS = int(dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)     # releases strictly before this
SERIES_ROOT = os.path.expanduser("~/Projects/Algo Trading/data/series-2014-2024")     # built by tools/series; raw files outside it
D = dt.date


# ------------------------------------------------------------------ US federal holidays and closures
def _nth_weekday(y, m, wd, n):
    d = D(y, m, 1)
    d += dt.timedelta(days=(wd - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


def _last_weekday(y, m, wd):
    d = D(y, m + 1, 1) - dt.timedelta(days=1) if m < 12 else D(y, 12, 31)
    return d - dt.timedelta(days=(d.weekday() - wd) % 7)


def _observed(d):
    return d - dt.timedelta(days=1) if d.weekday() == 5 else d + dt.timedelta(days=1) if d.weekday() == 6 else d


def federal_holidays(y):
    h = {_observed(D(y, 1, 1)), _nth_weekday(y, 1, 0, 3), _nth_weekday(y, 2, 0, 3), _last_weekday(y, 5, 0),
         _observed(D(y, 7, 4)), _nth_weekday(y, 9, 0, 1), _nth_weekday(y, 10, 0, 2), _observed(D(y, 11, 11)),
         _nth_weekday(y, 11, 3, 4), _observed(D(y, 12, 25))}
    if y >= 2021:
        h.add(_observed(D(y, 6, 19)))
    if D(y + 1, 1, 1).weekday() == 5:                      # New Year on a Saturday: observed Friday 31 Dec of this year
        h.add(D(y, 12, 31))
    return h


# Federal closures by executive order or national days of mourning (later candidate when unsure: an extra entry only delays)
CLOSURES = {D(2012, 12, 24), D(2014, 12, 26), D(2018, 12, 5), D(2018, 12, 24), D(2019, 12, 24), D(2020, 12, 24),
            D(2024, 12, 24), D(2025, 1, 9)}


def closed(d):
    return d.weekday() >= 5 or d in federal_holidays(d.year) or d in CLOSURES


def next_business(d, k=1):
    while k > 0:
        d += dt.timedelta(days=1)
        if not closed(d):
            k -= 1
    return d


# ------------------------------------------------------------------ COT release dates
_SHUTDOWN_2013 = {D(2013, 10, 1): D(2013, 10, 25), D(2013, 10, 8): D(2013, 11, 1), D(2013, 10, 15): D(2013, 11, 1),
                  D(2013, 10, 22): D(2013, 11, 8), D(2013, 10, 29): D(2013, 11, 8)}
_SHUTDOWN_2019 = dict(zip(
    [D(2018, 12, 24), D(2018, 12, 31), D(2019, 1, 8), D(2019, 1, 15), D(2019, 1, 22), D(2019, 1, 29), D(2019, 2, 5),
     D(2019, 2, 12), D(2019, 2, 19), D(2019, 2, 26)],
    [D(2019, 2, 1), D(2019, 2, 5), D(2019, 2, 8), D(2019, 2, 12), D(2019, 2, 15), D(2019, 2, 19), D(2019, 2, 22),
     D(2019, 2, 26), D(2019, 3, 1), D(2019, 3, 5)]))
_ION_2023 = {D(2023, 1, 31): D(2023, 2, 24), D(2023, 2, 7): D(2023, 3, 3), D(2023, 2, 14): D(2023, 3, 8),
             D(2023, 2, 21): D(2023, 3, 10), D(2023, 2, 28): D(2023, 3, 14), D(2023, 3, 7): D(2023, 3, 16),
             D(2023, 3, 14): D(2023, 3, 21)}
_REVISED = {D(2009, 12, 29): D(2010, 1, 7), D(2010, 4, 20): D(2010, 4, 28), D(2010, 5, 18): D(2010, 5, 27),
            D(2010, 8, 17): D(2010, 9, 2), D(2011, 5, 31): D(2011, 6, 8), D(2012, 5, 15): D(2012, 5, 21),
            D(2012, 11, 27): D(2012, 12, 5), D(2013, 1, 8): D(2013, 1, 15), D(2013, 12, 10): D(2013, 12, 18),
            D(2014, 3, 11): D(2014, 3, 18), D(2014, 11, 4): D(2014, 11, 10), D(2015, 6, 16): D(2015, 6, 23),
            D(2015, 6, 23): D(2015, 7, 1), D(2017, 3, 28): D(2017, 4, 4), D(2017, 5, 23): D(2017, 6, 1),
            D(2017, 12, 26): D(2018, 1, 3), D(2018, 9, 18): D(2018, 9, 26), D(2019, 3, 26): D(2019, 4, 3),
            D(2019, 10, 15): D(2019, 10, 24)}
COT_OVERRIDES = {**_SHUTDOWN_2013, **_SHUTDOWN_2019, **_ION_2023}


def cot_release_date(asof):
    """Release date of the COT report as of `asof` (a date): override, else the rule; a later revision date wins."""
    if asof in COT_OVERRIDES:
        rel = COT_OVERRIDES[asof]
    else:
        fri = asof + dt.timedelta(days=(4 - asof.weekday()) % 7)
        k = sum(closed(fri - dt.timedelta(days=j)) for j in range(3))      # Wed, Thu, Fri of the as-of week
        rel = next_business(fri, k) if k else fri
    return max(rel, _REVISED.get(asof, rel))


def ny_ms(d, hour, minute):
    """UTC ms of a New York wall-clock time on date d."""
    from zoneinfo import ZoneInfo
    return int(dt.datetime(d.year, d.month, d.day, hour, minute, tzinfo=ZoneInfo(NY)).timestamp() * 1000)


def cot_release_ms(asof):
    return ny_ms(cot_release_date(asof), 15, 30)


# ------------------------------------------------------------------ point-in-time alignment (any series)
def align(release_ms, values, close_ms, order=None):
    """values[k] released at release_ms[k]. For each bar close: the value with the latest `order` (as-of) among those released
    strictly before the close (NaN if none), its release time (-1) and age (close - release, -1). order defaults to release order.
    Releases at or after RESEARCH_END_MS are never used."""
    r = np.asarray(release_ms, np.int64)
    v = np.asarray(values, float)
    o = np.arange(len(r)) if order is None else np.asarray(order)
    keep = r < RESEARCH_END_MS
    r, v, o = r[keep], v[keep], o[keep]
    s_ = np.argsort(r, kind="stable")
    r, v, o = r[s_], v[s_], o[s_]
    best = np.zeros(len(r), np.int64)                                      # index (in release order) of the latest as-of so far
    for k in range(1, len(r)):
        best[k] = k if o[k] >= o[best[k - 1]] else best[k - 1]
    close_ms = np.asarray(close_ms, np.int64)
    idx = np.searchsorted(r, close_ms, side="left") - 1                   # released strictly before the close
    ok = idx >= 0
    j = best[np.where(ok, idx, 0)] if len(r) else np.zeros(len(close_ms), np.int64)
    val = np.where(ok, v[j] if len(v) else np.nan, np.nan)
    rel = np.where(ok, r[j] if len(r) else -1, -1).astype(np.int64)
    return {"value": val, "release_ms": rel, "age_ms": np.where(ok, close_ms - rel, -1).astype(np.int64)}


# ------------------------------------------------------------------ the research series store (built by tools/series/*)
def _asof_col(header):
    """The as-of date column (values YYYY-MM-DD). CFTC labels it 'As of Date in Form YYYY-MM-DD', 'Report_Date_as_YYYY-MM-DD' or,
    in the 2013-2024 Disaggregated / TFF files, 'Report_Date_as_MM_DD_YYYY' (values still YYYY-MM-DD; the builder cross-checks
    every row against the YYMMDD column)."""
    for i, h in enumerate(header):
        if re.search(r"yyyy-mm-dd", h, re.I) or re.fullmatch(r"report_date_as_mm_dd_yyyy", h, re.I):
            return i
    raise ValueError(f"no as-of date column in {header[:6]}")


def _yymmdd_col(header):
    for i, h in enumerate(header):
        if re.search(r"yymmdd", h, re.I):
            return i
    raise ValueError(f"no YYMMDD column in {header[:6]}")


def _code_col(header):
    for i, h in enumerate(header):
        if re.sub(r"[ _]", "", h).lower() == "cftccontractmarketcode":
            return i
    raise ValueError(f"no CFTC contract market code column in {header[:6]}")


@lru_cache(maxsize=None)
def _load(kind, name, root=None):
    p = os.path.join(root or SERIES_ROOT, kind, name + ".npz")
    if not os.path.isfile(p):
        raise ValueError(f"series store has no {kind}/{name} (build it with tools/series)")
    z = np.load(p, allow_pickle=False)
    return {k: z[k] for k in z.files}


COT_REPORTS = ("legacy", "disagg", "tff")
VIX_NAMES = ("VIX", "VIX3M", "VIX9D")
CALENDARS = ("monthly_expiry", "quarterly_expiry", "index_roll")


def parse_name(name):
    """'cot:<legacy|disagg|tff>:<market code>:<column>', 'vix:<VIX|VIX3M|VIX9D>:<open|high|low|close>',
    'calendar:<monthly_expiry|quarterly_expiry|index_roll>' -> tuple; anything else is refused."""
    parts = name.split(":", 3)
    if parts[0] == "cot" and len(parts) == 4 and parts[1] in COT_REPORTS and parts[2] and parts[3]:
        return tuple(parts)
    if parts[0] == "vix" and len(parts) == 3 and parts[1] in VIX_NAMES and parts[2] in ("open", "high", "low", "close"):
        return tuple(parts)
    if parts[0] == "calendar" and len(parts) == 2 and parts[1] in CALENDARS:
        return tuple(parts)
    raise ValueError(f"outside series {name!r}: not a known series (A14 §2; see engine/STRATEGY-API.md)")


def series(name, root=None):
    """(release_ms, values, as-of order) of one declared series from the store."""
    p = parse_name(name)
    if p[0] == "cot":
        z = _load("cot", p[1], root)
        cols = list(z["cols"])
        if p[3] not in cols:
            raise ValueError(f"{name}: no column {p[3]!r} in the {p[1]} report")
        m = z["code"] == p[2]
        if not m.any():
            raise ValueError(f"{name}: no market code {p[2]!r} in the {p[1]} report")
        return z["release_ms"][m], z["values"][m, cols.index(p[3])], z["asof_day"][m]
    if p[0] == "vix":
        z = _load("vix", p[1], root)
        return z["release_ms"], z[p[2]], z["day"]
    raise ValueError(f"{name}: a calendar has no release times; use calendar_dates")


def calendar_dates(name):
    """Rule-derived event dates (UTC ms of 00:00 New York on that date), known in advance."""
    kind = parse_name(name)[1]
    return np.array([ny_ms(d, 0, 0) for d, k in calendar(2010, 2024) if k == kind], np.int64)


def outside(names, close_ms, root=None):
    """ctx["series"] for a job: per declared name, aligned {"value", "release_ms", "age_ms"} (calendars: {"dates_ms"})."""
    out = {}
    for n in names:
        if n.startswith("calendar:"):
            out[n] = {"dates_ms": calendar_dates(n)}
        else:
            r, v, o = series(n, root)
            out[n] = align(r, v, close_ms, o)
    return out


def store_hash(names, root=None):
    """Hash of the store files the declared series read (for the ledger row's data_hash)."""
    h = hashlib.sha256()
    for kind, name in sorted({("cot", parse_name(n)[1]) if n.startswith("cot:") else ("vix", parse_name(n)[1])
                              for n in names if not n.startswith("calendar:")}):
        h.update(f"{kind}/{name}".encode() + open(os.path.join(root or SERIES_ROOT, kind, name + ".npz"), "rb").read())
    return h.hexdigest()[:12]


def check_store(root=None):
    """A14 §2.2 unit check: every stored series' release times are before 2025-01-01 00:00 UTC. Returns {file: max release}."""
    out = {}
    for p in sorted(glob.glob(os.path.join(root or SERIES_ROOT, "*", "*.npz"))):
        r = np.load(p)["release_ms"]
        if len(r) and int(r.max()) >= RESEARCH_END_MS:
            raise ValueError(f"{p}: a value released at or after 2025-01-01 is in the research store")
        out[os.path.relpath(p, root or SERIES_ROOT)] = int(r.max()) if len(r) else None
    return out


# ------------------------------------------------------------------ rule-derived calendars
def _easter(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = (h + l_ - 7 * m + 114) % 31 + 1
    return D(y, month, day)


EXCHANGE_CLOSURES = {D(2012, 10, 29), D(2012, 10, 30), D(2018, 12, 5), D(2025, 1, 9)}


def exchange_closed(d):
    """NYSE / CME equity: weekends, the NYSE holidays (Good Friday; Juneteenth from 2022) and unscheduled closures."""
    if d.weekday() >= 5 or d in EXCHANGE_CLOSURES or d == _easter(d.year) - dt.timedelta(days=2):
        return True
    y = d.year
    nyse = {_observed(D(y, 1, 1)), _nth_weekday(y, 1, 0, 3), _nth_weekday(y, 2, 0, 3), _last_weekday(y, 5, 0),
            _observed(D(y, 7, 4)), _nth_weekday(y, 9, 0, 1), _nth_weekday(y, 11, 3, 4), _observed(D(y, 12, 25))}
    if y >= 2022:
        nyse.add(_observed(D(y, 6, 19)))
    return d in nyse


def monthly_expiry(y, m):
    """US equity index options expiry: the third Friday, or the business day before when the exchange is shut."""
    d = _nth_weekday(y, m, 4, 3)
    while exchange_closed(d):
        d -= dt.timedelta(days=1)
    return d


def calendar(first_year=2010, last_year=2024):
    """[(date, kind)] for kind in 'monthly_expiry', 'quarterly_expiry' (= S&P quarterly rebalance effective after the close),
    'index_roll' (8 calendar days before the quarterly expiry)."""
    out = []
    for y in range(first_year, last_year + 1):
        for m in range(1, 13):
            e = monthly_expiry(y, m)
            out.append((e, "quarterly_expiry" if m % 3 == 0 else "monthly_expiry"))
            if m % 3 == 0:
                out.append((_nth_weekday(y, m, 4, 3) - dt.timedelta(days=8), "index_roll"))
    return sorted(out)
