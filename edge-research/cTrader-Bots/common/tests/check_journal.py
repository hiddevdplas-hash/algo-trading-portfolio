"""Checks one ER_RiskTest journal against cTrader-Bots/common/TEST-LIST.md §2 and prints PASS / FAIL / NOT EXERCISED / N/A per check
(plus FINDING lines). News windows are computed independently with engine/rules.py (read only) from the same calendar file the cBot
read. Exit code 1 if any check FAILs.

  ~/.venvs/fastbt/bin/python -I cTrader-Bots/common/tests/check_journal.py <journal.csv> <R1..R5> [calendar.csv] [--lines A-B]

The journal may hold several runs appended to one file (same start second): only the part after the last `start` line is checked,
or, with --lines A-B, file lines A..B (1-based, inclusive; the header line is read anyway).
"""
import csv
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, REPO)
from engine import rules  # noqa: E402  (read only)

AMS, NY, PRG = ZoneInfo("Europe/Amsterdam"), ZoneInfo("America/New_York"), ZoneInfo("Europe/Prague")
MIN = 60_000
# TEST-LIST.md §1 run table; mode and far override from firms/TEST.cfg stages
RUNS = {
    "R1": dict(symbol="EURUSD", stage="m2", mode="M2", cls="B", far=None, firm_break=False, restarts=True, foreign=True, maxloss=False),
    "R2": dict(symbol="EURUSD", stage="m3", mode="M3", cls="A", far=None, firm_break=True, restarts=True, foreign=True, maxloss=False),
    "R3": dict(symbol="XAUUSD", stage="m3far", mode="M3", cls="C", far=30.0, firm_break=False, restarts=True, foreign=True, maxloss=False),
    "R4": dict(symbol="US500", stage="m1", mode="M1", cls="A", far=None, firm_break=False, restarts=True, foreign=True, maxloss=False),
    "R5": dict(symbol="EURUSD", stage="maxloss", mode="M2", cls="B", far=None, firm_break=False, restarts=False, foreign=False, maxloss=True),
}
SOURCES = {"ForexFactory"}           # TEST.cfg news_sources
FX_METAL = re.compile(r"^([A-Z]{6}|XAUUSD|XAGUSD)$")


def utc(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc)


def ams(ms):
    return utc(ms).astimezone(AMS)


# ------------------------------------------------------------------------------------------------------------------------------
def load_journal(path, lines=None):
    raw = open(path, encoding="utf-8").read().splitlines()
    if lines:
        a, b = lines
        raw = [raw[0]] + raw[a - 1:b]
    rows = list(csv.DictReader(raw))
    starts = [k for k, r in enumerate(rows) if r["event"] == "start"]
    if not starts:
        sys.exit("no start line in the journal")
    rows = rows[starts[-1]:]
    for r in rows:
        r["t"] = int(r["utc_ms"])
        r["id"] = int(r["id"])
    return rows


def positions(rows):
    """Own positions: open time, side, sl, units, exit time and kind (from entry / fill / exit lines)."""
    pos = {}
    for r in rows:
        d = r["detail"]
        if r["event"] == "entry":
            m = re.match(r"(Buy|Sell) market ([\d.]+) units at ([\d.]+) sl (\S*) tp", d)
            pos[r["id"]] = dict(open=r["t"], side=m.group(1) if m else "?", units=float(m.group(2)) if m else 0,
                                sl=m.group(4) if m else "", exit=None, kind=None, detail=d)
        elif r["event"] == "fill":
            m = re.search(r"filled at ([\d.]+) sl (\S*)", d)
            pos[r["id"]] = dict(open=r["t"], side="?", units=0, sl=m.group(2) if m else "", exit=None, kind=None, detail=d)
        elif r["event"] == "exit" and r["id"] in pos:
            pos[r["id"]]["exit"] = r["t"]
            pos[r["id"]]["kind"] = d.split(" ")[0]
    return pos


