"""Dry validation of draft job files: engine.runner.validate on each <dir>/IDEA-*.json. No submit, nothing written to queue/ or ledger/.
Usage: ~/.venvs/fastbt/bin/python gatekeeper/dry_validate.py <dir-with-job-files>
store.store_meta is replaced by an existence check of <store>/<SYMBOL>/meta.json (no data file is opened)."""
import glob, json, os, sys
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from engine import store
from engine import runner as R
def meta_exists(symbol, store_root=store.STORE_ROOT):
    if not os.path.isfile(os.path.join(store_root, symbol, "meta.json")):
        raise FileNotFoundError(f"{symbol} not in the research store")
    return {}
store.store_meta = meta_exists
q_before = sorted(glob.glob(os.path.join(R.QUEUE, "*", "*.json"))); l_before = {f: os.path.getsize(f) for f in glob.glob(os.path.join(R.LEDGER, "*.jsonl"))}
for p in sorted(glob.glob(sys.argv[1] + "/IDEA-*.json")):
    job = json.load(open(p))
    try:
        j = R.validate(job, require_committed=True)
        print(f"{job['idea_id']}: PASS route={j['route']} flags={j['card_flags']} card_commit={j['card_commit'][:8]} "
              f"strategy_commit={j['strategy_commit'][:8]} deps={list(j['strategy_deps'])} review={j['review']}")
    except Exception as e:
        print(f"{job['idea_id']}: FAIL {type(e).__name__}: {e}")
assert sorted(glob.glob(os.path.join(R.QUEUE, "*", "*.json"))) == q_before, "queue changed"
assert {f: os.path.getsize(f) for f in glob.glob(os.path.join(R.LEDGER, "*.jsonl"))} == l_before, "ledger changed"
print("queue and ledger unchanged")
