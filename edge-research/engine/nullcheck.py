"""Null calibration (DESIGN §8): random-entry strategies (and built-in-edge ones) through the whole pipeline, with the same rules,
costs, news modes, amber budget, near-miss lane and firm eligibility as real ideas. Every run is a ledger test (lane 'null').

  ~/.venvs/fastbt/bin/python -m engine.nullcheck plan [--n 1000] [--edge 100]   writes null/PLAN.json (commit it: it is the null 'card')
  ~/.venvs/fastbt/bin/python -m engine.nullcheck run [--workers 14] [--limit N]  runs the phases; resumable (state in runs/null/)
  ~/.venvs/fastbt/bin/python -m engine.nullcheck report                         null/REPORT.json + a table

Phases (stage-synchronous, so 14 workers stay busy):
  1 screen     default point (grid centre), full research period; zone on M0 (only M0 is run: the zone uses M0 alone)
  2 amber      up to 3 variations, chosen as a lane would: first the slices that were green on their own (session / vol / regime
               -> that filter; bloc -> that symbol group; 'recent' -> a regime date from the fixed list), then menu draws; each
               variation is screened; a regime variation is green if its trades from the regime date are green
  3 grid       3 x 3 (stop x exit multipliers), all four news modes, for every green base or variation
  4 G1         walk-forward selection and stitching (engine/pipeline.py); eligible = passes or near-misses in M1, M2 or M3
  5 stress     noise (jitter 1 spread, signals +1 bar, A4.4), cost (spread x1.5, swap x1.5 for B / C), positive swap 0 (B / C), on the
               grid; neighbours, best year, top 5, FX 2015, long / short, without the best symbol (A4) from the stitched logs
  6 verdict    reached the gatekeeper = pass or near miss in at least one eligible mode, on any route
Outputs: shares green / amber / red, rescued by amber, through G1, through G2, reached; the same for +0.05 R and +0.10 R; the
zero-edge Sharpe distribution of the unseen period (for the luck bar, §7) and the grid-correlation factor.
"""
import argparse
import json
import os
import sys
import time

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from engine import metrics as M, pipeline as P, runner as R  # noqa: E402
from engine.costs import load as load_costs  # noqa: E402
from engine.context import bloc  # noqa: E402

PLAN = os.path.join(REPO, "null", "PLAN.json")
STATE_DIR = os.path.join(REPO, "runs", "null")
STRATEGY = "strategies/null_random.py:intents"
AXES = ("stop_mult", "exit_mult", "entry_variant")          # grid axes in this order (a card's tuned parameters map onto them)
BROAD_SHAPE = [3, 3]
PROFILES = os.path.join(REPO, "null", "card-profiles.json")
DATA_ONLY = ("AUS200", "F40", "HK50")
MENU = [{"session": "asia"}, {"session": "london"}, {"session": "ny"}, {"vol": "low"}, {"vol": "mid"}, {"vol": "high"},
        {"regime": "trend"}, {"regime": "range"}]
PERIOD = ["2014-11", "2024-12"]


def axis_values(name, k):
    if name == "entry_variant":
        return [float(v) for v in range(k)]
    return [1.0] if k == 1 else [round(float(1.33 ** x), 4) for x in np.linspace(-1, 1, k)]   # geometric, centre 1.0 (the default)


def grid_points(shape):
    """Flat grid (C order) for a shape of up to 3 axes: stop multiplier, exit multiplier, entry variant."""
    vals = [axis_values(AXES[a], k) for a, k in enumerate(shape)]
    return [{AXES[a]: float(v) for a, v in enumerate(combo)}
            for combo in np.array(np.meshgrid(*vals, indexing="ij")).reshape(len(shape), -1).T]


