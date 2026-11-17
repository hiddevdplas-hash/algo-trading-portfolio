"""DESIGN A14 §2 (draft): outside series (engine/series.py). COT release dates against CFTC's published schedules, the overrides,
point-in-time alignment, the research-end cut, the file reader on synthetic files, and the rule-derived calendars."""
import csv
import datetime as dt
import io
import zipfile

import numpy as np
import pytest

from engine import series as S

D = dt.date
# cftc.gov Release Schedule pages: 2014-12 -> 2015 (archived 2015-06-11) and 2026 (current)
PUB_2015 = [D(2014, 12, d) for d in (1, 5, 12, 19, 30)] + [D(2015, m, d) for m, ds in {
    1: [5, 9, 16, 23, 30], 2: [6, 13, 20, 27], 3: [6, 13, 20, 27], 4: [3, 10, 17, 24], 5: [1, 8, 15, 22, 29], 6: [5, 12, 19, 26],
    7: [6, 10, 17, 24, 31], 8: [7, 14, 21, 28], 9: [4, 11, 18, 25], 10: [2, 9, 16, 23, 30], 11: [6, 13, 20, 30],
    12: [4, 11, 18, 28]}.items() for d in ds]
PUB_2026 = [D(2026, m, d) for m, ds in {
    1: [5, 9, 16, 23, 30], 2: [6, 13, 20, 27], 3: [6, 13, 20, 27], 4: [3, 10, 17, 24], 5: [1, 8, 15, 22, 29], 6: [5, 12, 22, 26],
    7: [6, 10, 17, 24, 31], 8: [7, 14, 21, 28], 9: [4, 11, 18, 25], 10: [2, 9, 16, 23, 30], 11: [6, 16, 20, 30],
    12: [4, 11, 18, 28]}.items() for d in ds]


def _asofs(first, n):
    out, d = [], first
    while len(out) < n:
        if d.weekday() == 1:
            out.append(d - dt.timedelta(days=1) if d in S.federal_holidays(d.year) else d)
        d += dt.timedelta(days=1)
    return out


@pytest.mark.parametrize("pub,first", [(PUB_2015, D(2014, 11, 25)), (PUB_2026, D(2025, 12, 30))])
def test_release_rule_never_before_the_published_schedule(pub, first):
    """CFTC's published schedules: 2014-12 -> 2015 (archived page 2015-06-11) and 2026 (current page)."""
    rel = [S.cot_release_date(a) for a in _asofs(first, len(pub))]
    assert all(r >= p for r, p in zip(rel, pub))
    later = [(p, r) for p, r in zip(pub, rel) if r > p]
    if pub is PUB_2026:
        assert later == []                                              # equal to every 2026 date (Veterans Day, Juneteenth...)
    else:                                                               # later only: two revised weeks and Veterans Day 2015
        assert later == [(D(2015, 6, 19), D(2015, 6, 23)), (D(2015, 6, 26), D(2015, 7, 1)), (D(2015, 11, 13), D(2015, 11, 16))]


def test_overrides_and_holidays():
    assert S.cot_release_date(D(2014, 12, 23)) == D(2014, 12, 30)       # Dec 25-26, 2014 closed: two days late (announcement)
    assert S.cot_release_date(D(2021, 6, 15)) == D(2021, 6, 21)         # first Juneteenth (announcement)
    assert S.cot_release_date(D(2020, 12, 21)) >= D(2020, 12, 28)       # Monday data, published Monday 28th (announcement)
    assert S.cot_release_date(D(2013, 10, 1)) == D(2013, 10, 25)        # shutdown 2013 (PR 6745-13)
    assert S.cot_release_date(D(2018, 12, 24)) == D(2019, 2, 1)         # shutdown 2018-19 (PR 7864-19)
    assert S.cot_release_date(D(2019, 2, 26)) == D(2019, 3, 5) and S.cot_release_date(D(2019, 3, 5)) == D(2019, 3, 8)
    assert S.cot_release_date(D(2023, 1, 31)) == D(2023, 2, 24)         # ION 2023
    assert S.cot_release_date(D(2017, 3, 28)) == D(2017, 4, 4)          # revised after release: the revision date
    t = S.cot_release_ms(D(2015, 1, 6))                                 # Friday 9 Jan 2015 15:30 New York = 20:30 UTC
    assert dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc) == dt.datetime(2015, 1, 9, 20, 30, tzinfo=dt.timezone.utc)
    t = S.cot_release_ms(D(2015, 7, 14))                                # summer: 19:30 UTC
    assert dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).hour == 19
    assert S.cot_release_ms(D(2024, 12, 31)) >= S.RESEARCH_END_MS       # released 2025-01-06: outside research