def windows(cal_path, run):
    far, evs = {}, []
    lines = open(cal_path, encoding="utf-8").read().splitlines()
    for ln in lines:
        if ln.startswith("#far,"):
            _, s, t, v = ln.split(",")
            far[(s, t)] = float(v)
    for r in csv.DictReader([ln for ln in lines if ln and not ln.startswith("#")]):
        if r["research"] != "1" and not (set(r["sources"].split(";")) & SOURCES):
            continue
        evs.append({"start_ms": int(r["start_utc_ms"]), "end_ms": int(r["end_utc_ms"]) if r["end_utc_ms"] else None, "kind": r["kind"],
                    "tier": int(r["tier"]), "ccy": r["ccy"], "type_id": r["type_id"], "range": r["range"] == "1"})
    sym = run["symbol"]
    if run["far"] is not None:
        far = {(sym, e["type_id"]): run["far"] for e in evs}
    out = {}
    for mode in ("M1", "M3"):
        ws, we, wk, wf = rules.news_windows(evs, sym, mode, far)
        out[mode] = [(int(a), int(b), int(k), f) for a, b, k, f in zip(ws, we, wk, wf)]
    if run["mode"] == "M0":
        out["run"] = []
    else:
        ws, we, wk, wf = rules.news_windows(evs, sym, run["mode"], far)
        out["run"] = [(int(a), int(b), int(k), f) for a, b, k, f in zip(ws, we, wk, wf)]
    return out


def inside(ws, t):
    for a, b, k, f in ws:
        if a <= t < b:
            return (a, b, k, f)
    return None


def flat_times(cls, first, last):
    if cls == "C":
        return []
    out, d = [], ams(first).date() - timedelta(days=1)
    while d <= ams(last).date() + timedelta(days=1):
        if cls == "A" or d.weekday() == 4:
            out.append(int(datetime(d.year, d.month, d.day, 22, 45, tzinfo=AMS).timestamp() * 1000))
        d += timedelta(days=1)
    return out


def break_rows(cal_path, symbol):
    """The calendar's market-break rows for the symbol (DESIGN A8): [(close, reopen, kind)], or None if the file has none."""
    rows = []
    for ln in open(cal_path, encoding="utf-8"):
        if ln.startswith("#break,"):
            _, s, c, r, k = ln.strip().split(",")
            if s == symbol:
                rows.append((int(c), int(r), k))
    return rows or None


def break_flat(cls, close):
    x = close - 5 * MIN
    a = ams(x).date()
    return min(x, int(datetime(a.year, a.month, a.day, 22, 45, tzinfo=AMS).timestamp() * 1000))


def expected_flats(cls, symbol, first, last, rows=None):
    if cls == "C":
        return []
    if rows is not None:              # the engine's breaks (A8): A 22:45 daily + every break, B every break except the regular daily one
        pts = flat_times("A", first, last) if cls == "A" else []
        return sorted(pts + [break_flat(cls, c) for c, r, k in rows if not (cls == "B" and k == "daily")])
    return expected_flats_fx(cls, symbol, first, last)


def expected_flats_fx(cls, symbol, first, last):
    """DESIGN A8 flat times: class A 22:45 Amsterdam daily; plus, for FX / metals, min(Friday close - 5 min, 22:45 Amsterdam that day)
    (A and B), the close at 17:00 New York (a tick close up to 10 min earlier is accepted by T3a's 10-min tolerance). Index breaks are
    not known to the checker: their flats are checked from the cBot's log only."""
    pts = flat_times(cls, first, last) if cls == "A" else []
    if cls != "C" and FX_METAL.match(symbol):
        d = utc(first).date()
        while d <= utc(last).date():
            if d.weekday() == 4:
                c = fri_close(d)
                a = ams(c).date()
                f = int(datetime(a.year, a.month, a.day, 22, 45, tzinfo=AMS).timestamp() * 1000)
                pts.append(min(c - 5 * MIN, f))
            d += timedelta(days=1)
    return sorted(pts)


def fri_close(d):
    """IC FX / metals weekly close: Friday 17:00 New York."""
    return int(datetime(d.year, d.month, d.day, 17, 0, tzinfo=NY).timestamp() * 1000)


