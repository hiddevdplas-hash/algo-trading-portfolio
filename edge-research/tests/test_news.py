"""News calendar loader (DESIGN §3.6): local times with zones, talks with end times, events without a fixed time, far-stop bp."""
from datetime import datetime, timezone

import numpy as np

from engine import news as N, rules as RU


def ms(*a):
    return int(datetime(*a, tzinfo=timezone.utc).timestamp() * 1000)


def test_loader(tmp_path, monkeypatch):
    (tmp_path / "dates").mkdir()
    (tmp_path / "types-x.csv").write_text(
        "type_id,ccy,name,kind,tier,firms,fixed_time,official_source,note\n"
        "US_CPI,USD,CPI,release,1,FTMO,yes,bls.gov,\n"
        "FOMC_PRESSER,USD,press conference,press_conference,1,FTMO,yes,fed,\n"
        "BOJ_RATE,JPY,BoJ,decision,1,FTMO,no,boj,\n")
    (tmp_path / "dates" / "USD.csv").write_text(
        "# comment line\ndate,time_local,tz,ccy,type_id,end_time_local,end_status,source\n"
        "2024-03-12,08:30,America/New_York,USD,US_CPI,,n/a,bls\n"
        "2024-03-20,14:30,America/New_York,USD,FOMC_PRESSER,15:25,official,fed\n"
        "2025-01-15,08:30,America/New_York,USD,US_CPI,,n/a,bls\n")
    (tmp_path / "dates" / "JPY.csv").write_text(
        "date,time_local,tz,ccy,type_id,end_time_local,end_status,source\n"
        "2024-03-19,12:23,Asia/Tokyo,JPY,BOJ_RATE,,n/a,boj\n2024-04-26,,Asia/Tokyo,JPY,BOJ_RATE,,n/a,boj\n")
    monkeypatch.setattr(N, "NEWS", str(tmp_path))
    monkeypatch.setattr(N, "tracked", lambda pat: sorted(__import__("glob").glob(str(tmp_path / pat))))
    N.types.cache_clear()
    ev = N.events()
    N.types.cache_clear()
    assert len(ev) == 4                                                  # 2025 is outside the research period
    cpi = [e for e in ev if e["type_id"] == "US_CPI"][0]
    assert cpi["start_ms"] == ms(2024, 3, 12, 12, 30)                    # 08:30 New York in DST (US clocks moved 10 Mar)
    pc = [e for e in ev if e["type_id"] == "FOMC_PRESSER"][0]
    assert RU.event_window(pc) == (ms(2024, 3, 20, 18, 24), ms(2024, 3, 20, 18, 36))          # A6: T-6 -> T+6 around the start
    assert RU.event_window_fundingpips(pc) == (ms(2024, 3, 20, 18, 24), ms(2024, 3, 20, 19, 30))  # A6.4: official end 15:25 + 5
    boj = [e for e in ev if e["type_id"] == "BOJ_RATE"]
    assert boj[0]["start_ms"] == ms(2024, 3, 19, 2) and boj[0]["end_ms"] == ms(2024, 3, 19, 5)   # 11:00-14:00 Tokyo range
    assert boj[1]["start_ms"] == ms(2024, 4, 26, 2)


def test_far_bp_converted_at_window_price():
    ev = [dict(start_ms=ms(2024, 5, 3, 12, 30), kind="release", tier=1, ccy="USD", type_id="US_NFP")]
    s, e, k, f = RU.news_windows(ev, "XAUUSD", "M3", far={("XAUUSD", "US_NFP"): 50.0}, price_at=lambda t: 2300.0)
    assert f[0] == 50.0 / 1e4 * 2300.0


def test_research_sources_and_speech_range(tmp_path, monkeypatch):
    (tmp_path / "dates").mkdir()
    (tmp_path / "types-x.csv").write_text(
        "type_id,ccy,name,kind,tier,firms,fixed_time,official_source,note\n"
        "FED_CHAIR_SPEAKS,USD,speech,speech,2,FundingPips;ForexFactory,no,fed,\n"
        "US_CLAIMS,USD,claims,release,2,FundingPips;Myfxbook,yes,dol,\n")
    (tmp_path / "dates" / "USD.csv").write_text(
        "date,time_local,tz,ccy,type_id,end_time_local,end_status,source\n"
        "2024-03-07,,America/New_York,USD,FED_CHAIR_SPEAKS,,assumed,fed\n2024-03-07,08:30,America/New_York,USD,US_CLAIMS,,n/a,dol\n")
    monkeypatch.setattr(N, "NEWS", str(tmp_path))
    monkeypatch.setattr(N, "tracked", lambda pat: sorted(__import__("glob").glob(str(tmp_path / pat))))
    N.types.cache_clear()
    ev, allev = N.events(), N.events(research=False)
    N.types.cache_clear()
    assert [e["type_id"] for e in ev] == ["FED_CHAIR_SPEAKS"] and len(allev) == 2          # A5.1: Myfxbook / FundingPips-only out
    assert ev[0]["start_ms"] == ms(2024, 3, 7, 13) and ev[0]["end_ms"] == ms(2024, 3, 8, 1)  # A5.2: 08:00-20:00 New York
    assert RU.event_window(ev[0]) == (ms(2024, 3, 7, 12, 54), ms(2024, 3, 8, 1, 5))          # no official start: whole range + 5
    assert RU.event_window_fundingpips(ev[0]) == RU.event_window(ev[0])
    assert RU.FP_ASSUMED_END["press_conference"] == 90 * 60_000                            # A6.4
