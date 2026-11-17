"""DESIGN A7: built-in edges net of costs. Run once, before the edge rerun (outside engine/, so the engine hash stays 504406fbaacd).

For every edge strategy in null/PLAN.json (kind edge05 / edge10), its own measured cost per trade comes from its pre-A7 screen run
(ledger row, stage null-screen, engine 504406fbaacd, FTMO): cost = -(spread + commission + swap + slippage) R per trade. The planted
edge becomes x + cost (x = 0.05 / 0.10), so the expected net result is x per trade after FTMO costs. Writes the new edge_r into
null/PLAN.json (edge_x and edge_cost_r kept beside it) and the table into null/edge-costs-A7.json.

  ~/.venvs/fastbt/bin/python null/a7_edges.py
"""
import glob
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAN = os.path.join(REPO, "null", "PLAN.json")
ENGINE = "504406fbaacd"
X = {"edge05": 0.05, "edge10": 0.10}

rows = {}
for f in sorted(glob.glob(os.path.join(REPO, "ledger", "*.jsonl"))):
    for line in open(f):
        if line.strip():
            r = json.loads(line)
            if r.get("lane") == "null" and r.get("stage") == "null-screen" and r.get("engine_hash") == ENGINE and r.get("synthetic_edge_r"):
                rows[r["idea_id"]] = r
plan = json.load(open(PLAN))
table = {}
for s in plan["strategies"]:
    if s["kind"] not in X:
        continue
    r = rows[s["id"]]
    m = r["metrics"]["M0"]
    cost = -(m["spread_r_per_trade"] + m["comm_r_per_trade"] + m["swap_r_per_trade"] + m["slip_r_per_trade"])
    x = X[s["kind"]]
    s["edge_x"], s["edge_cost_r"], s["edge_r"] = x, round(cost, 6), round(x + cost, 6)
    table[s["id"]] = {"kind": s["kind"], "x": x, "cost_r_per_trade": round(cost, 6), "edge_r": s["edge_r"], "trades": m["trades"],
                      "source_test_id": r["test_id"]}
plan["a7"] = ("DESIGN A7 (2026-11-13): edge strategies' edge_r = x + own FTMO cost per trade from the pre-A7 screen run "
              "(null/edge-costs-A7.json); random strategies unchanged.")
json.dump(plan, open(PLAN, "w"), indent=1)
json.dump({"about": __doc__.strip().splitlines()[0], "engine": ENGINE, "strategies": table},
          open(os.path.join(REPO, "null", "edge-costs-A7.json"), "w"), indent=1)
c = sorted(v["cost_r_per_trade"] for v in table.values())
print(f"{len(table)} edge strategies; cost per trade min {c[0]:.4f} median {c[len(c)//2]:.4f} max {c[-1]:.4f}")
