"""Cheap gate for the 3-hourly gatekeeper screen task (2026-11-17): is there anything new to screen or merge?

  ~/.venvs/fastbt/bin/python gatekeeper/screen_gate.py            -> prints GO + reasons (exit 0) or NOTHING NEW (exit 3)
  ~/.venvs/fastbt/bin/python gatekeeper/screen_gate.py --record   -> stores the current fingerprint (end of a screen run)

Fingerprint = every candidate card (status inbox, a strategy module that exists, no real screen row in the ledger) with the last
commit of its card and module, the last commit of gatekeeper/REVIEW-FIXES.md, and the tips of the lane branches not yet merged into
main. Reads git and the ledger only; no market data. The fingerprint lives in runs/ (git-ignored).
"""
import glob
import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
STATE = os.path.join(REPO, "runs", "screen-gate.json")
LANE_BRANCHES = ("lane/market-logic", "lane/literature")


def git(*args):
    r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def fingerprint():
    from engine import pipeline as P
    git("fetch", "-q", "origin")
    screened = {r.get("idea_id") for r in P.read_ledger() if P.is_real(r) and r.get("stage") == "screen"}
    cards = {}
    for path in sorted(glob.glob(os.path.join(REPO, "ideas", "cards", "IDEA-*.md"))):
        text = open(path, encoding="utf-8").read()
        idea = "IDEA-" + os.path.basename(path).split("-")[1]
        if idea in screened or not re.search(r"^\|\s*status\s*\|\s*inbox\s*\|", text, re.M):
            continue
        m = re.search(r"strategies/idea_\w+\.py", text)
        if not m or not os.path.isfile(os.path.join(REPO, m.group(0))):
            continue
        rel = os.path.relpath(path, REPO)
        cards[idea] = [git("log", "-1", "--format=%h", "--", rel), git("log", "-1", "--format=%h", "--", m.group(0))]
    lanes = {}
    for b in LANE_BRANCHES:
        ahead = git("rev-list", "--count", f"main..origin/{b}")
        if ahead and ahead != "0":
            lanes[b] = git("rev-parse", "--short", f"origin/{b}")
    return {"cards": cards, "review_fixes": git("log", "-1", "--format=%h", "--", "gatekeeper/REVIEW-FIXES.md"), "lanes": lanes}


def main():
    fp = fingerprint()
    if "--record" in sys.argv:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        json.dump(fp, open(STATE, "w"), indent=1)
        print("recorded", len(fp["cards"]), "candidate cards,", len(fp["lanes"]), "unmerged lane branches")
        return 0
    old = json.load(open(STATE)) if os.path.isfile(STATE) else None
    if old == fp:
        print("NOTHING NEW")
        return 3
    reasons = []
    old = old or {"cards": {}, "review_fixes": None, "lanes": {}}
    new_cards = [i for i in fp["cards"] if fp["cards"][i] != old["cards"].get(i)]
    if new_cards:
        reasons.append("new or changed candidate cards: " + ", ".join(new_cards))
    if fp["review_fixes"] != old["review_fixes"]:
        reasons.append("REVIEW-FIXES changed")
    new_lanes = [b for b in fp["lanes"] if fp["lanes"][b] != old["lanes"].get(b)]
    if new_lanes:
        reasons.append("unmerged lane commits: " + ", ".join(new_lanes))
    if not reasons:
        print("NOTHING NEW")
        return 3
    print("GO: " + "; ".join(reasons))
    return 0


if __name__ == "__main__":
    sys.exit(main())
