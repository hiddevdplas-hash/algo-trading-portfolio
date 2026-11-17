"""DESIGN A11.6: end-to-end test of the real-idea route through the real runner and the real data store, on a temporary ledger:
screen at the card defaults -> zone -> tune grid (route base) -> walk-forward G1 with k counted from the ledger (count_k) ->
recorded judgement -> the locked-open guard (A11.4) and the batch-test rates (A11.5). About 10 s (one oil symbol, h4)."""
import json
import os
import time

import pytest

from engine import ideas as I, pipeline as P, runner as R

sys_gatekeeper = os.path.join(R.REPO, "gatekeeper")
CARD = ("| data-mined | no |\n| seen family | no |\n| source overlap | no |\n| source overlap, why | test card |\n| grid size | 3 |\n")
AXES = [("stop_mult", [0.75, 1.0, 1.33])]
BASE = {"seed": 424242, "freq": 150.0, "stop_atr": 1.5, "target_r": 1.5, "hold_h": 0.0, "exit_mult": 1.0, "entry_variant": 0.0}


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    runs = os.path.join(R.REPO, "runs", "_e2e", f"{time.strftime('%Y%m%d%H%M%S')}-{os.getpid()}-{time.time_ns()}")   # never reused
    os.makedirs(runs, exist_ok=True)
    monkeypatch.setattr(R, "LEDGER", str(tmp_path / "ledger"))
    monkeypatch.setattr(R, "QUEUE", str(tmp_path / "queue"))
    monkeypatch.setattr(R, "RUNS", runs)
    cards = os.path.join(R.REPO, "runs", "_test_cards")
    os.makedirs(cards, exist_ok=True)
    open(os.path.join(cards, "e2e.md"), "w").write(CARD)
    return tmp_path


def _queue(jobs):
    os.makedirs(os.path.join(R.QUEUE, "pending"), exist_ok=True)
    for k, j in enumerate(jobs):
        j = R.validate(j, require_committed=False)
        j["job_id"] = f"JE2E{k:04d}{j['stage']}"
        json.dump(j, open(os.path.join(R.QUEUE, "pending", j["job_id"] + ".json"), "w"))


def _job(stage, params, route=None):
    j = {"idea_id": "IDEA-E2E", "card": "runs/_test_cards/e2e.md", "lane": "market logic", "stage": stage,
         "strategy": "strategies/null_random.py:intents", "symbols": ["XTIUSD"], "timeframe": "h4", "period": ["2014-11", "2024-12"],
         "class": "A", "params": params}
    if route:
        j["route"] = route
    return j


