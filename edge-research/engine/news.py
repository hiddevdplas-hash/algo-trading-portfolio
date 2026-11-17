"""News calendar (DESIGN §3.6): loads news/types-*.csv and news/dates/*.csv into events for the rules layer, and builds the far-stop
thresholds (engine/news_far.json). Only files committed to git are used (work in progress in news/ never reaches a run); they are part of
the engine hash (engine/hash.py).

Event (engine.rules format): start_ms (UTC), end_ms (talks: the official end, or None; events without a fixed time: the end of their
usual range), range (True when start_ms / end_ms span a usual range because there is no official start), kind, tier, ccy ('OIL' for EIA
inventories), type_id. Research windows: T-6 -> T+6 around an official start, the whole range otherwise (DESIGN A6, engine.rules).
Events without a fixed time (Bank of Japan decisions): the window covers the usual release range plus the actual time (§3.6).

Far-stop thresholds (§3.6): per symbol and event type, 1.5 x the 99th percentile of the window's high-low range (mid prices) over
2014-11 -> 2024-12, in **bp of price** (a decade of gold from 1,200 to 2,600 makes a price-unit percentile meaningless); the rules
layer converts bp to price at each window's opening tick. A type with fewer than 20 windows on a symbol gets no threshold (no exemption).

  ~/.venvs/fastbt/bin/python -m engine.news check            counts per type and year, problems
  ~/.venvs/fastbt/bin/python -m engine.news far [SYMBOLS...]  builds engine/news_far.json from the research store
"""
import csv
import glob
import json
import os
import sys
from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEWS = os.path.join(REPO, "news")
FAR_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "news_far.json")
FIRST, LAST = "2014-11-01", "2024-12-31"
# usual release range of events without a fixed time: type_id -> (zone, start HH:MM, end HH:MM)
USUAL_RANGE = {"BOJ_RATE": ("Asia/Tokyo", "11:00", "14:00"),
               # testimony without an official start (61 of 62 rows): any common hearing start (09:30-13:30 New York) plus the
               # 3.5 h default; a row with an official start and end keeps them (DESIGN §3.6: a longer block only removes trading time)
               "FED_CHAIR_TESTIFIES": ("America/New_York", "09:30", "17:00")}
FAR_MULT, FAR_PCT, FAR_MIN_N = 1.5, 99, 20
# DESIGN A5.1: the research modes use types listed by ForexFactory (red), FTMO or FundingPips' dashboard; FXStreet-only and
# Myfxbook-only types are for the firm simulation only. The `firms` tag "FundingPips" in the type files marks a category on FundingPips'
# public page, not its login-only dashboard list, so on its own it does not make a research type.
RESEARCH_SOURCES = ("ForexFactory", "FTMO", "FundingPips-dashboard")
# speeches without an official start: the bank's usual range for that day (A5.2)
SPEECH_RANGE = ("08:00", "20:00")


def tracked(pattern):
    """Calendar files matching pattern that are committed to git (work in progress in news/ is never used)."""
    import subprocess
    root = os.path.dirname(NEWS)
    r = subprocess.run(["git", "-C", root, "ls-files", "--", os.path.relpath(NEWS, root)], capture_output=True, text=True)
    files = {os.path.join(root, f) for f in r.stdout.split()}
    return sorted(p for p in glob.glob(os.path.join(NEWS, pattern)) if p in files)