# ------------------------------------------------------------------------------------------------------------------------------
# lot size in units per symbol at IC (TEST cap: 3 lots); a journal's `symbol` line (cBot from 13 Nov) overrides it
LOT = {"EURUSD": 100_000, "XAUUSD": 100, "XAGUSD": 5_000, "US500": 1, "USTEC": 1, "US30": 1, "DE40": 1, "UK100": 1, "JP225": 1,
       "XTIUSD": 100, "XBRUSD": 100}


def main(path, run_id, cal_path, lines=None):
    run = RUNS[run_id]
    rows = load_journal(path, lines)
    ev = defaultdict(list)
    for r in rows:
        ev[r["event"]].append(r)
    refused = defaultdict(list)
    for r in ev["refused"]:
        refused[r["detail"].split(" ")[0]].append(r)
    pos = positions(rows)
    breaklines = []          # (position id, close text, close ms) from "close ... flat break: session close <iso>Z" lines
    for r in rows:
        m = re.search(r"break: session close (\S+ \S+)Z", r["detail"]) if r["event"] == "close" else None
        if m:
            cms = int(datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)
            breaklines.append((r["id"], m.group(1), cms))
    first, last = rows[0]["t"], rows[-1]["t"]
    W = windows(cal_path, run)
    results = []

    def res(cid, status, text):
        results.append((status, cid, text))

    # ---- T1 start
    need = ["start", "config", "calendar", "hours", "bars", "recovery", "daybase"]
    miss = [e for e in need if not ev[e]]
    cal_ok = ev["calendar"] and "problems=" in ev["calendar"][0]["detail"] and ev["calendar"][0]["detail"].rstrip().endswith("problems=")
    nwin = re.search(r"windows\([^)]*\)=(\d+)", ev["calendar"][0]["detail"]) if ev["calendar"] else None
    sess = re.search(r"sessions=(\d+)", ev["hours"][0]["detail"]) if ev["hours"] else None
    bad = miss + (["FATAL"] if ev["FATAL"] else []) + (["calendar_error"] if ev["calendar_error"] else [])
    if not cal_ok:
        bad.append("calendar problems")
    if run["mode"] != "M0" and not (nwin and int(nwin.group(1)) > 0):
        bad.append("no windows")
    if not (sess and int(sess.group(1)) > 0):
        bad.append("no sessions")
    res("T1 start lines", "FAIL" if bad else "PASS", ", ".join(bad) or f"{nwin.group(1) if nwin else 0} windows in the calendar file, {sess.group(1)} sessions")

    # ---- T2 sizing, lot cap, stops
    lot, step = LOT.get(run["symbol"], 1), None
    for r in ev["symbol"]:
        m1, m2 = re.search(r"lot_size=([\d.]+)", r["detail"]), re.search(r"volume_step=([\d.]+)", r["detail"])
        lot = float(m1.group(1)) if m1 else lot
        step = float(m2.group(1)) if m2 else step
    cap_units = 3 * lot                                       # TEST.cfg max_lots_trade = 3
    over, lowrisk, capped = [], [], 0
    for r in ev["entry"] + ev["order"]:
        m = re.search(r"([\d.]+) units at .* risk ([\d.]+)", r["detail"])
        if not m:
            continue
        units, risk = float(m.group(1)), float(m.group(2))
        st = step or (1000.0 if units >= 1000 else 1.0)      # volume step: from the journal, else IC's (FX 1,000 units, metals / indices 1)
        is_cap = units >= cap_units - st / 2
        capped += is_cap
        half = ", half" in r["detail"] or (run["maxloss"] and risk <= 100.5)     # pending-order lines carry no ", half" mark
        target = 100 if half else 200
        if risk > 200.5:
            over.append(f"{r['utc']} risk {risk}")
        elif not is_cap and risk * (units + st) / units < target - 0.5:
            lowrisk.append(f"{r['utc']} risk {risk} units {units}")   # one more volume step would still have been inside the target
    res("T2a sizing (risk <= 0.20%; below it only by rounding down one volume step, a lot cap or half risk)", "FAIL" if over or lowrisk else "PASS",
        f"{len(ev['entry']) + len(ev['order'])} entries / orders" + ("; " + "; ".join((over + lowrisk)[:5]) if over or lowrisk else ""))
    res("T2b lot cap 3 lots", "PASS" if capped else "NOT EXERCISED", f"{capped} entries / orders at {cap_units:,.0f} units (3 lots x {lot:,.0f})")
    nostop = sorted({pid for pid, p in pos.items() if p["sl"] == "" or p["kind"] == "Closed:no_stop"})
    res("T2c every position has its stop", "FAIL" if nostop else "PASS",
        f"{len(nostop)} without stop; stop_inside_spread refusals {len(refused['stop_inside_spread'])}")

    # ---- T3 class flats (DESIGN A8: 22:45 Amsterdam, or 5 min before a close that starts a break of >= 2 h if earlier)
    brows = break_rows(cal_path, run["symbol"])
    pts = expected_flats(run["cls"], run["symbol"], first, last, brows)
    fexits = [(pid, p) for pid, p in pos.items() if p["kind"] == "Closed:flat"]
    if run["cls"] == "C":
        res("T3a class flats (C: none)", "FAIL" if fexits else "PASS", f"{len(fexits)} Closed:flat")
    else:
        wrong, brk = [], 0
        for pid, p in fexits:
            P = max((x for x in pts if x <= p["exit"]), default=None)
            if P is None or P < p["open"] or p["exit"] - P > 10 * MIN:
                wrong.append(f"{pid} Closed:flat at {utc(p['exit']):%a %m-%d %H:%M}Z")
            brk += any(x[0] == pid for x in breaklines)
        missed = []
        for pid, p in pos.items():
            if p["exit"] is None or p["kind"] == "Closed:flat":
                continue
            P = min((x for x in pts if p["open"] < x <= p["exit"]), default=None)
            if P is not None and not (p["kind"] in ("StopLoss", "TakeProfit") and p["exit"] - P <= MIN) and p["exit"] - P > MIN:
                missed.append(f"{pid} open at the flat {utc(P):%a %m-%d %H:%M}Z, closed {p['kind']} {utc(p['exit']):%a %m-%d %H:%M}Z")
        fx = bool(FX_METAL.match(run["symbol"])) and brows is None
        status = "FAIL" if wrong or missed else ("PASS" if fexits else "NOT EXERCISED")
        res(f"T3a class {run['cls']} flats (A8: 22:45 Amsterdam or 5 min before a >= 2 h break)", status,
            f"{len(fexits)} Closed:flat, {brk} at a break" + (f" (expected closes: the calendar's {len(brows)} break rows)" if brows else
                                                             " (expected times: Friday close 17:00 New York)" if fx else " (break closes from the cBot's log)")
            + ("; " + "; ".join((wrong + missed)[:5]) if wrong or missed else ""))
        if brows:
            closes = [c for c, _, _ in brows]
            off = [f"{pid}: close {c}" for pid, c, cms in breaklines if not any(0 <= x - cms < 1000 for x in closes)]   # journal: whole seconds
            res("T3b the cBot's break closes = the calendar's break rows (the engine's closes)", "FAIL" if off else ("PASS" if breaklines else "NOT EXERCISED"),
                f"{len(breaklines)} break flats logged" + ("; " + "; ".join(off[:4]) if off else ""))
        elif fx:
            off = [f"{pid}: close {c}" for pid, c, cms in breaklines
                   if not (utc(cms).weekday() == 4 and 0 <= fri_close(utc(cms).date()) - cms <= 10 * MIN)]
            res("T3b the cBot's break closes = Friday 17:00 New York or up to 10 min earlier (tick closes; FX / metals)", "FAIL" if off else ("PASS" if breaklines else "NOT EXERCISED"),
                f"{len(breaklines)} break flats logged" + ("; " + "; ".join(off[:4]) if off else ""))
    held = []
    wk_closes = [c for c, r, k in brows if k != "daily"] if brows else None
    for pid, p in pos.items():
        if p["exit"] is None:
            continue
        if wk_closes is not None:
            for c in wk_closes:
                if p["open"] < c and p["exit"] > c + 3600_000:
                    held.append(f"{pid} ({p['kind']} {utc(p['exit']):%a %m-%d %H:%M}Z)")
            continue
        d = utc(p["open"]).date()
        while d <= utc(p["exit"]).date():
            if d.weekday() == 4:
                c = fri_close(d)
                if p["open"] < c and p["exit"] > c + 3600_000:
                    held.append(f"{pid} ({p['kind']} {utc(p['exit']):%a %m-%d %H:%M}Z)")
            d += timedelta(days=1)
    if run["cls"] != "C" and (brows or FX_METAL.match(run["symbol"])):
        res("T3c no position held over a weekend or holiday break (A8; " + ("the calendar's break rows" if brows else "FX close Fri 17:00 New York") + ")", "FAIL" if held else "PASS", "; ".join(held[:8]) or "none")
    fb = [p for p in pos.values() if p["kind"] == "Closed:firm_break"]
    res("T3d firm break flat", "INFO" if run["firm_break"] else ("FAIL" if fb else "N/A"),
        f"{len(fb)} Closed:firm_break" + (" (with A8 the class flat fires first at the same time; the firm break stays as a backstop)" if run["firm_break"] else ""))

    # ---- T4 entry blocks
    def night(t):
        a = ams(t)
        return (a.hour, a.minute) >= (22, 45) or (a.hour, a.minute) < (0, 15)
    ents = ev["entry"] + ev["order"]
    nb = [r["utc"] for r in ents if night(r["t"])]
    nref = [r for r in refused["blocked_entry"] if night(r["t"])]
    res("T4a no entries 22:45-00:15 Amsterdam", "FAIL" if nb else ("PASS" if nref else "NOT EXERCISED"), f"{len(nb)} inside, {len(nref)} refusals there")
    if FX_METAL.match(run["symbol"]):
        fri = [r["utc"] for r in ents if utc(r["t"]).weekday() == 4 and r["t"] >= fri_close(utc(r["t"]).date()) - 2 * 3600_000]
        res("T4b no Friday entries in the 2 h before the close", "FAIL" if fri else "PASS", f"{len(fri)} late Friday entries")
    else:
        res("T4b Friday pre-close", "N/A", "index close times are not known to the checker: read the refusals before Thu 28 Mar / Fridays")
    cb = [r for r in ev["cancel"] if "cancelled_block" in r["detail"]]
    res("T4c pending orders cancelled at a block start", "PASS" if cb else "NOT EXERCISED", f"{len(cb)} cancelled_block")

    # ---- T5 news
    ws = [w for w in W["run"] if first <= w[0] <= last]
    inwin = [r["utc"] for r in ents if inside(ws, r["t"])]
    res("T5a no entries inside the mode's windows", "FAIL" if inwin else "PASS", f"{len(ws)} windows, {len(inwin)} entries inside")
    news_by = defaultdict(list)
    for e in ("news_hold", "news_far", "news_restore", "news_defer"):
        for r in ev[e]:
            news_by[r["id"]].append((r["t"], e, r["detail"]))
    flat_ok = hold_ok = far_n = 0
    fails, ends_ok, ends_bad, held_ids = [], 0, [], []
    for pid, p in pos.items():
        ex = p["exit"] if p["exit"] is not None else last + 1
        for a, b, k, f in ws:
            if not (p["open"] < a <= ex):
                continue
            quick = p["exit"] is not None and p["exit"] - a <= MIN and p["kind"] in ("StopLoss", "TakeProfit")
            hold = [x for x in news_by[pid] if x[1] == "news_hold" and a <= x[0] <= a + 2 * MIN]
            farl = [x for x in news_by[pid] if x[1] == "news_far" and a <= x[0] <= a + 2 * MIN]
            if k == 1 and not farl:
                if p["kind"] == "Closed:news_flat" and p["exit"] - a <= 2 * MIN:
                    flat_ok += 1
                elif not quick:
                    fails.append(f"{pid}: tier-1 window {utc(a):%m-%d %H:%M}Z, got {p['kind']} {utc(ex):%m-%d %H:%M}Z")
            else:
                far_n += bool(farl)
                if hold:
                    hold_ok += 1
                    held_ids.append((pid, a, b))
                elif not quick:
                    fails.append(f"{pid}: hold window {utc(a):%m-%d %H:%M}Z, no news_hold")
            break
    exercised = flat_ok + hold_ok
    res("T5b at the window start: flatten (tier 1 / M3) or hold without target (tier 2 in M2, far-stop)",
        "FAIL" if fails else ("PASS" if exercised else "NOT EXERCISED"),
        f"{flat_ok} flattened, {hold_ok} held ({far_n} far-stop)" + ("; " + "; ".join(fails[:5]) if fails else ""))
    for pid, a, b in held_ids:
        p = pos[pid]
        after = [x for x in news_by[pid] if x[1] == "news_restore" and b <= x[0] <= b + 2 * MIN]
        ex = p["exit"]
        if after or (ex is not None and ex <= b + 2 * MIN and p["kind"] in ("StopLoss", "TakeProfit", "Closed:news_target", "Closed:time",
                                                                           "Closed:signal") ) or (ex is not None and ex < b):
            ends_ok += 1
        else:
            ends_bad.append(f"{pid} window end {utc(b):%m-%d %H:%M}Z: {p['kind']}")
    res("T5c window end: target back, past target, deferred exit or stopped", "FAIL" if ends_bad else ("PASS" if ends_ok else "NOT EXERCISED"),
        f"{ends_ok} ends; news_restore {len(ev['news_restore'])}, Closed:news_target {sum(p['kind'] == 'Closed:news_target' for p in pos.values())}"
        + ("; " + "; ".join(ends_bad[:5]) if ends_bad else ""))
    dbad, dok = [], 0
    for r in ev["news_defer"]:
        kind = "Closed:" + r["detail"].split(" ")[0]
        p = pos.get(r["id"])
        w = inside(ws, r["t"])
        if p and w and p["kind"] in (kind, "StopLoss", "Closed:news_target", "Closed:guard_daily") and p["exit"] is not None and p["exit"] <= w[1] + 2 * MIN:
            dok += 1
        else:
            dbad.append(f"{r['id']} {r['detail'][:20]} -> {p['kind'] if p else '?'}")
    res("T5d deferred time / signal exits close at the window end", "FAIL" if dbad else ("PASS" if dok else "NOT EXERCISED"),
        f"{dok} deferred" + ("; " + "; ".join(dbad[:5]) if dbad else ""))
    trails = ev["trail"]
    tin = [r["utc"] for r in trails if inside(ws, r["t"])]
    res("T5e no trail inside a window", "FAIL" if tin else ("PASS" if trails else "NOT EXERCISED"), f"{len(trails)} trail moves, {len(tin)} inside windows")
    if run["far"] is not None:
        nf = sum(p["kind"] == "Closed:news_flat" for p in pos.values())
        res("T5f far-stop: wide stops held, close stops flattened", "PASS" if ev["news_far"] and nf else "NOT EXERCISED",
            f"{len(ev['news_far'])} news_far, {nf} news_flat")
    if run["mode"] == "M1":
        t2 = [w for w in W["M3"] if not inside(W["M1"], w[0])]
        touched = [r["utc"] for e in ("news_hold", "news_far") for r in ev[e] if inside(t2, r["t"])] + \
                  [utc(p["exit"]).isoformat() for p in pos.values() if p["kind"] == "Closed:news_flat" and inside(t2, p["exit"])]
        open_t2 = sum(1 for p in pos.values() for a, b, k, f in t2 if p["open"] < a <= (p["exit"] or last))
        res("T5g M1: tier-2 events leave positions alone", "FAIL" if touched else ("PASS" if open_t2 else "NOT EXERCISED"),
            f"{open_t2} position-events at tier-2 times, {len(touched)} acted on")

    # ---- T6 caps
    per_day = defaultdict(int)
    for r in ev["entry"] + ev["fill"]:
        per_day[ams(r["t"]).date()] += 1
    mx = max(per_day.values(), default=0)
    res("T6a <= 10 fills per Amsterdam day", "FAIL" if mx > 10 else "PASS", f"max {mx}")
    res("T6b dropped_day_cap", "PASS" if refused["dropped_day_cap"] else "NOT EXERCISED", f"{len(refused['dropped_day_cap'])}")
    res("T6c dropped_order_rate (unit-tested)", "PASS" if refused["dropped_order_rate"] else "NOT EXERCISED", f"{len(refused['dropped_order_rate'])}")
    res("T6d request_budget", "PASS" if refused["request_budget"] else "NOT EXERCISED", f"{len(refused['request_budget'])}")
    iv = sorted((p["open"], p["exit"] if p["exit"] is not None else last + 1, pid) for pid, p in pos.items())
    ov = [f"{iv[k][2]}+{iv[k + 1][2]}" for k in range(len(iv) - 1) if iv[k + 1][0] < iv[k][1]]
    res("T6e never two own positions at once", "FAIL" if ov else "PASS", f"{len(pos)} positions, {len(refused['dropped_busy'])} dropped_busy" + (f"; overlaps {ov[:5]}" if ov else ""))

    # ---- T7 daily guard
    resets = set()
    for r in ev["daybase"]:
        m = re.match(r"reset (\S+ \S+)Z", r["detail"])
        if m:
            resets.add(m.group(1))
    days, d, missing = 0, ams(first).date(), []
    while d <= ams(last).date():
        if d.weekday() < 5:
            days += 1
            r0 = datetime(d.year, d.month, d.day, 0, 0, tzinfo=PRG).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            if r0 not in resets:
                missing.append(str(d))
        d += timedelta(days=1)
    unknown = [r["utc"] for r in ev["daybase"] if "UNKNOWN" in r["detail"]]
    res("T7a a day base at every reset (00:00 Prague)", "FAIL" if missing or unknown else "PASS",
        f"{days} weekdays, missing {missing[:5]}, unknown {unknown[:3]}")
    res("T7b daily_guard refusals", "PASS" if refused["daily_guard"] else "NOT EXERCISED", f"{len(refused['daily_guard'])}")
    gd = [r for r in ev["guard"] if r["detail"].startswith("guard_daily")]
    after = []
    for g in gd:
        nxt = min((int(datetime.strptime(x, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000) for x in resets
                   if datetime.strptime(x, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000 > g["t"]), default=last + 1)
        after += [r["utc"] for r in ents if g["t"] < r["t"] < nxt]
    res("T7c guard_daily flatten, then no entries until the next reset", "FAIL" if after else ("PASS" if gd else "NOT EXERCISED"),
        f"{len(gd)} flattens" + (f"; entries after: {after[:3]}" if after else ""))

    # ---- T8 max loss (R5)
    if run["maxloss"]:
        half = [r for r in ev["entry"] + ev["order"] if ", half" in r["detail"]] + [r for r in ev["entry"] if "half" in r["detail"]]
        gm = [r for r in ev["guard"] if r["detail"].startswith("guard_max")]
        res("T8a half risk near the max floor", "PASS" if half else "NOT EXERCISED", f"{len(half)} half-risk entries")
        res("T8b maxloss_near refusals", "PASS" if refused["maxloss_near"] else "NOT EXERCISED", f"{len(refused['maxloss_near'])}")
        res("T8c guard_max flatten", "PASS" if gm else "NOT EXERCISED", f"{len(gm)}")
    else:
        res("T8 max loss", "N/A", "run R5 only")

    # ---- T9 recovery
    rec = [r for r in ev["recovery"] if r["detail"].startswith("simulated restart")]
    if run["restarts"]:
        bad = [r["utc"] for r in rec if "UNCERTAIN" in r["detail"]]
        res("T9 simulated restarts: day base recorded / reconstructed, no double entry (T6e)", "FAIL" if bad else ("PASS" if rec else "NOT EXERCISED"),
            f"{len(rec)} restarts" + (f"; uncertain {bad[:3]}" if bad else ""))
    else:
        res("T9 restarts", "N/A" if not rec else "INFO", f"{len(rec)} restarts")

    # ---- T10 foreign position
    if run["foreign"]:
        tf = ev["test_foreign"]
        if not tf:
            res("T10 foreign position: hedge guard", "NOT EXERCISED", "no test_foreign line")
        else:
            fid, t0 = tf[0]["id"], tf[0]["t"]
            fside = "Buy" if "opened Buy" in tf[0]["detail"] else "Sell"
            closed = [r for r in ev["closed_other"] if r["id"] == fid]
            t1 = closed[0]["t"] if closed else last + 1
            hg = [r for r in refused["hedge_guard"] if t0 < r["t"] <= t1]
            # an opposite own entry while the foreign position was open is the failure; no rig intent at all in that time = not exercised
            opp = [f"{r['utc']} {r['detail'][:30]}" for r in ev["entry"] + ev["order"] if t0 < r["t"] < t1 and not r["detail"].startswith(fside)]
            intents = [r for r in ev["entry"] + ev["order"] + ev["refused"] if t0 < r["t"] < t1]
            st = "FAIL" if opp else ("PASS" if hg and closed else ("NOT EXERCISED" if not intents or not hg else "FAIL"))
            res("T10 foreign position: opposite intents refused (hedge_guard), its close logged", st,
                f"{len(hg)} hedge_guard, {len(intents)} rig intents while it was open ({utc(t0):%m-%d %H:%M} -> "
                f"{utc(t1):%m-%d %H:%M}Z), close logged: {bool(closed)}" + (f"; opposite entries {opp[:3]}" if opp else ""))
    else:
        res("T10 foreign position", "N/A", "off in this run")

    # ---- T11 other
    res("T11a warn_min_hold logged", "PASS" if ev["warn_min_hold"] else "NOT EXERCISED", f"{len(ev['warn_min_hold'])}")
    errs = [f"{r['utc']} {r['event']} {r['detail'][:70]}" for r in ev["error"] + ev["ALARM"]]
    res("T11b no errors or alarms", "FAIL" if errs else "PASS", "; ".join(errs[:5]) or "none")

    width = max(len(c) for _, c, _ in results)
    order = {"FAIL": 0, "NOT EXERCISED": 1, "FINDING": 2, "PASS": 3, "INFO": 4, "N/A": 5}
    print(f"journal {os.path.basename(path)}  run {run_id} ({run['symbol']} {run['stage']} {run['mode']} class {run['cls']})  "
          f"{utc(first):%Y-%m-%d} -> {utc(last):%Y-%m-%d}, {len(rows)} lines, {len(pos)} positions")
    for st, cid, text in results:
        print(f"{st:<14} {cid:<{width}}  {text}")
    counts = defaultdict(int)
    for st, _, _ in results:
        counts[st] += 1
    print("summary: " + ", ".join(f"{k} {counts[k]}" for k in sorted(counts, key=lambda x: order.get(x, 9))))
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    a = sys.argv[1:]
    lines = None
    if "--lines" in a:
        k = a.index("--lines")
        lo, hi = a[k + 1].split("-")
        lines = (int(lo), int(hi) if hi else 10 ** 9)
        a = a[:k] + a[k + 2:]
    if len(a) < 2 or a[1] not in RUNS:
        sys.exit(__doc__)
    sys.exit(main(a[0], a[1], a[2] if len(a) > 2 else os.path.join(os.path.dirname(HERE), "calendar", "er-calendar-test.csv"), lines))
