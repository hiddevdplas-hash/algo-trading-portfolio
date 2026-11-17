"""Rules layer (DESIGN §4.2, §3.6): Amsterdam clock per date, class flats, entry blocks, news windows and modes."""
from datetime import date, datetime, timedelta, timezone

import numpy as np

from engine import rules as RU


def ms(*a):
    return int(datetime(*a, tzinfo=timezone.utc).timestamp() * 1000)


def test_class_flats_follow_amsterdam_dst():
    f = RU.class_flats("A", ms(2024, 3, 29), ms(2024, 4, 2))
    # 22:45 Amsterdam = 21:45 UTC on Fri 29 Mar (CET), 20:45 UTC from Sun 31 Mar (CEST)
    assert ms(2024, 3, 29, 21, 45) in f and ms(2024, 3, 31, 20, 45) in f and ms(2024, 4, 1, 20, 45) in f
    # B: only before a break of >= 2 h (A8); two normal FX Friday closes (17:00 NY = 23:00 Amsterdam) -> 22:45 Amsterdam
    brk = [(ms(2024, 3, 29, 22, 0), ms(2024, 3, 31, 21, 0), False), (ms(2024, 4, 2, 19, 0), ms(2024, 4, 3, 7, 0), True),
           (ms(2024, 4, 5, 21, 0), ms(2024, 4, 7, 21, 0), False)]
    b = RU.class_flats("B", ms(2024, 3, 25), ms(2024, 4, 8), brk)        # the regular daily break (2 Apr) is skipped (A8.6)
    assert list(b) == [ms(2024, 3, 29, 21, 45), ms(2024, 4, 5, 20, 45)]
    assert ms(2024, 4, 2, 18, 55) in RU.class_flats("A", ms(2024, 3, 25), ms(2024, 4, 8), brk)
    assert len(RU.class_flats("B", ms(2024, 3, 25), ms(2024, 4, 8))) == 0
    assert len(RU.class_flats("C", ms(2024, 1, 1), ms(2024, 2, 1))) == 0


def test_nightly_block_and_merge():
    s, e = RU.merge(RU.nightly_blocks(ms(2024, 7, 1), ms(2024, 7, 3)))
    assert (ms(2024, 7, 1, 20, 45), ms(2024, 7, 1, 22, 15)) in list(zip(s, e))     # 22:45 -> 00:15 Amsterdam in summer
    s, e = RU.merge([(0, 10), (5, 20), (30, 40), (40, 50)])
    assert list(s) == [0, 30] and list(e) == [20, 50]


def test_preclose_block_from_exported_close():
    H = 3_600_000
    t = np.array([0, H, 2 * H, 50 * H, 51 * H, 51 * H + 30 * 60_000], np.int64)      # 48 h weekend gap, then a 30-min hole
    close = np.array([2 * H + 60_000] * 3 + [-1] * 3, np.int64)                   # the market closes 1 min after the last tick
    out = RU.preclose_blocks(t, close)
    assert out == [(60_000, 2 * H + 60_000)]
    assert RU.market_breaks(t, close) == [(2 * H + 60_000, 50 * H, False)]
    late = np.array([5 * H] * 3 + [-1] * 3, np.int64)                             # scheduled close 3 h after trading stopped
    assert RU.market_breaks(t, late) == [(2 * H + 60_000, 50 * H, False)]                 # -> last tick + 1 min (A8)
    assert RU.market_breaks(t, None) == [(2 * H + 60_000, 50 * H, False)]


# ---- DESIGN A8: class A / B flat before every break of >= 2 h --------------------------------------------------------------
def ams(*a):
    return int(datetime(*a, tzinfo=RU.AMS).timestamp() * 1000)


def ticks_around(last, sched, reopen, start=None, step=60_000):
    """Minute ticks from start (default last - 6 h) to last, then from reopen for 6 h; every tick before the gap carries the
    scheduled close sched (as exported), the ticks after it the next close (irrelevant here)."""
    start = last - 6 * RU.HOUR if start is None else start
    a = np.arange(start, last + 1, step, dtype=np.int64)
    b = np.arange(reopen, reopen + 6 * RU.HOUR, step, dtype=np.int64)
    t = np.concatenate([a, b])
    close = np.concatenate([np.full(len(a), sched), np.full(len(b), reopen + 30 * RU.HOUR)]).astype(np.int64)
    return t, close


def flats(cls, t, close):
    return list(RU.class_flats(cls, int(t[0]), int(t[-1]) + 1, RU.market_breaks(t, close)))


