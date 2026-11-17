"""Runner end to end in a temporary queue / ledger / runs folder: shared tick memory, workers, one ledger row per job, deterministic."""
import json
import os

import pytest

from engine import runner as R


@pytest.fixture
def tmp_dirs(tmp_path, monkeypatch):
    for k in ("QUEUE", "LEDGER", "RUNS"):
        monkeypatch.setattr(R, k, str(tmp_path / k.lower()))
    return tmp_path


def job(**kw):
    j = {"idea_id": "REF-R1", "card": "runlists/REFEREES.md", "lane": "referee", "stage": "referee",
         "strategy": "strategies/referee.py:intents", "params": {"ref": "R1"}, "symbols": ["EURUSD"], "timeframe": "m15",
         "period": ["2024-01", "2024-02"], "class": "C", "modes": ["M0", "M3"]}
    j.update(kw)
    return j


def test_validate_refuses():
    with pytest.raises(ValueError):
        R.validate(job(stage="locked"), require_committed=False)
    with pytest.raises(ValueError):
        R.validate(job(period=["2024-12", "2025-01"]), require_committed=False)
    with pytest.raises(ValueError):
        R.validate(job(lane="market", venue="ic"), require_committed=False)
    with pytest.raises(ValueError):
        R.validate(job(card="ideas/cards/NOT-THERE.md"))            # not committed


def test_runner_end_to_end_and_deterministic(tmp_dirs):
    paths = []
    for k in range(2):
        p = tmp_dirs / f"j{k}.json"
        p.write_text(json.dumps(job(job_id=f"J{k}", venue="ic", symbols=["EURUSD"])))
        paths.append(str(p))
    R.submit(paths, require_committed=False)
    assert R.run_batch(workers=2, log=lambda s: None) == 2
    rows = [json.loads(l) for f in os.listdir(R.LEDGER) if f.endswith(".jsonl") for l in open(os.path.join(R.LEDGER, f))]
    assert len(rows) == 2 and rows[0]["count_at_run"]["tests"] == 1 and rows[1]["count_at_run"]["tests"] == 2
    assert rows[0]["metrics"] == rows[1]["metrics"]                       # same job twice -> identical results
    m0 = rows[0]["metrics"]["M0"]
    assert m0["trades"] > 50 and "by_year" in m0 and rows[0]["engine_hash"] and rows[0]["data_hash"]
    run = os.path.normpath(os.path.join(R.REPO, rows[0]["run_path"]))
    assert sorted(os.listdir(run)) == ["EURUSD_M0.npz", "EURUSD_M3.npz"]
    st = R.status()
    assert st["done"] == 2 and st["pending"] == 0 and st["ledger_tests"] == 2
