"""Locked-period open (2025-01-01 ->): the gatekeeper's tool, once per candidate, with the user's go (CLAUDE.md, lanes/GATEKEEPER.md).

  ~/.venvs/fastbt/bin/python gatekeeper/open_locked.py IDEA-NNNN <route> [--mode M3]

DESIGN A11.4 guard, applied first: the candidate's stored G1 (the latest results/g1.jsonl row of that idea and route) must still
clear the luck bar at the k in the ledger TODAY (count_k over every real row so far), with the same sigma (the stored unseen years
and VR). Modes that no longer clear are dropped; if none is left the open is refused and recorded in gatekeeper/locked-checks.jsonl
as a luck-bar fail at open time ("refused: luck bar"); the locked period stays closed for it.

The open itself (running the candidate on 2025-01-01 ->) is not built yet: it comes with the first candidate, built by the engine
owner and reviewed by the sceptic. This file holds the guard so that it is in place before the first real G1.
"""
import argparse
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from engine import ideas as I, pipeline as P  # noqa: E402
from engine.hash import engine_hash  # noqa: E402

CHECKS = os.path.join(REPO, "gatekeeper", "locked-checks.jsonl")


def luck_recheck(stored, rows, modes=None, rho_fn=P.route_rho):
    """Re-applies the luck bar to a stored route G1 at today's k. Returns {k_now, modes: {mode: {sharpe, bar_then, bar_now, ok}},
    clears: [modes still clearing]}. The modes considered are the eligible ones when judged (pipeline.eligible_modes: M1-M3 passing
    or near miss; a near miss is never on the luck bar, a safety bar). Sceptic re-check 2026-11-15 (B): near misses were dropped."""
    kc = P.count_k(rows, stored["idea_id"], rho_fn=rho_fn)
    out = {"k_then": stored["k"]["k"], "k_now": kc["k"], "modes": {}, "clears": []}
    eligible = P.eligible_modes(stored["g1"])
    for m, g in stored["g1"].items():
        if (modes and m not in modes) or m not in eligible:
            continue
        if not g.get("luck"):
            raise ValueError(f"{stored['idea_id']}/{m}: the stored G1 has no luck bar")
        L = g["luck"]
        bar = P.luck_bar(kc["k"], stored.get("from_ms"), L["vr"])
        if abs(bar["sigma"] - L["sigma"]) > 1e-4:
            raise ValueError(f"{stored['idea_id']}/{m}: sigma {bar['sigma']} differs from the stored {L['sigma']}")
        ok = g["daily_sharpe"] is not None and g["daily_sharpe"] >= bar["bar"]
        out["modes"][m] = {"sharpe": g["daily_sharpe"], "bar_then": L["bar"], "bar_now": bar["bar"], "sigma": L["sigma"], "ok": ok}
        if ok:
            out["clears"].append(m)
    return out


def guard(idea_id, route, modes=None, rows=None, g1_rows=None, checks=CHECKS, rho_fn=P.route_rho):
    rows = P.read_ledger() if rows is None else rows
    g1_rows = I.read_g1() if g1_rows is None else g1_rows
    mine = [g for g in g1_rows if g["idea_id"] == idea_id and g["route"] == route]
    if not mine:
        raise SystemExit(f"{idea_id}/{route}: no stored G1 in results/g1.jsonl")
    stored = mine[-1]
    chk = luck_recheck(stored, rows, modes, rho_fn)
    rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "idea_id": idea_id, "route": route, "engine_hash": engine_hash(),
           "g1_ts": stored["ts"], **chk,
           "result": "refused: luck bar" if not chk["clears"] else "guard passed"}
    with open(checks, "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("idea")
    ap.add_argument("route", choices=P.ROUTES)
    ap.add_argument("--mode", action="append", choices=("M1", "M2", "M3"))
    a = ap.parse_args(argv)
    rec = guard(a.idea, a.route, a.mode)
    print(json.dumps(rec, indent=1))
    if rec["result"] != "guard passed":
        raise SystemExit(f"REFUSED: {a.idea}/{a.route} no longer clears the luck bar at k = {rec['k_now']}; the locked period stays closed")
    raise SystemExit("guard passed; the locked-period run itself is not built yet (engine owner, with the gatekeeper's go)")


if __name__ == "__main__":
    main()
