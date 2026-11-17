"""Engine hash (DESIGN §4.4): engine code + cost table + policy rates + thresholds + the news calendar (news/types-*, news/dates/*).

Every result carries it; a change that alters results gets a new hash and a LOG entry naming the results it invalidates.
The cost table's build time is left out, so rebuilding identical costs keeps the hash.

  ~/.venvs/fastbt/bin/python -m engine.hash
"""
import glob
import hashlib
import json
import os

ENGINE = os.path.dirname(os.path.abspath(__file__))
CONFIG = ("costs.json", "policy_rates.json", "rules.json", "thresholds.json", "regime_k.json", "news_far.json")


def engine_hash(short=True):
    h = hashlib.sha256()
    for name in sorted(os.listdir(ENGINE)):
        if name.endswith(".py"):
            h.update(name.encode() + b"\0" + open(os.path.join(ENGINE, name), "rb").read() + b"\0")
    for name in CONFIG:
        p = os.path.join(ENGINE, name)
        if not os.path.isfile(p):
            continue
        d = json.load(open(p))
        if isinstance(d, dict):
            d.pop("built_utc", None)
        h.update(name.encode() + b"\0" + json.dumps(d, sort_keys=True).encode() + b"\0")
    from engine.news import NEWS as news, tracked                   # the committed news calendar decides windows and slippage
    for p in tracked("types-*.csv") + tracked(os.path.join("dates", "*.csv")):
        h.update(os.path.relpath(p, news).encode() + b"\0" + open(p, "rb").read() + b"\0")
    return h.hexdigest()[:12] if short else h.hexdigest()


if __name__ == "__main__":
    print(engine_hash())
