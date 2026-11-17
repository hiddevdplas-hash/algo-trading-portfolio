"""Look-ahead review registry (DESIGN §6.2, build list item 10): no review pass, no counted result.

A review is recorded per strategy module **and commit** in reviews/<module stem>@<commit 12>.json, after the `lookahead-reviewer`
agent has read that exact code and its card (the report goes next to it as .md). The runner stamps every ledger row with the review of
the code it ran: {"id", "verdict": PASS / FAIL / pending}. Only PASS rows count; a FAIL voids every row of that commit, and a fixed
module is a new commit that needs its own review.

  ~/.venvs/fastbt/bin/python -m engine.reviews record <strategies/x.py> <PASS|FAIL> <report.md> [--card ideas/cards/...]
  ~/.venvs/fastbt/bin/python -m engine.reviews pending        modules in the queue or ledger without a review of their commit
"""
import argparse
import glob
import json
import os
import shutil
import sys
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(REPO, "reviews")


def _key(path, commit):
    return f"{os.path.splitext(os.path.basename(path))[0]}@{commit[:12]}"


def lookup(path, commit, deps=None):
    """{'id', 'verdict'} for a module at a commit; 'pending' when no review exists or when a repo module it imports has changed since
    the review (deps: {file: commit})."""
    if not commit:
        return {"id": None, "verdict": "pending"}
    p = os.path.join(DIR, _key(path, commit) + ".json")
    if not os.path.isfile(p):
        return {"id": None, "verdict": "pending"}
    d = json.load(open(p))
    if (d.get("deps") or {}) != (deps or {}):
        return {"id": _key(path, commit), "verdict": "pending", "note": "an imported module changed since the review"}
    return {"id": _key(path, commit), "verdict": d["verdict"]}


def record(path, verdict, report, card=None):
    from engine.runner import committed
    if verdict not in ("PASS", "FAIL"):
        raise ValueError(verdict)
    from engine.runner import local_imports
    commit = committed(path)
    deps = {dep: committed(dep) for dep in local_imports(path)}
    if not commit or not all(deps.values()):
        raise ValueError(f"{path} is not committed or has uncommitted changes: review committed code only")
    os.makedirs(DIR, exist_ok=True)
    k = _key(path, commit)
    shutil.copyfile(report, os.path.join(DIR, k + ".md"))
    d = {"module": path, "commit": commit, "deps": deps, "card": card, "card_commit": committed(card) if card else None, "verdict": verdict,
         "reviewer": "lookahead-reviewer", "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "report": k + ".md"}
    json.dump(d, open(os.path.join(DIR, k + ".json"), "w"), indent=1)
    return d


def pending():
    from engine import runner as R
    seen = {}                                          # (module, commit, pinned deps) -> True; deps as the job pinned them
    def add(j):
        if j.get("strategy_commit"):
            seen[(j["strategy"].partition(":")[0], j["strategy_commit"], json.dumps(j.get("strategy_deps") or {}, sort_keys=True))] = True
    for f in glob.glob(os.path.join(R.QUEUE, "*", "*.json")):
        add(json.load(open(f)))
    for f in glob.glob(os.path.join(R.LEDGER, "*.jsonl")):
        for line in open(f):
            if line.strip():
                add(json.loads(line))
    return sorted({f"{p}@{c[:12]}" for p, c, d in seen if lookup(p, c, json.loads(d))["verdict"] == "pending"})


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("record", "pending"))
    ap.add_argument("args", nargs="*")
    ap.add_argument("--card")
    a = ap.parse_args(argv)
    if a.action == "record":
        print(json.dumps(record(a.args[0], a.args[1], a.args[2], a.card), indent=1))
    else:
        print("\n".join(pending()) or "none")


if __name__ == "__main__":
    sys.path.insert(0, REPO)
    main()