def test_a8_us_only_dst_friday():
    # Fri 15 Mar 2024: US on summer time, Europe not. FX closes 17:00 NY = 22:00 Amsterdam; the exported (fixed) schedule says
    # 22:57. Last tick 21:59 -> close 22:00 -> A and B flat 21:55 Amsterdam, not 22:45 (which is after the close: weekend hold).
    t, close = ticks_around(ams(2024, 3, 15, 21, 59), ams(2024, 3, 15, 22, 57), ams(2024, 3, 17, 23, 0))
    assert RU.market_breaks(t, close)[0][0] == ams(2024, 3, 15, 22, 0)
    assert RU.preclose_blocks(t, close) == [(ams(2024, 3, 15, 20, 0), ams(2024, 3, 15, 22, 0))]
    a = flats("A", t, close)                                           # the daily 22:45s stay (inside the break they do nothing)
    assert ams(2024, 3, 15, 21, 55) in a and ams(2024, 3, 15, 22, 45) in a and a[0] == ams(2024, 3, 15, 21, 55)
    assert flats("B", t, close) == [ams(2024, 3, 15, 21, 55)]


def test_a8_normal_friday():
    # Fri 5 Jan 2024: FX closes 23:00 Amsterdam (schedule 22:57, last tick 22:56) -> 22:45 stays the earlier time.
    t, close = ticks_around(ams(2024, 1, 5, 22, 56), ams(2024, 1, 5, 22, 57), ams(2024, 1, 7, 23, 1))
    assert RU.market_breaks(t, close)[0][0] == ams(2024, 1, 5, 22, 57)
    assert ams(2024, 1, 5, 22, 45) in flats("A", t, close) and len(set(flats("A", t, close))) == len(flats("A", t, close))
    assert flats("B", t, close) == [ams(2024, 1, 5, 22, 45)]
    # summer: schedule 23:57 (fixed weekly schedule), trading stops 22:59 -> close 23:00, flat still 22:45
    t, close = ticks_around(ams(2024, 7, 5, 22, 59), ams(2024, 7, 5, 23, 57), ams(2024, 7, 7, 23, 1))
    assert RU.market_breaks(t, close)[0][0] == ams(2024, 7, 5, 23, 0)
    assert flats("B", t, close) == [ams(2024, 7, 5, 22, 45)]


def test_a8_holiday_closure_and_early_close():
    # US500, Tue 24 Dec 2024: early close (last tick 19:14 Amsterdam, schedule 21:59), closed 25 Dec, reopens Thu 00:00.
    t, close = ticks_around(ams(2024, 12, 24, 19, 14), ams(2024, 12, 24, 21, 59), ams(2024, 12, 26, 0, 0))
    assert RU.market_breaks(t, close) == [(ams(2024, 12, 24, 19, 15), ams(2024, 12, 26, 0, 0), False)]
    a = flats("A", t, close)                                           # 19:10, then the 22:45s inside the closure (no-ops)
    assert a[:3] == [ams(2024, 12, 24, 19, 10), ams(2024, 12, 24, 22, 45), ams(2024, 12, 25, 22, 45)]
    assert flats("B", t, close) == [ams(2024, 12, 24, 19, 10)]         # B: a Tuesday, the last session before the closure
    # holiday closure the schedule doesn't know at all (schedule close after the reopening): last tick + 1 min
    t, close = ticks_around(ams(2024, 3, 28, 21, 58), ams(2024, 4, 3, 21, 59), ams(2024, 4, 1, 0, 0))
    assert flats("B", t, close) == [ams(2024, 3, 28, 21, 54)]          # Maundy Thursday, before Good Friday


def sessions(first, last, open_hm, close_hm, special=None):
    """Minute ticks of weekday sessions (Amsterdam) from date first to last; each tick carries its session's scheduled close.
    open_hm / close_hm: (h, m); a close at or before the open runs to the next day. special: {date: (open_hm, close_hm) or None}."""
    special = special or {}
    t, close = [], []
    d = first
    while d <= last:
        if d.weekday() < 5:
            oc = special.get(d, (open_hm, close_hm))
            if oc is not None:
                (oh, om), (ch, cm) = oc
                a, b = ams(d.year, d.month, d.day, oh, om), ams(d.year, d.month, d.day, ch, cm)
                x = np.arange(a, b, 60_000, dtype=np.int64)
                t.append(x); close.append(np.full(len(x), b, np.int64))
        d += timedelta(days=1)
    return np.concatenate(t), np.concatenate(close)