def centre(shape):
    return int(np.ravel_multi_index([k // 2 for k in shape], shape))


# ------------------------------------------------------------------ plan
def make_plan(n=1000, n_edge=100, seed=20261112, profiles=None):
    """DESIGN A3.6: half the strategies drawn from the committed cards' declared profiles (null/card-profiles.json, a snapshot with
    card ids and versions), half from the broad spread."""
    rng = np.random.default_rng(seed)
    syms = sorted(s for s in load_costs()["symbols"] if s not in DATA_ONLY)
    cards = (profiles or {}).get("cards", [])
    out = []

    def from_card(k, kind, edge):
        c = cards[int(rng.integers(len(cards)))]
        cls, tf = c["class"], c["timeframe"]
        sy = [x for x in c["symbols"] if x in syms] or [str(rng.choice(syms))]
        freq = max(float(c["trades_per_year"]) / len(sy), 1.0)
        stop = float(c.get("stop_atr") or rng.choice([1.0, 1.5, 2.0, 3.0]))
        if c.get("exit") == "target":
            target, hold = float(c.get("target_r") or rng.choice([1.0, 1.5, 2.0, 3.0])), 0.0
        else:
            target, hold = 0.0, float(c.get("hold_h") or rng.choice({"A": [2, 4, 8], "B": [24, 48, 72], "C": [72, 120, 240]}[cls]))
        shape = [int(x) for x in c.get("grid", [1])][:3] or [1]
        menu = [MENU[i] for i in rng.permutation(len(MENU))]
        return {"id": f"N{k:04d}", "kind": kind, "edge_r": edge, "profile": "card", "card": c["card"], "class": cls, "timeframe": tf,
                "symbols": sorted(sy), "grid_shape": shape,
                "params": {"seed": int(rng.integers(1, 2**31)), "freq": freq, "stop_atr": stop, "target_r": target, "hold_h": hold},
                "menu": menu, "regime_date": str(rng.choice(P.TH["null"]["regime_dates"]))}

    def one(k, kind, edge):
        if cards and rng.random() < 0.5:
            return from_card(k, kind, edge)
        cls = str(rng.choice(["A", "B", "C"]))
        tf = str(rng.choice({"A": ["m15", "h1"], "B": ["h1", "h4"], "C": ["h1", "h4"]}[cls]))
        k_sym = int(rng.integers(1, 5))
        sy = sorted(rng.choice(syms, k_sym, replace=False).tolist())
        freq = float(rng.choice([50, 150, 400])) / k_sym                  # A3.6: trades per year 50 / 150 / 400, over the symbols
        stop = float(rng.choice([1.0, 1.5, 2.0, 3.0]))
        if rng.random() < 0.6:
            target, hold = float(rng.choice([1.0, 1.5, 2.0, 3.0])), 0.0
        else:
            target, hold = 0.0, float(rng.choice({"A": [2, 4, 8], "B": [24, 48, 72], "C": [72, 120, 240]}[cls]))
        menu = [MENU[i] for i in rng.permutation(len(MENU))]
        return {"id": f"N{k:04d}", "kind": kind, "edge_r": edge, "profile": "broad", "class": cls, "timeframe": tf, "symbols": sy,
                "grid_shape": list(BROAD_SHAPE),
                "params": {"seed": int(rng.integers(1, 2**31)), "freq": freq, "stop_atr": stop, "target_r": target, "hold_h": hold},
                "menu": menu, "regime_date": str(rng.choice(P.TH["null"]["regime_dates"]))}
    k = 1
    for kind, edge, cnt in (("random", 0.0, n), ("edge05", 0.05, n_edge), ("edge10", 0.10, n_edge)):
        for _ in range(cnt):
            out.append(one(k, kind, edge))
            k += 1
    return {"about": "Null calibration plan (DESIGN §8, A3), generated by engine/nullcheck.py; the 'card' of every null-lane job.",
            "seed": seed, "axes": AXES, "period": PERIOD,
            "card_snapshot": [{"card": c["card"], "version": c.get("version")} for c in cards], "strategies": out}


# ------------------------------------------------------------------ jobs and waiting
def job(st, stage, params_extra=None, filters=None, symbols=None, modes=None, stress=None, noise=None):
    shape = st["grid_shape"]
    p = dict(st["params"], **(params_extra or grid_points(shape)[centre(shape)]))
    gsize = int(np.prod(shape))
    return {"idea_id": st["id"], "card": os.path.relpath(PLAN, REPO), "lane": "null", "stage": stage, "strategy": STRATEGY,
            "params": p, "grid_id": f"{st['id']}-grid" if stage.endswith("grid") or "stress" in stage else None,
            "grid_size": gsize if (stage.endswith("grid") or "stress" in stage) else 1, "symbols": symbols or st["symbols"],
            "timeframe": st["timeframe"], "period": PERIOD, "class": st["class"], "modes": modes or list(R.rules.MODES),
            "filters": filters or {}, "stress": stress or {}, "noise": noise, "synthetic_edge_r": st["edge_r"]}


def submit_all(jobs, require_committed=True):
    ids = []
    os.makedirs(os.path.join(R.QUEUE, "pending"), exist_ok=True)
    stamp = time.strftime("%Y%m%d%H%M%S")
    for k, j in enumerate(jobs):
        j = R.validate(j, require_committed)
        j["job_id"] = f"JN{stamp}{k:06d}"
        j["submitted_utc"] = stamp
        json.dump(j, open(os.path.join(R.QUEUE, "pending", j["job_id"] + ".json"), "w"))
        ids.append(j["job_id"])
    return ids


def ledger_by_job():
    out = {}
    if not os.path.isdir(R.LEDGER):
        return out
    for f in sorted(os.listdir(R.LEDGER)):
        if f.endswith(".jsonl"):
            for line in open(os.path.join(R.LEDGER, f)):
                if line.strip():
                    r = json.loads(line)
                    out[r.get("job_id")] = r
    return out


def wait(ids, workers, log):
    """Runs the queue until every job id has a ledger row or failed."""
    while True:
        rows = ledger_by_job()
        failed = {os.path.basename(p)[:-5] for p in os.listdir(os.path.join(R.QUEUE, "failed"))} \
            if os.path.isdir(os.path.join(R.QUEUE, "failed")) else set()
        missing = [i for i in ids if i not in rows and i not in failed]
        if not missing:
            return {i: rows.get(i) for i in ids}
        if not R.run_batch(workers, log=log):
            time.sleep(10)


def logs_of(row, modes):
    return P.load_logs(os.path.join(REPO, row["run_path"]), row["symbols"], modes)


# ------------------------------------------------------------------ phases
def run(workers=R.WORKERS, limit=None, require_committed=True, log=print):
    plan = json.load(open(PLAN))
    strats = plan["strategies"][:limit] if limit else plan["strategies"]
    os.makedirs(STATE_DIR, exist_ok=True)
    sp = os.path.join(STATE_DIR, "state.json")
    S = json.load(open(sp)) if os.path.isfile(sp) else {}

    def save():
        json.dump(S, open(sp, "w"))

    by_id = {s["id"]: s for s in strats}
    # 1 screen
    todo = [s for s in strats if "screen" not in S.get(s["id"], {})]
    if todo:
        ids = submit_all([job(s, "null-screen", modes=["M0"]) for s in todo], require_committed)
        res = wait(ids, workers, log)
        for s, i in zip(todo, ids):
            r = res[i]
            if r is None:
                S[s["id"]] = {"screen": {"zone": "error"}}
                continue
            lg = logs_of(r, ["M0"])["M0"]
            z = P.screen_zone(lg, edge_r=r.get("synthetic_edge_r") or 0.0)
            z["amber_rule"] = "mid"                                       # DESIGN A11.1
            z["sharpe_unseen"] = sharpe_unseen(lg, "r_net_ftmo")
            z["sharpe_unseen_gross"] = sharpe_unseen(lg, "r_gross")         # after FTMO's spread (the kernel's R)
            z["sharpe_unseen_mid"] = sharpe_unseen(lg, "r_mid")             # at mid prices: before every cost
            S[s["id"]] = {"screen": dict(z, test_id=r["test_id"]), "routes": []}
        save()
    # DESIGN A9.6: the luck bar uses the Sharpe before costs (mid prices); fill it in for earlier screens (same rows, nothing re-run)
    miss = [sid for sid in by_id if sid in S and S[sid]["screen"].get("test_id") and "sharpe_unseen_mid" not in S[sid]["screen"]]
    for sid in miss:
        lg = logs_of(R_row(S[sid]["screen"]["test_id"]), ["M0"])["M0"]
        for key, col in (("sharpe_unseen_mid", "r_mid"), ("sharpe_unseen_gross", "r_gross"), ("sharpe_unseen", "r_net_ftmo")):
            S[sid]["screen"][key] = sharpe_unseen(lg, col)
    if miss:
        save()
    # DESIGN A11.1: amber judged before costs (r_mid + the planted edge). Re-derive the zone of every screen judged by the old rule
    # (t after the spread) from its trade file; a strategy whose zone changes gets (or loses) its amber variations below.
    old = [sid for sid in by_id if sid in S and S[sid]["screen"].get("test_id") and S[sid]["screen"].get("amber_rule") != "mid"]
    for sid in old:
        row = R_row(S[sid]["screen"]["test_id"])
        z = P.screen_zone(logs_of(row, ["M0"])["M0"], edge_r=row.get("synthetic_edge_r") or 0.0)
        sc = S[sid]["screen"]
        if z["zone"] != sc["zone"]:
            sc["zone_before_a11"] = sc["zone"]
            if sc["zone"] == "amber":                                    # no longer amber: its variations and their routes go
                S[sid]["dropped_a11"] = {"variations": S[sid].pop("variations", None),
                                         "routes": [x for x in S[sid].get("routes", []) if x["route"] != "base"]}
                S[sid]["routes"] = [x for x in S[sid].get("routes", []) if x["route"] == "base"]
        sc.update(zone=z["zone"], green_slices=z["green_slices"], t_mid=z["t_mid"], t_gross=z["t_gross"], amber_rule="mid")
    if old:
        log(f"A11.1 re-zoned {len(old)} screens: {sum('zone_before_a11' in S[x]['screen'] for x in old)} changed zone")
        save()
    # 2 amber variations
    todo = [s for s in strats if S[s["id"]]["screen"].get("zone") == "amber" and "variations" not in S[s["id"]]]
    jobs, owners = [], []
    for s in todo:
        vs = variations(s, S[s["id"]]["screen"]["green_slices"])
        S[s["id"]]["variations"] = vs
        for k, v in enumerate(vs):
            if v["type"] == "regime":
                base = logs_of(R_row(S[s["id"]]["screen"]["test_id"]), ["M0"])["M0"]
                cut = P.take(base, base["entry_t"] >= P.month_ms(v["date"]))
                v["zone"] = "green" if P.is_green(cut["r_net_ftmo"].astype(float)) else "not green"
            else:
                jobs.append(job(s, f"null-amber-V{k + 1}", filters=v.get("filters"), symbols=v.get("symbols"), modes=["M0"]))
                owners.append((s["id"], k))
    if jobs:
        ids = submit_all(jobs, require_committed)
        res = wait(ids, workers, log)
        for (sid, k), i in zip(owners, ids):
            r = res[i]
            v = S[sid]["variations"][k]
            v["test_id"] = r["test_id"] if r else None
            v["zone"] = P.screen_zone(logs_of(r, ["M0"])["M0"], edge_r=r.get("synthetic_edge_r") or 0.0)["zone"] if r else "error"
    save()
    # 3 grids for green routes
    routes = []
    for s in strats:
        st = S[s["id"]]
        if st["screen"].get("zone") == "green":
            routes.append((s["id"], {"route": "base"}))
        for k, v in enumerate(st.get("variations", [])):
            if v.get("zone") == "green":
                routes.append((s["id"], dict(v, route=f"V{k + 1}")))
    jobs, owners = [], []
    for sid, rt in routes:
        st = S[sid]
        if any(x["route"] == rt["route"] for x in st["routes"]):
            continue
        s = by_id[sid]
        st["routes"].append({"route": rt["route"], "def": rt})
        for g, pt in enumerate(grid_points(s["grid_shape"])):
            jobs.append(job(s, "null-grid", params_extra=pt, filters=rt.get("filters"), symbols=rt.get("symbols")))
            owners.append((sid, rt["route"], "grid", g))
    if jobs:
        ids = submit_all(jobs, require_committed)
        res = wait(ids, workers, log)
        for (sid, route, kind, g), i in zip(owners, ids):
            rr = next(x for x in S[sid]["routes"] if x["route"] == route)
            rr.setdefault(kind, [None] * int(np.prod(by_id[sid]["grid_shape"])))[g] = res[i]["test_id"] if res[i] else None
    save()
    # 4 G1
    for sid, st in S.items():
        if sid not in by_id:
            continue
        for rr in st.get("routes", []):
            if "g1" in rr or not rr.get("grid") or None in rr["grid"]:
                continue
            gl = [logs_of(R_row(t), list(R.rules.MODES)) for t in rr["grid"]]
            shape = tuple(by_id[sid]["grid_shape"])
            ch = P.wf_select(gl, shape, default=centre(shape))
            frm = P.month_ms(rr["def"]["date"]) if rr["def"].get("type") == "regime" else None
            rr["choices"] = ch
            rr["g1"] = {}
            for m in R.rules.MODES:
                st_log = P.wf_stitch(gl, ch, m)
                rr["g1"][m] = P.g1(st_log, from_ms=frm, k=None)                   # luck bar: in the report (A11.4 sigma from vr)
                rr["g1"][m]["vr"] = round(P.variance_ratio(P.take(st_log, st_log["entry_t"] >= frm) if frm else st_log, frm), 4)
            rr["eligible"] = P.eligible_modes(rr["g1"])
            rr["sharpe_m0"] = rr["g1"]["M0"]["daily_sharpe"]
    save()
    # 5 stress runs for eligible routes
    jobs, owners = [], []
    for sid, st in S.items():
        if sid not in by_id:
            continue
        s = by_id[sid]
        for rr in st.get("routes", []):
            if not rr.get("eligible") or "noise" in rr:
                continue
            kinds = {"noise": dict(noise={"seed": 7, "jitter_spreads": 1.0, "shift_bars": 1}),
                     "cost": dict(stress={"spread_mult": 1.5, "swap_mult": 1.5 if s["class"] in ("B", "C") else 1.0})}
            if s["class"] in ("B", "C"):
                kinds["swap0"] = dict(stress={"zero_positive_swap": True})
            for kind, kw in kinds.items():
                for g, pt in enumerate(grid_points(s["grid_shape"])):
                    jobs.append(job(s, f"null-stress-{kind}", params_extra=pt, filters=rr["def"].get("filters"),
                                    symbols=rr["def"].get("symbols"), **kw))
                    owners.append((sid, rr["route"], kind, g))
    if jobs:
        ids = submit_all(jobs, require_committed)
        res = wait(ids, workers, log)
        for (sid, route, kind, g), i in zip(owners, ids):
            rr = next(x for x in S[sid]["routes"] if x["route"] == route)
            rr.setdefault(kind, [None] * int(np.prod(by_id[sid]["grid_shape"])))[g] = res[i]["test_id"] if res[i] else None
    save()
    # 6 G2 and verdict
    for sid, st in S.items():
        if sid not in by_id:
            continue
        s = by_id[sid]
        for rr in st.get("routes", []):
            if not rr.get("eligible") or "verdict" in rr or None in rr.get("noise", [None]):
                continue
            modes = list(R.rules.MODES)
            gl = [logs_of(R_row(t), modes) for t in rr["grid"]]
            stressed_runs = {k: [logs_of(R_row(t), modes) for t in rr[k]] for k in ("noise", "cost", "swap0") if k in rr}
            frm = P.month_ms(rr["def"]["date"]) if rr["def"].get("type") == "regime" else None
            fx = any(c == "usd" or c == "none" for c in (bloc(x) for x in s["symbols"]))
            rr["g2"], rr["verdict"] = {}, {}
            for m in rr["eligible"]:
                base = P.wf_stitch(gl, rr["choices"], m)
                stressed = {k: P.wf_stitch(v, rr["choices"], m) for k, v in stressed_runs.items()}
                if fx:
                    ch2 = P.wf_select(gl, tuple(s["grid_shape"]), exclude=P.fx_quarantine_mask, default=centre(tuple(s["grid_shape"])))
                    stressed["fx2015"] = P.wf_stitch(gl, ch2, m)
                nbs = neighbour_paths(gl, rr["choices"], m, tuple(s["grid_shape"]))
                g2 = P.g2(base, m, s["class"], fx, stressed, nbs, P.stress_g1(rr["g1"][m], frm),
                          declared_symbols=rr["def"].get("symbols") or s["symbols"])
                rr["g2"][m] = g2
                rr["verdict"][m] = P.verdict(rr["g1"][m], g2)
    save()
    return S


def route_bar(rr, mode, k):
    frm = P.month_ms(rr["def"]["date"]) if rr["def"].get("type") == "regime" else None
    return P.luck_bar(k, frm, rr["g1"][mode].get("vr", 1.0))["bar"]


# ------------------------------------------------------------------ cost-neutral null (DESIGN A11.5)
FIRST_COL = {"session": "session", "vol": "vol_third", "regime": "regime"}


def cost_neutral(S=None, write=True):
    """The 1,000 random strategies with net R := R at mid prices (zero edge, no costs), from their screen trade files; no new runs.
    Screen zone on mid; the lane-style amber variations (variations()) applied to the screen log as slices; the G1 bars (before the
    luck bar) on each green route's unseen trades of the default path, M0 (no grid, no walk-forward: a proxy, as the sceptic's).
    Shares: green at the screen, >= 1 green route, through the G1 bars before the luck bar, and with the A11 luck bar at k."""
    plan = json.load(open(PLAN))
    if S is None:
        S = json.load(open(os.path.join(STATE_DIR, "state.json")))
    first = P.month_ms(P.TH["walk_forward"]["first_test"])
    per = []
    for s in plan["strategies"]:
        if s["kind"] != "random" or s["id"] not in S or not S[s["id"]]["screen"].get("test_id"):
            continue
        lg = logs_of(R_row(S[s["id"]]["screen"]["test_id"]), ["M0"])["M0"]
        lg = dict(lg, r_net_ftmo=lg["r_mid"].astype(float))
        z = P.screen_zone(lg)
        routes = []
        if z["zone"] == "green":
            routes.append(("base", np.ones(P.n_of(lg), bool), None))
        if z["zone"] == "amber":
            for k, v in enumerate(variations(s, z["green_slices"])):
                if v["type"] == "filter":
                    (key, val), = v["filters"].items()
                    m, frm = lg[FIRST_COL[key]].astype(str) == val, None
                elif v["type"] == "symbols":
                    m, frm = np.isin(lg["symbol"].astype(str), v["symbols"]), None
                else:
                    frm = P.month_ms(v["date"])
                    m = lg["entry_t"] >= frm
                if P.is_green(lg["r_net_ftmo"][m]):
                    routes.append((f"V{k + 1}", m, frm))
        rr = []
        for name, m, frm in routes:
            sub = P.take(lg, m & (lg["entry_t"] >= (frm if frm is not None else first)))
            g = P.g1(sub, from_ms=frm, k=None)
            rr.append({"route": name, "from_ms": frm, "pass_before_luck": g["pass"], "failed": g["failed"],
                       "sharpe": g["daily_sharpe"], "vr": round(P.variance_ratio(sub, frm), 4)})
        per.append({"id": s["id"], "zone": z["zone"], "routes": rr})
    n = len(per)
    sh = lambda f: round(sum(1 for x in per if f(x)) / n, 4) if n else None
    rates = {"n": n, "amber_at_screen": sh(lambda x: x["zone"] == "amber"), "green_at_screen": sh(lambda x: x["zone"] == "green"),
             "green_route": sh(lambda x: bool(x["routes"])),
             "g1_before_luck": sh(lambda x: any(r["pass_before_luck"] for r in x["routes"])),
             "g1_routes_before_luck": sum(r["pass_before_luck"] for x in per for r in x["routes"]),
             "best_route_sharpe": max([r["sharpe"] for x in per for r in x["routes"] if r["sharpe"] is not None] or [None],
                                      key=lambda v: -9 if v is None else v)}
    for k in (10, 100, 1000):
        rates[f"with_luck_k{k}"] = sh(lambda x: any(r["pass_before_luck"] and (r["sharpe"] or -9) >= P.luck_bar(k, r["from_ms"], r["vr"])["bar"]
                                                for r in x["routes"]))
    out = {"about": cost_neutral.__doc__.split("\n")[0], "proxy": "default path, M0, amber variations as slices of the screen log, "
           "no grid, no walk-forward, no G2 (sceptic re-check C)", "engine_hash": R.engine_hash(), "rates": rates, "per_strategy": per}
    if write:
        json.dump(out, open(os.path.join(REPO, "null", "COST-NEUTRAL.json"), "w"), indent=1)
    return out


_ROWS = {}


def sharpe_unseen(lg, col):
    """Daily Sharpe of a screen log over the unseen years (first walk-forward test month to the end of the period)."""
    un = P.take(lg, lg["entry_t"] >= P.month_ms(P.TH["walk_forward"]["first_test"]))
    o = np.argsort(un["exit_t"], kind="stable")
    return M.daily_sharpe(un[col].astype(float)[o], un["exit_t"][o], P.month_ms(P.TH["walk_forward"]["first_test"]),
                          P.month_ms(PERIOD[1], 1)) if len(o) > 1 else None


def R_row(test_id):
    if test_id not in _ROWS:                     # refresh: later phases add rows
        for r in ledger_by_job().values():
            _ROWS[r["test_id"]] = r
    return _ROWS[test_id]


def variations(s, green_slices):
    """Up to 3 amber variations: the green slices first (as a lane would pick them), then menu draws."""
    out = []
    seen = set()
    for g in green_slices:
        k, _, v = g.partition("=")
        if k in ("session", "vol", "regime"):
            f = {k: v}
            key = json.dumps(f, sort_keys=True)
            if key not in seen:
                seen.add(key)
                out.append({"type": "filter", "filters": f, "reason": f"slice {g} green"})
        elif k == "bloc":
            sy = [x for x in s["symbols"] if bloc(x) == v]
            if sy and sy != s["symbols"] and ("bloc", v) not in seen:
                seen.add(("bloc", v))
                out.append({"type": "symbols", "symbols": sy, "reason": f"slice {g} green"})
        elif g == "recent" and "recent" not in seen:
            seen.add("recent")
            out.append({"type": "regime", "date": s["regime_date"], "reason": "recent slice green"})
        if len(out) == 3:
            return out
    for f in s["menu"]:
        key = json.dumps(f, sort_keys=True)
        if key not in seen:
            seen.add(key)
            out.append({"type": "filter", "filters": f, "reason": "menu draw"})
        if len(out) == 3:
            break
    return out


def neighbour_paths(gl, choices, mode, SHAPE):
    """Stitched logs with every chosen point moved one grid step along each axis (both ways, where the grid allows)."""
    out = []
    for ax in range(len(SHAPE)):
        for d in (-1, 1):
            moved = []
            for c in choices:
                pos = list(np.unravel_index(c, SHAPE))
                pos[ax] = min(max(pos[ax] + d, 0), SHAPE[ax] - 1)
                moved.append(int(np.ravel_multi_index(pos, SHAPE)))
            if moved != list(choices):
                out.append(P.wf_stitch(gl, choices, mode, offsets=moved))
    return out


# ------------------------------------------------------------------ report
def report(S=None, write=True):
    plan = json.load(open(PLAN))
    if S is None:
        S = json.load(open(os.path.join(STATE_DIR, "state.json")))
    out = {}
    for kind in ("random", "edge05", "edge10"):
        ids = [s["id"] for s in plan["strategies"] if s["kind"] == kind and s["id"] in S]
        n = len(ids)
        if not n:
            continue
        z = [S[i]["screen"].get("zone") for i in ids]
        g1 = [i for i in ids if any(r.get("eligible") for r in S[i].get("routes", []))]
        reached = [i for i in ids if any(v in ("pass", "near_miss") for r in S[i].get("routes", []) for v in r.get("verdict", {}).values())]
        rescued = [i for i in ids if S[i]["screen"].get("zone") == "amber" and any(r["route"] != "base" for r in S[i].get("routes", []))]
        out[kind] = {"n": n, "green": z.count("green") / n, "amber": z.count("amber") / n, "red": z.count("red") / n,
                     "amber_rescued": len(rescued) / n, "through_g1": len(g1) / n, "reached_gatekeeper": len(reached) / n,
                     "reached_ids": reached}
    # zero-edge Sharpe of the default path over the unseen years (random kind only): the luck bar's raw material (§7).
    # DESIGN A9.6: built from the Sharpe BEFORE costs, at mid prices (zero edge by construction). Kept for reference: after FTMO's
    # spread only (r_gross, the kernel's R) and after all costs.
    def luck(key):
        sh = np.array([S[s["id"]]["screen"].get(key) for s in plan["strategies"]
                       if s["kind"] == "random" and s["id"] in S and S[s["id"]]["screen"].get(key) is not None], float)
        if len(sh) <= 2:
            return {"n": int(len(sh)), "mean": None, "sd": None, "luck_bar_95th_of_best_of_k_normal_fit": {}}
        mu, sd = float(sh.mean()), float(sh.std(ddof=1))
        from statistics import NormalDist
        return {"n": int(len(sh)), "mean": round(mu, 4), "sd": round(sd, 4),
                "luck_bar_95th_of_best_of_k_normal_fit": {str(k): round(mu + sd * NormalDist().inv_cdf(0.95 ** (1 / k)), 3)
                                                          for k in (1, 10, 100, 1000, 3000)}}
    out["zero_edge_sharpe_unseen_mid"] = luck("sharpe_unseen_mid")
    out["zero_edge_sharpe_unseen_after_spread_reference"] = luck("sharpe_unseen_gross")
    out["zero_edge_sharpe_unseen_net_reference"] = luck("sharpe_unseen")
    # the trade-off table with the luck bar applied (DESIGN A10.3 as amended by A11.4): reached = pass / near miss in a mode whose
    # stitched unseen daily Sharpe clears mu0 (0) + sigma0 * sqrt(8.17 / unseen years) * max(1, sqrt(VR)) * Phi^-1(0.95^(1/k)),
    # VR the mode's Newey-West ratio (a safety bar: no near miss on it)
    out["with_luck_bar"] = {}
    for k in (10, 100, 1000):
        row = {}
        for kind in ("random", "edge05", "edge10"):
            ids = [s["id"] for s in plan["strategies"] if s["kind"] == kind and s["id"] in S]
            if not ids:
                continue
            ok = [i for i in ids if any(v in ("pass", "near_miss") and (r["g1"][m].get("daily_sharpe") or -9) >= route_bar(r, m, k)
                                        for r in S[i].get("routes", []) for m, v in r.get("verdict", {}).items())]
            row[kind] = {"share": len(ok) / len(ids), "ids": ok}
        out["with_luck_bar"][str(k)] = dict(row, bar_full_period_vr1=P.luck_bar(k)["bar"])
    # DESIGN A11.1 raise-only triggers (the gatekeeper writes the addendum): random amber > 10%; random reaching the gatekeeper
    # with the luck bar > 0.5% (at k = 100, the first batch's order)
    rnd = out.get("random", {})
    out["a11_triggers"] = {"random_amber": rnd.get("amber"), "amber_cutoff_raise": (rnd.get("amber") or 0) > 0.10,
                           "random_reached_with_luck_k100": out["with_luck_bar"].get("100", {}).get("random", {}).get("share"),
                           "luck_bar_raise": (out["with_luck_bar"].get("100", {}).get("random", {}).get("share") or 0)
                           > P.TH["null"]["target_share"]}
    # A11.1 re-derivation: zones that changed, and the rescue share
    out["a11_rezone"] = {}
    for kind in ("random", "edge05", "edge10"):
        ids = [s["id"] for s in plan["strategies"] if s["kind"] == kind and s["id"] in S]
        ch = [i for i in ids if "zone_before_a11" in S[i]["screen"]]
        out["a11_rezone"][kind] = {"changed": len(ch), "red_to_amber": sum(S[i]["screen"]["zone_before_a11"] == "red" and
                                                                           S[i]["screen"]["zone"] == "amber" for i in ch),
                                   "amber_to_red": sum(S[i]["screen"]["zone_before_a11"] == "amber" and S[i]["screen"]["zone"] == "red"
                                                       for i in ch)}
    # DESIGN A9.1: fit risk (FTMO, % per trade) of the strategies that reach the gatekeeper: the best over their passing routes / modes
    out["fit_risk_reached"] = {}
    for kind in ("random", "edge05", "edge10"):
        v = []
        for i in out.get(kind, {}).get("reached_ids", []):
            fr = [r["g1"][m]["fit_risk_pct"]["FTMO"] for r in S[i]["routes"] for m, vv in r.get("verdict", {}).items()
                  if vv in ("pass", "near_miss") and r["g1"][m].get("fit_risk_pct", {}).get("FTMO") is not None]
            if fr:
                v.append(max(fr))
        if v:
            a = np.array(v)
            out["fit_risk_reached"][kind] = {"n": len(v), "min": round(float(a.min()), 3), "p25": round(float(np.percentile(a, 25)), 3),
                                             "median": round(float(np.median(a)), 3), "p75": round(float(np.percentile(a, 75)), 3),
                                             "max": round(float(a.max()), 3), "share_ge_funded_0.75": round(float((a >= 0.75).mean()), 3),
                                             "share_ge_0.25": round(float((a >= 0.25).mean()), 3)}
    # G2 fail reasons, per route and eligible mode (a route can fail several tests)
    out["g2_fail_reasons"] = {}
    for kind in ("random", "edge05", "edge10"):
        c, n_fail, n_all = {}, 0, 0
        for s in plan["strategies"]:
            if s["kind"] != kind or s["id"] not in S:
                continue
            for r in S[s["id"]].get("routes", []):
                for m, g in r.get("g2", {}).items():
                    n_all += 1
                    if g["failed"]:
                        n_fail += 1
                    for k in g["failed"]:
                        c[k] = c.get(k, 0) + 1
        out["g2_fail_reasons"][kind] = {"route_modes": n_all, "failed": n_fail, "tests": dict(sorted(c.items(), key=lambda x: -x[1]))}
    if write:
        json.dump(out, open(os.path.join(REPO, "null", "REPORT.json"), "w"), indent=1)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("plan", "run", "report", "cost-neutral"))
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--edge", type=int, default=100)
    ap.add_argument("--workers", type=int, default=R.WORKERS)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args(argv)
    if a.action == "plan":
        os.makedirs(os.path.dirname(PLAN), exist_ok=True)
        prof = json.load(open(PROFILES)) if os.path.isfile(PROFILES) else None
        if prof is None:
            print("no null/card-profiles.json: every profile from the broad spread (A3.6 wants half from the cards)")
        json.dump(make_plan(a.n, a.edge, profiles=prof), open(PLAN, "w"), indent=1)
        print("wrote", os.path.relpath(PLAN, REPO), "- commit it before 'run'")
    elif a.action == "run":
        run(a.workers, a.limit, log=lambda s: print(time.strftime("%H:%M:%S"), s, flush=True))
        print(json.dumps(report(), indent=1))
    elif a.action == "cost-neutral":
        print(json.dumps(cost_neutral()["rates"], indent=1))
    else:
        print(json.dumps(report(), indent=1))


if __name__ == "__main__":
    main()
