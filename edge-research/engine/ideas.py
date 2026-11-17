"""The real-idea route (DESIGN §6.3-6.6, A10.4, A11): screen zone -> tune grid -> walk-forward G1 with the ledger's k.

Pure reading of ledger rows and trade files; nothing here runs a backtest (the runner does) or writes the ledger (only the runner
does). A route's G1 judgement is appended to results/g1.jsonl (one row per judgement, never edited): the stored daily Sharpe,
k, sigma, VR and luck bar per news mode are what gatekeeper/open_locked.py re-checks before a locked-period open (A11.4).

  ~/.venvs/fastbt/bin/python -m engine.ideas screen IDEA-1000             zone of the idea's screen row(s)
  ~/.venvs/fastbt/bin/python -m engine.ideas batch                        the weekly batch test (A11.5) as JSON
"""
import argparse
import itertools
import json
import os
import sys
import time

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from engine import pipeline as P, rules  # noqa: E402
from engine.hash import engine_hash  # noqa: E402

RESULTS = os.path.join(REPO, "results")
G1_FILE = os.path.join(RESULTS, "g1.jsonl")
NULL_CN = os.path.join(REPO, "null", "COST-NEUTRAL.json")


def load_row(row, modes):
    return P.load_logs(os.path.join(REPO, row["run_path"]), row["symbols"], modes)


def screen_stage(route):
    return "screen" if route == "base" else f"amber-{route}"


# ------------------------------------------------------------------ screen
def screen_result(row, load=load_row):
    """The zone of one screen / amber row (M0, FTMO costs; amber before costs, A11.1)."""
    z = P.screen_zone(load(row, ["M0"])["M0"])
    return dict(z, idea_id=row["idea_id"], stage=row["stage"], route=P.route_of(row), test_id=row["test_id"])


# ------------------------------------------------------------------ tune -> G1
def grid_points(axes):
    """axes: [(param name, [values]), ...] in the card's order -> (shape, list of value tuples in C order)."""
    shape = tuple(len(v) for _, v in axes)
    return shape, list(itertools.product(*[list(v) for _, v in axes]))


def route_g1(idea_id, route, axes, rows=None, from_ms=None, load=load_row, rho_fn=P.route_rho):
    """G1 of one route of a real idea from its tune rows in the ledger.
    axes: the card's declared grid [(param, [values])...]; every point must have exactly one real 'tune' row of this route whose
    other parameters, symbols and filters equal the route's screen row. The screen row's parameters are the card defaults: the
    walk-forward falls back to them in a training window without trades (A11.2). k = count_k over the ledger rows now (A10.4,
    A11.3-4); each news mode is judged with that k (luck bar with sigma from the mode's VR, A11.4)."""
    rows = P.read_ledger() if rows is None else rows
    mine = [r for r in rows if P.is_real(r) and r.get("idea_id") == idea_id]
    scr = [r for r in mine if r.get("stage") == screen_stage(route)]
    if not scr:
        raise ValueError(f"{idea_id}/{route}: no {screen_stage(route)} row")
    scr = scr[0]
    names = [a for a, _ in axes]
    shape, pts = grid_points(axes)
    pinned = P.first_screen_flags([r for r in rows if P.is_real(r)]).get(idea_id, {}).get("grid_size")
    if pinned != len(pts):                                              # sceptic re-check (D): the axes are the declared grid
        raise ValueError(f"{idea_id}/{route}: the axes give {len(pts)} points, the first screen row's grid size is {pinned}")
    rest = {k: v for k, v in (scr.get("variant") or {}).items() if k not in names}
    by = {}
    for r in mine:
        if r.get("stage") != P.GRID_STAGE or P.route_of(r) != route:
            continue
        v = r.get("variant") or {}
        if {k: x for k, x in v.items() if k not in names} != rest or r["symbols"] != scr["symbols"] \
                or (r.get("filters") or {}) != (scr.get("filters") or {}):
            raise ValueError(f"{r['test_id']}: tune row differs from the route's screen row outside the grid axes")
        key = tuple(v.get(n) for n in names)
        if key not in pts:
            raise ValueError(f"{r['test_id']}: point {key} is not on the declared grid")
        if key in by:
            raise ValueError(f"{idea_id}/{route}: grid point {key} has two tune rows ({by[key]['test_id']}, {r['test_id']})")
        by[key] = r
    missing = [p for p in pts if p not in by]
    if missing:
        raise ValueError(f"{idea_id}/{route}: {len(missing)} of {len(pts)} grid points have no tune row yet")
    d_key = tuple((scr.get("variant") or {}).get(n) for n in names)
    if d_key not in pts:
        raise ValueError(f"{idea_id}/{route}: the screen's defaults {d_key} are not on the declared grid")
    modes = list(rules.MODES)
    grid_rows = [by[p] for p in pts]
    gl = [load(r, modes) for r in grid_rows]
    default = pts.index(d_key)
    choices = P.wf_select(gl, shape, default=default)
    kc = P.count_k(rows, idea_id, rho_fn=rho_fn)
    g = {m: P.g1(P.wf_stitch(gl, choices, m), from_ms=from_ms, k=kc["k"]) for m in modes}
    return {"idea_id": idea_id, "route": route, "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "engine_hash": engine_hash(),
            "axes": [[a, list(v)] for a, v in axes], "default_index": default, "choices": choices, "from_ms": from_ms,
            "tune_test_ids": [r["test_id"] for r in grid_rows], "screen_test_id": scr["test_id"],
            "card_flags": P.first_screen_flags([r for r in rows if P.is_real(r)])[idea_id], "k": kc, "g1": g,
            "eligible": P.eligible_modes(g)}