def test_screen_tune_g1_with_ledger_k(sandbox):
    # 1 screen at the defaults (M0 only, as the zone needs)
    _queue([dict(_job("screen", dict(BASE, stop_mult=1.0)), modes=["M0"])])
    assert R.run_batch(workers=4, log=lambda s: None) == 1
    rows = P.read_ledger(R.LEDGER)
    assert len(rows) == 1 and rows[0]["route"] == "base" and rows[0]["card_flags"]["source_overlap"] is False
    z = I.screen_result(rows[0])
    assert z["zone"] in ("green", "amber", "red") and "t_mid" in z
    with pytest.raises(ValueError):
        I.route_g1("IDEA-E2E", "base", AXES, rows=rows)                # no tune rows yet
    # 2 tune: the declared grid, all four news modes
    _queue([_job("tune", dict(BASE, stop_mult=v), route="base") for v in AXES[0][1]])
    assert R.run_batch(workers=4, log=lambda s: None) == 3
    rows = P.read_ledger(R.LEDGER)
    assert [r["stage"] for r in rows] == ["screen", "tune", "tune", "tune"]
    with pytest.raises(ValueError, match="grid size is 3"):            # the axes must give the pinned grid size (re-check D)
        I.route_g1("IDEA-E2E", "base", [("stop_mult", [0.75, 1.0, 1.33]), ("exit_mult", [1.0, 1.2])], rows=rows)
    # 3 G1 with k from the ledger: one real idea, one base route of 3 points -> k = k_eff(3, measured rho)
    res = I.route_g1("IDEA-E2E", "base", AXES, rows=rows)
    kc = res["k"]
    assert kc["method"].startswith("sum of k_eff") and kc["routes"] == 1 and kc["per_route"]["IDEA-E2E/base"]["measured"]
    rho = kc["per_route"]["IDEA-E2E/base"]["rho"]
    assert abs(kc["k"] - round(P.k_eff(3, rho), 3)) < 1e-6 and 1.0 <= kc["k"] <= 3.0
    assert res["default_index"] == 1 and len(res["choices"]) == len(P.wf_windows())
    for m in ("M0", "M1", "M2", "M3"):
        g = res["g1"][m]
        assert g["luck"]["k"] == round(kc["k"], 3) and g["luck"]["vr"] > 0
        assert g["luck"]["bar"] == P.luck_bar(kc["k"], None, g["luck"]["vr"])["bar"]
        assert "hold_time" not in g["failed"] or g["values"]["short_hold_share"] > 0.10
    # the stitched log is the chosen points' unseen trades: rebuild it by hand for M3
    gl = [P.load_logs(os.path.join(R.REPO, r["run_path"]), r["symbols"], ["M3"]) for r in rows[1:]]
    st = P.wf_stitch(gl, res["choices"], "M3")
    assert res["g1"]["M3"]["values"]["trades"] == P.n_of(st) and st["entry_t"].min() >= P.month_ms("2016-11")
    # 4 the judgement is recorded; the batch test reads it; the locked-open guard re-applies the bar at today's k
    out = sandbox / "g1.jsonl"
    I.record(res, str(out))
    g1_rows = I.read_g1(str(out))
    assert g1_rows[0]["k"]["k"] == kc["k"]
    rates = I.real_rates(rows, g1_rows)
    assert rates["ideas_screened"] == 1 and rates["green_at_screen"] == (1.0 if z["zone"] == "green" else 0.0)
    import importlib.util
    spec = importlib.util.spec_from_file_location("open_locked", os.path.join(sys_gatekeeper, "open_locked.py"))
    OL = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(OL)
    # a fabricated passing judgement (test only): sharpe just above the bar now, and below it once the ledger's k grows
    fake = json.loads(json.dumps(g1_rows[0]))
    fake["g1"]["M3"].update(**{"pass": True, "daily_sharpe": fake["g1"]["M3"]["luck"]["bar"] + 0.001})
    chk = OL.guard("IDEA-E2E", "base", rows=rows, g1_rows=[fake], checks=str(sandbox / "checks.jsonl"))
    assert chk["result"] == "guard passed" and "M3" in chk["clears"]
    grown = rows + [dict(rows[0], idea_id=f"IDEA-X{i}", test_id=f"TX{i}") for i in range(40)]   # 40 more screened ideas
    chk = OL.guard("IDEA-E2E", "base", rows=grown, g1_rows=[fake], checks=str(sandbox / "checks.jsonl"),
                   rho_fn=lambda g, n: None)
    assert chk["result"] == "refused: luck bar" and chk["k_now"] > chk["k_then"]
    assert chk["modes"]["M3"]["sigma"] == fake["g1"]["M3"]["luck"]["sigma"]          # same sigma, higher k
    logged = [json.loads(x) for x in open(sandbox / "checks.jsonl")]
    assert [x["result"] for x in logged] == ["guard passed", "refused: luck bar"]
    # a near-miss mode counts like a pass (sceptic re-check B); M0 is never a firm mode
    nm = json.loads(json.dumps(g1_rows[0]))
    for m in ("M0", "M1", "M2", "M3"):
        nm["g1"][m].update(**{"pass": m == "M0", "near_miss": m == "M2", "daily_sharpe": nm["g1"][m]["luck"]["bar"] + 0.001})
    chk = OL.luck_recheck(nm, rows)
    assert list(chk["modes"]) == ["M2"] and chk["clears"] == ["M2"]


def test_zero_intent_symbol_is_refused_and_empty_symbols_flagged(sandbox):
    """Guard 2026-11-15: a real job whose module gives no intent on a declared symbol is refused before any trade runs (no ledger
    row); a symbol emptied by the job's filter runs and is flagged on the row (zero_trade_symbols) and in the runner log."""
    j = dict(_job("screen", dict(BASE, stop_mult=1.0)), modes=["M0"], symbols=["XBRUSD", "XTIUSD"],
             strategy="tests/fixtures/zero_on_brent.py:intents")
    _queue([j])
    lines = []
    assert R.run_batch(workers=4, log=lines.append) == 0
    assert P.read_ledger(R.LEDGER) == []
    failed = os.listdir(os.path.join(R.QUEUE, "failed"))
    assert len(failed) == 1 and "ZERO INTENTS" in json.load(open(os.path.join(R.QUEUE, "failed", failed[0])))["error"]
    assert any("ZeroIntentError" in x and "XBRUSD" in x for x in lines)
    # the null lane is not guarded (its strategies always trade): the same job there runs, and the empty symbol is flagged on the
    # row (zero_trade_symbols) and in the runner log; a real job's filter that empties a symbol gets the same flag
    k = dict(j, lane="null", card="null/PLAN.json")
    _queue([k])
    lines = []
    assert R.run_batch(workers=4, log=lines.append) == 1
    row = P.read_ledger(R.LEDGER)[0]
    assert row["zero_trade_symbols"] == ["XBRUSD"] and row["metrics"]["M0"]["trades"] > 0
    assert any(x.startswith("WARNING") and "XBRUSD" in x for x in lines)