def _rows(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return [r for r in csv.DictReader(l for l in fh if l.strip() and not l.lstrip().startswith("#"))]


@lru_cache(maxsize=1)
def types():
    out = {}
    for p in tracked("types-*.csv"):
        for r in _rows(p):
            out[r["type_id"].strip()] = {k: (v or "").strip() for k, v in r.items()}
    return out


def _ms(day, hhmm, tz):
    d = datetime.strptime(f"{day} {hhmm}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(tz))
    return int(d.timestamp() * 1000)


# A5.2 names these speeches explicitly; they count for research even where ForexFactory showed them orange in the months read
A5_2_SPEECHES = ("FED_CHAIR_SPEAKS", "ECB_PRESIDENT_SPEAKS", "BOE_GOV_SPEAKS")


def research_type(t):
    """A5.1: the curated `research` column (yes / no ...) where the type file has one, else the source rule; plus A5.2's speeches."""
    if t.get("type_id") in A5_2_SPEECHES:
        return True
    col = (t.get("research") or "").strip().lower()
    if col:
        return col.startswith("yes")
    return bool({x.strip() for x in t.get("firms", "").split(";")} & set(RESEARCH_SOURCES))


def events(first=FIRST, last=LAST, research=True):
    """Events of the calendar inside [first, last] (local dates), sorted by start. research=True: only the research types (A5.1);
    False: every type, each tagged with its sources (for the firm simulation)."""
    ty = types()
    out = []
    for p in tracked(os.path.join("dates", "*.csv")):
        for r in _rows(p):
            day = (r.get("date") or "").strip()
            if not (first <= day <= last):
                continue
            tid = r["type_id"].strip()
            t = ty.get(tid)
            if t is None:
                raise ValueError(f"{p}: type {tid} not in news/types-*.csv")
            tz = r["tz"].strip()
            tl = (r.get("time_local") or "").strip()
            if research and not research_type(t):
                continue
            ev = {"type_id": tid, "ccy": r["ccy"].strip(), "kind": t["kind"], "tier": int(t["tier"]), "end_ms": None,
                  "firms": t.get("firms", "")}
            el0 = (r.get("end_time_local") or "").strip()
            if tid in USUAL_RANGE and not (tl and el0):
                z, a, b = USUAL_RANGE[tid]
                s, e = _ms(day, a, z), _ms(day, b, z)
                if tl:
                    x = _ms(day, tl, tz)
                    s, e = min(s, x), max(e, x)
                ev["start_ms"], ev["end_ms"], ev["range"] = s, e, True
            elif not tl and t["kind"] in ("speech", "press_conference", "testimony"):   # A5.2 (and press conferences and committee
                # appearances likewise): no official start -> the bank's 08:00-20:00 local day range (RBNZ press conferences 2014-18,
                # BoJ 2020-03-16 / 05-22, BoC / RBNZ committee appearances; Fed testimony keeps its USUAL_RANGE above)
                ev["start_ms"], ev["end_ms"], ev["range"] = _ms(day, SPEECH_RANGE[0], tz), _ms(day, SPEECH_RANGE[1], tz), True
            else:
                if not tl:
                    raise ValueError(f"{p}: {day} {tid} has no time and no usual range")
                ev["start_ms"] = _ms(day, tl, tz)
                el = (r.get("end_time_local") or "").strip()
                if el:
                    e = _ms(day, el, tz)
                    ev["end_ms"] = e if e > ev["start_ms"] else e + 86_400_000
            out.append(ev)
    out.sort(key=lambda e: (e["start_ms"], e["type_id"]))
    return out


def far_thresholds():
    """{(symbol, type_id): bp of price}; empty until engine/news_far.json is built."""
    if not os.path.isfile(FAR_JSON):
        return {}
    d = json.load(open(FAR_JSON))
    return {(s, t): v["far_bp"] for s, row in d["symbols"].items() for t, v in row.items() if v.get("far_bp") is not None}


def build_far(symbols=None, log=print):
    from engine import data, rules, store
    evs = events()
    syms = symbols or sorted(d for d in os.listdir(store.STORE_ROOT) if os.path.isfile(os.path.join(store.STORE_ROOT, d, "meta.json")))
    out = json.load(open(FAR_JSON)) if os.path.isfile(FAR_JSON) and symbols else {"symbols": {}}
    for sym in syms:
        mine = [e for e in evs if rules.blocks_symbol(e["ccy"], sym)]
        if not mine:
            out["symbols"][sym] = {}
            continue
        tk = data.ticks(sym, "2014-11", "2024-12", venue="ic")
        mid = tk.mid
        row = {}
        for tid in sorted({e["type_id"] for e in mine}):
            rng = []
            for e in (x for x in mine if x["type_id"] == tid):
                o, c = rules.event_window(e)
                a, b = np.searchsorted(tk.t, o), np.searchsorted(tk.t, c)
                if b - a >= 2:
                    seg = mid[a:b]
                    rng.append((seg.max() - seg.min()) / seg[0] * 1e4)
            n = len(rng)
            far = round(FAR_MULT * float(np.percentile(rng, FAR_PCT)), 2) if n >= FAR_MIN_N else None
            row[tid] = {"n": n, "p99_bp": round(float(np.percentile(rng, FAR_PCT)), 2) if n else None, "far_bp": far}
        out["symbols"][sym] = row
        # share of trading time (ticks, a proxy) inside each mode's windows; M0 blocks nothing
        blocked = {}
        for mode in ("M1", "M2", "M3"):
            ws, we, wk, _ = rules.news_windows(evs, sym, mode)
            blocked[mode] = rules.blocked_tick_share(tk.t, ws, we)
        out.setdefault("blocked_share", {})[sym] = blocked
        log(f"{sym}: {len(row)} event types, {sum(v['n'] for v in row.values())} windows, blocked {blocked}")
        del tk, mid
    out["about"] = ("Far-stop thresholds (DESIGN §3.6): 1.5 x p99 of the window high-low range (IC mid), bp of the price at the window's "
                    f"opening tick, 2014-11 -> 2024-12; types with < {FAR_MIN_N} windows on a symbol: none.")
    json.dump(out, open(FAR_JSON, "w"), indent=1, sort_keys=True)
    return out


def check():
    ty, evs = types(), events()
    by = {}
    for e in evs:
        y = datetime.utcfromtimestamp(e["start_ms"] / 1000).year
        by.setdefault(e["type_id"], {}).setdefault(y, 0)
        by[e["type_id"]][y] += 1
    unused = sorted(set(ty) - set(by))
    return {"types": len(ty), "events": len(evs), "per_type_year": by, "types_without_dates": unused}


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "far":
        build_far(a[1:] or None)
    else:
        print(json.dumps(check(), indent=1))