def record(res, path=None):
    """Append a route judgement to results/g1.jsonl (never edited)."""
    p = path or G1_FILE
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as fh:
        fh.write(json.dumps(res, default=lambda o: o.item() if hasattr(o, "item") else str(o)) + "\n")
    return res


def read_g1(path=None):
    p = path or G1_FILE
    return [json.loads(x) for x in open(p) if x.strip()] if os.path.isfile(p) else []


# ------------------------------------------------------------------ weekly batch test (A11.5)
def _before_luck(g):
    return [x for x in g["failed"] if x != "luck"]


def real_rates(rows=None, g1_rows=None, zone_fn=None):
    """Real ideas at the batch-test stages: green at the screen, >= 1 green route (screen or amber), through the G1 bars before
    the luck bar (any route, any mode M1-M3), through G1 with the luck bar. zone_fn(row) -> zone (default: screen_result)."""
    rows = P.read_ledger() if rows is None else rows
    g1_rows = read_g1() if g1_rows is None else g1_rows
    zone_fn = zone_fn or (lambda r: screen_result(r)["zone"])
    real = [r for r in rows if P.is_real(r)]
    ideas = sorted({r["idea_id"] for r in real if r.get("stage") == "screen"})
    green, route_green, g1_pre, g1_luck = set(), set(), set(), set()
    for r in real:
        if r.get("stage") in P.SCREEN_STAGES and r["idea_id"] in ideas:
            z = zone_fn(r)
            if z == "green":
                route_green.add(r["idea_id"])
                if r["stage"] == "screen":
                    green.add(r["idea_id"])
    for g in g1_rows:
        for m in ("M1", "M2", "M3"):
            if m in g["g1"] and not _before_luck(g["g1"][m]):
                g1_pre.add(g["idea_id"])
            if m in g["g1"] and g["g1"][m]["pass"]:
                g1_luck.add(g["idea_id"])
    n = len(ideas)
    sh = lambda s: round(len(s & set(ideas)) / n, 4) if n else None
    return {"ideas_screened": n, "green_at_screen": sh(green), "green_route": sh(route_green), "g1_before_luck": sh(g1_pre),
            "g1_with_luck": sh(g1_luck)}


def expected_noise_clears(g1_rows):
    """Per quarter: route judgements, and the expected number of zero-edge routes clearing the luck bar at the k in force,
    sum over routes of 1 - 0.95^(w / k), w = the route's k_eff weight (A10.4), k = the k it was judged at."""
    q = P.TH["luck_bar"]["quantile"]
    out = {}
    for g in g1_rows:
        y, mth = int(g["ts"][:4]), int(g["ts"][5:7])
        key = f"{y}-Q{(mth - 1) // 3 + 1}"
        k = g["k"]["k"]
        w = (g["k"].get("per_route") or {}).get(f"{g['idea_id']}/{g['route']}", {}).get("k_eff", g["k"].get("own_k_eff", 1.0))
        o = out.setdefault(key, {"routes_judged": 0, "expected_noise_clears": 0.0})
        o["routes_judged"] += 1
        o["expected_noise_clears"] = round(o["expected_noise_clears"] + 1 - q ** (min(w, k) / k), 4)
    return out


def locked_by_quarter(path=None):
    p = path or os.path.join(REPO, "gatekeeper", "locked-checks.jsonl")
    out = {}
    for x in (json.loads(l) for l in open(p) if l.strip()) if os.path.isfile(p) else []:
        y, mth = int(x["ts"][:4]), int(x["ts"][5:7])
        o = out.setdefault(f"{y}-Q{(mth - 1) // 3 + 1}", {"opened": 0, "refused_luck_bar": 0, "guard_passed": 0})
        o[{"opened": "opened", "refused: luck bar": "refused_luck_bar"}.get(x["result"], "guard_passed")] += 1
    return out


COST_NEUTRAL_NOTE = ("PROXY (sceptic re-check C): the cost-neutral null's green-route and 'G1 before luck' shares come from each random "
                     "strategy's default path on M0, amber variations as slices of the screen log, no grid, no walk-forward, no G2; "
                     "the real ideas' G1 shares are walk-forward on the grid, all modes. Compare the levels, not exactly.")


def batch_test(rows=None, g1_rows=None, zone_fn=None):
    """DESIGN §7 + A11.5: the real ideas' rates next to the cost-neutral null (null/COST-NEUTRAL.json) and the 0.5% reference;
    locked opens per quarter next to the expected false finalists from noise."""
    g1_rows = read_g1() if g1_rows is None else g1_rows
    cn = json.load(open(NULL_CN)) if os.path.isfile(NULL_CN) else None
    return {"real": real_rates(rows, g1_rows, zone_fn),
            "null_cost_neutral": None if cn is None else cn["rates"],
            "null_cost_neutral_note": COST_NEUTRAL_NOTE,
            "null_reference_reaching_gatekeeper": P.TH["null"]["target_share"],
            "locked_opens_by_quarter": locked_by_quarter(),
            "expected_noise_clears_by_quarter": expected_noise_clears(g1_rows)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("screen", "batch"))
    ap.add_argument("idea", nargs="?")
    a = ap.parse_args(argv)
    if a.action == "screen":
        rows = [r for r in P.read_ledger() if P.is_real(r) and r["idea_id"] == a.idea and r.get("stage") in P.SCREEN_STAGES]
        print(json.dumps([screen_result(r) for r in rows], indent=1))
    else:
        print(json.dumps(batch_test(), indent=1))


if __name__ == "__main__":
    main()