def test_align_point_in_time():
    rel = np.array([100, 200, 300, S.RESEARCH_END_MS + 5], np.int64)
    val = np.array([1.0, 2.0, 3.0, 99.0])
    a = S.align(rel, val, np.array([50, 100, 101, 200, 299, 300, 301, S.RESEARCH_END_MS + 10], np.int64))
    assert np.isnan(a["value"][0]) and a["release_ms"][0] == -1 and a["age_ms"][0] == -1
    assert np.isnan(a["value"][1])                                      # a bar closing exactly at the release: not yet visible
    assert list(a["value"][2:]) == [1.0, 1.0, 2.0, 2.0, 3.0, 3.0]       # never the value released after the research end
    assert a["age_ms"][2] == 1
    # a report revised after release (released later than the next week's report) never replaces the newer week
    a = S.align([100, 300, 200], [1.0, 1.5, 2.0], [250, 350], order=[1, 1, 2])
    assert list(a["value"]) == [2.0, 2.0]


def _zip(path, header, rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("f.txt", buf.getvalue())


def test_cot_builder_and_store_on_synthetic_files(tmp_path):
    from tools.series import build_cot as B
    raw, root = tmp_path / "raw", tmp_path / "store"
    raw.mkdir()
    legacy = ["Market and Exchange Names", "As of Date in Form YYMMDD", "As of Date in Form YYYY-MM-DD", "CFTC Contract Market Code",
              "Noncommercial Positions-Long (All)"]
    _zip(raw / "deacot2024.zip", legacy, [["EURO FX", "241224", "2024-12-24", "099741", "10"],
                                          ["EURO FX", "241231", "2024-12-31", "099741", "11"],
                                          ["EURO FX", "241217", "2024-12-17", "099741", "9"]])
    m = B.build("legacy", raw=str(raw), out=str(root / "cot"))
    assert m["rows_stored"] == 2 and m["cut_asofs"] == ["2024-12-31"]  # released 2025: never stored
    rel, val, order = S.series("cot:legacy:099741:Noncommercial Positions-Long (All)", root=str(root))
    assert list(val) == [9.0, 10.0] and (np.diff(rel) > 0).all()
    assert S.check_store(str(root))
    with pytest.raises(ValueError, match="no market code"):
        S.series("cot:legacy:000000:Noncommercial Positions-Long (All)", root=str(root))
    with pytest.raises(ValueError, match="no column"):
        S.series("cot:legacy:099741:Nonsense", root=str(root))
    disagg = ["Market_and_Exchange_Names", "As_of_Date_In_Form_YYMMDD", "Report_Date_as_MM_DD_YYYY", "CFTC_Contract_Market_Code",
              "M_Money_Positions_Long_All"]
    _zip(raw / "fut_disagg_txt_2024.zip", disagg, [["GOLD", "241217", "2024-12-18", "088691", "5"]])
    with pytest.raises(ValueError, match="YYMMDD"):                     # the as-of label varies; the values are cross-checked
        B.build("disagg", raw=str(raw), out=str(root / "cot"))


def test_stored_series_end_before_the_locked_period():
    """A14 §2.2: every stored series (the real research store) has its last release before 2025-01-01 00:00 UTC."""
    out = S.check_store()
    assert {"cot/legacy.npz", "cot/disagg.npz", "cot/tff.npz", "vix/VIX.npz"} <= set(out)
    assert max(out.values()) < S.RESEARCH_END_MS
    r, v, _ = S.series("vix:VIX:close")
    t = dt.datetime.fromtimestamp(r[-1] / 1000, dt.timezone.utc)
    assert t.date() == D(2024, 12, 31) and t.hour == 21 and t.minute == 15   # 16:15 New York


def test_series_names():
    assert S.parse_name("cot:tff:13874A:Lev_Money_Positions_Long_All")[2] == "13874A"
    assert S.parse_name("calendar:quarterly_expiry") == ("calendar", "quarterly_expiry")
    for bad in ("cot:tff:13874A", "vix:VIX:volume", "news:NFP", "calendar:fomc"):
        with pytest.raises(ValueError):
            S.parse_name(bad)
    c = S.outside(["calendar:quarterly_expiry"], np.array([0], np.int64))["calendar:quarterly_expiry"]["dates_ms"]
    assert len(c) == 15 * 4


def test_calendars():
    assert S.monthly_expiry(2014, 4) == D(2014, 4, 17)                  # Good Friday 18 Apr 2014
    assert S.monthly_expiry(2022, 4) == D(2022, 4, 14) and S.monthly_expiry(2019, 4) == D(2019, 4, 18)
    assert S.monthly_expiry(2024, 6) == D(2024, 6, 21) and S.monthly_expiry(2020, 3) == D(2020, 3, 20)
    cal = S.calendar(2014, 2024)
    kinds = {k for _, k in cal}
    assert kinds == {"monthly_expiry", "quarterly_expiry", "index_roll"} and len(cal) == 11 * 16
    q = [d for d, k in cal if k == "quarterly_expiry"]
    roll = [d for d, k in cal if k == "index_roll"]
    assert all(r.weekday() == 3 and 0 < (e - r).days <= 8 for r, e in zip(roll, q))
