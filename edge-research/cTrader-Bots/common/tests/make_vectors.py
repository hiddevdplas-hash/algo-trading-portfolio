"""Parity vectors for the cBot core (ErCore.cs) from the engine's own rules (engine/rules.py, read only): class flats and nightly blocks
across both DST changes, firm reset times, and the news windows of every mode for several symbols, computed from the same exported
calendar file the cBot reads. Run by run_tests.sh; writes JSON to the path given.

  ~/.venvs/fastbt/bin/python -I cTrader-Bots/common/tests/make_vectors.py <calendar.csv> <out.json>
"""
import csv
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO)
from engine import rules  # noqa: E402  (read only)


def ms(*a):
    return int(datetime(*a, tzinfo=timezone.utc).timestamp() * 1000)


def load_calendar(path):
    far, rows = {}, []
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    for ln in lines:
        if ln.startswith("#far,"):
            _, s, t, v = ln.split(",")
            far[(s, t)] = float(v)
    body = [ln for ln in lines if ln and not ln.startswith("#")]
    for r in csv.DictReader(body):
        if r["research"] != "1":
            continue
        rows.append({"start_ms": int(r["start_utc_ms"]), "end_ms": int(r["end_utc_ms"]) if r["end_utc_ms"] else None, "kind": r["kind"],
                     "tier": int(r["tier"]), "ccy": r["ccy"], "type_id": r["type_id"], "range": r["range"] == "1"})
    return rows, far


def main(cal, out):
    v = {}
    first, end = ms(2024, 2, 1), ms(2024, 12, 1)
    v["flats_A"] = [int(x) for x in rules.class_flats("A", first, end)]
    # DESIGN A8: synthetic breaks (close, reopen, kind) through the engine's class_flats; class B gets the non-daily closes (A8.6)
    NYZ, AMZ = ZoneInfo("America/New_York"), ZoneInfo("Europe/Amsterdam")
    brk = []
    d = datetime(2024, 2, 2).date()
    while d < datetime(2024, 12, 1).date():
        if d.weekday() == 4:                      # FX week: last tick 17:00 New York - 3 min, reopen Sunday 17:00
            c = int(datetime(d.year, d.month, d.day, 16, 57, tzinfo=NYZ).timestamp() * 1000)
            brk.append((c, c + 48 * 3_600_000 + 3 * 60_000, "weekend"))
        elif d.weekday() < 4:                     # a STOXX50-like regular daily break 22:00 -> 08:00 Berlin
            c = int(datetime(d.year, d.month, d.day, 22, 0, tzinfo=ZoneInfo("Europe/Berlin")).timestamp() * 1000)
            brk.append((c, c + 10 * 3_600_000, "daily"))
        d += timedelta(days=1)
    extra = [(datetime(2024, 7, 3, 13, 15, tzinfo=NYZ), 20, "holiday"),          # US early close
             (datetime(2024, 11, 28, 13, 0, tzinfo=NYZ), 30, "holiday"),         # Thanksgiving
             (datetime(2024, 5, 6, 23, 2, tzinfo=AMZ), 5, "holiday"),            # close after 22:45 Amsterdam
             (datetime(2024, 5, 8, 0, 3, tzinfo=AMZ), 4, "holiday"),             # close just after Amsterdam midnight (date edge)
             (datetime(2024, 3, 31, 2, 30, tzinfo=timezone.utc), 3, "gap")]      # DST night, data gap
    brk += [(int(x.timestamp() * 1000), int(x.timestamp() * 1000) + h * 3_600_000, k) for x, h, k in extra]
    brk.sort()
    v["breaks"] = [[c, r, k] for c, r, k in brk]
    eng = [(c, r, k == "daily") for c, r, k in brk]            # engine form (A8.6): (close, reopen, regular_daily)
    v["flats_A8_A"] = [int(x) for x in rules.class_flats("A", first, end, eng)]
    v["flats_A8_B"] = [int(x) for x in rules.class_flats("B", first, end, eng)]
    v["flats_B"] = v["flats_A8_B"]
    s, e = rules.merge(rules.nightly_blocks(first, end))
    probes = list(range(ms(2024, 3, 8), ms(2024, 4, 3), 7 * 60_000)) + list(range(ms(2024, 10, 24), ms(2024, 11, 6), 7 * 60_000))
    v["night_probes"] = [[t, any(a <= t < b for a, b in zip(s, e))] for t in probes]
    v["day_starts"] = [int(x) for x in rules.day_starts(ms(2024, 3, 25), ms(2024, 4, 2))]
    # firm resets: the last reset at or before each probe (zoneinfo), for the configs' zones and times
    resets = {"Europe/Prague 00:00": ("Europe/Prague", 0, 0), "America/New_York 17:00": ("America/New_York", 17, 0),
              "Europe/Amsterdam 23:30": ("Europe/Amsterdam", 23, 30), "UTC 00:00": ("UTC", 0, 0)}
    rp = list(range(ms(2024, 3, 7), ms(2024, 4, 3), 37 * 60_000)) + list(range(ms(2024, 10, 24), ms(2024, 11, 6), 37 * 60_000))
    out_r = {}
    for k, (z, hh, mm) in resets.items():
        zi = ZoneInfo(z)
        rows = []
        for t in rp:
            d = datetime.fromtimestamp(t / 1000, zi).date()
            for back in range(3):
                dd = d - timedelta(days=back)
                r = int(datetime(dd.year, dd.month, dd.day, hh, mm, tzinfo=zi).timestamp() * 1000)
                if r <= t:
                    rows.append([t, r])
                    break
        out_r[k] = rows
    v["resets"] = out_r
    # news windows: identical calendar input, research events, all modes
    evs, far = load_calendar(cal)
    win = {}
    for sym in ("EURUSD", "USDJPY", "XAUUSD", "US500", "DE40", "UK100", "JP225", "XTIUSD", "AUDNZD", "GBPCHF"):
        for mode in rules.MODES:
            ws, we, wk, wf = rules.news_windows(evs, sym, mode, far)
            win[f"{sym}|{mode}"] = [[int(a), int(b), int(c), None if f != f else float(f)] for a, b, c, f in zip(ws, we, wk, wf)]
    v["windows"] = win
    v["events"] = len(evs)
    json.dump(v, open(out, "w"))
    print(f"vectors: {len(v['flats_A'])} A flats, {len(probes)} night probes, {sum(len(x) for x in win.values())} windows from {len(evs)} events -> {out}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