def test_a8_eu_index_night_and_weekend():
    # STOXX50: 08:00 -> 22:00 Amsterdam, Mon-Fri; the 10-h night break is the regular daily break (from its 4th occurrence: 3 matching
    # breaks in the previous 14 days). Class A flats 21:55 every night; class B holds overnight and flats 21:55 on Fridays (A8.6).
    t, close = sessions(date(2024, 1, 29), date(2024, 2, 12), (8, 0), (22, 0))
    br = RU.market_breaks(t, close)
    assert len(br) == 10 and all(c == ams(*datetime.fromtimestamp(c / 1000, RU.AMS).timetuple()[:3], 22, 0) for c, _, _ in br)
    reg = {datetime.fromtimestamp(c / 1000, RU.AMS).date(): r for c, _, r in br}
    assert not reg[date(2024, 1, 31)] and reg[date(2024, 2, 1)] and reg[date(2024, 2, 6)]   # 4th night on: regular
    assert not reg[date(2024, 2, 2)] and not reg[date(2024, 2, 9)]                             # Fridays: weekend
    b = flats("B", t, close)
    assert ams(2024, 2, 6, 21, 55) not in b                                                    # EU index normal night: B holds
    assert ams(2024, 2, 9, 21, 55) in b and ams(2024, 2, 2, 21, 55) in b                       # EU index before a weekend
    a = flats("A", t, close)
    assert ams(2024, 2, 6, 21, 55) in a and ams(2024, 2, 6, 22, 45) in a
    assert flats("C", t, close) == []
    # build_parts takes the breaks: B gets only the non-regular ones, the entry block covers every close
    kw, info = RU.build_parts("STOXX50", "B", "M0", t, br)
    assert list(kw["flat_ms"]) == b
    s_, e_ = kw["blk_start"], kw["blk_end"]
    assert any(s0 <= ams(2024, 2, 6, 20, 30) < e0 for s0, e0 in zip(s_, e_))                  # 2-h pre-close block on a normal night


def test_a8_us500_holiday_early_close():
    # US500: 00:00 -> 23:00 Amsterdam (1-h daily break, < 2 h: moves nothing); Wed 3 Jul 2024 early close 19:15 (US holiday eve,
    # schedule unchanged in the export: the ticks stop), Thu 4 Jul shortened to 19:00. Both are breaks >= 2 h, not regular -> B flat.
    sp = {date(2024, 7, 3): ((0, 0), (19, 15)), date(2024, 7, 4): ((0, 0), (19, 0))}
    t, close = sessions(date(2024, 6, 17), date(2024, 7, 5), (0, 0), (23, 0), sp)
    close[(t >= ams(2024, 7, 3, 0, 0)) & (t < ams(2024, 7, 4, 0, 0))] = ams(2024, 7, 3, 23, 0)   # the fixed schedule says 23:00
    br = RU.market_breaks(t, close)
    assert (ams(2024, 7, 3, 19, 15), ams(2024, 7, 4, 0, 0), False) in br
    assert (ams(2024, 7, 4, 19, 0), ams(2024, 7, 5, 0, 0), False) in br
    b = flats("B", t, close)
    assert b == [ams(2024, 6, 21, 22, 45), ams(2024, 6, 28, 22, 45), ams(2024, 7, 3, 19, 10), ams(2024, 7, 4, 18, 55)]
    pre = RU.preclose_blocks(t, close)
    assert (ams(2024, 7, 3, 17, 15), ams(2024, 7, 3, 19, 15)) in pre                          # entry block from the real close


def test_news_windows_modes_symbols_merge():
    T = ms(2024, 5, 3, 12, 30)
    ev = [dict(start_ms=T, kind="release", tier=1, ccy="USD", type_id="US_NFP"),
          dict(start_ms=T + 3 * 60_000, kind="release", tier=2, ccy="USD", type_id="US_X"),
          dict(start_ms=T + 3 * 3_600_000, kind="speech", tier=2, ccy="USD", type_id="FED_SPEAK"),
          dict(start_ms=T, kind="release", tier=1, ccy="JPY", type_id="BOJ")]
    s, e, k, f = RU.news_windows(ev, "EURUSD", "M0")
    assert len(s) == 0
    s, e, k, f = RU.news_windows(ev, "EURUSD", "M1")                 # tier 1 only
    assert list(s) == [T - 6 * 60_000] and list(e) == [T + 6 * 60_000] and list(k) == [1]
    s, e, k, f = RU.news_windows(ev, "EURUSD", "M2", far={("EURUSD", "US_NFP"): 0.004})
    # NFP + tier-2 release merge into one flatten window; the speech (official start) is a hold window T+3h-6 -> T+3h+6 (DESIGN A6)
    assert list(k) == [1, 2] and e[0] == T + 9 * 60_000 and f[0] == 0.004
    assert s[1] == T + 3 * 3_600_000 - 6 * 60_000 and e[1] == T + 3 * 3_600_000 + 6 * 60_000
    s, e, k, f = RU.news_windows(ev, "EURUSD", "M3")
    assert list(k) == [1, 1] and np.isnan(f[0])                      # no far threshold for US_X -> no exemption
    assert len(RU.news_windows(ev, "EURGBP", "M3")[0]) == 0           # USD events don't block EURGBP
    assert len(RU.news_windows(ev, "US500", "M1")[0]) == 1 and len(RU.news_windows(ev, "JP225", "M1")[0]) == 1
    assert RU.blocks_symbol("OIL", "XBRUSD") and not RU.blocks_symbol("OIL", "EURUSD") and RU.blocks_symbol("EUR", "STOXX50")


def test_hold_report():
    r = RU.hold_report([0, 0, 0], [60_000, 20 * 60_000, 30 * 60_000])
    assert r["share_under_2min"] == round(1 / 3, 4) and r["fail_under_2min"] and r["median_min"] == 20
