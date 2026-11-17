"""DESIGN A10, A11: frozen thresholds, strict card fields, k counted from the ledger, the luck bar in G1, the hold-time bar."""
import os

import numpy as np
import pytest

from engine import pipeline as P, runner as R

DAY = 86_400_000
GOOD = ("| data-mined | no |\n| seen family (DESIGN §3.7) | no |\n| source overlap (DESIGN A11.3) | no |\n"
        "| source overlap, why | own reasoning, no tested sample |\n| grid size | 9 |\n")


def test_thresholds_frozen():
    assert P.TH["status"].startswith("frozen")
    assert P.TH["null"]["target_share"] == 0.005
    L = P.TH["luck_bar"]
    assert (L["mu0"], L["sigma0"], L["years0"], L["quantile"], L["rho_default"]) == (0.0, 0.354, 8.17, 0.95, 0.688)   # A11.4
    assert P.TH["screen"]["amber_mid_t"] == 1.5 and "amber_gross_t" not in P.TH["screen"]                          # A11.1
    assert (P.TH["walk_forward"]["hold_short_minutes"], P.TH["walk_forward"]["hold_short_max_share"]) == (2, 0.10)  # A11.2


def test_card_flags_strict():
    assert P.card_flags(GOOD) == {"data_mined": False, "seen_family": False, "source_overlap": False, "grid_size": 9}
    assert P.card_flags(GOOD.replace("| source overlap (DESIGN A11.3) | no |", "| source overlap | yes |"))["source_overlap"] is True
    for bad in ("partly", "yes (2018-2021)", "unknown", ""):
        with pytest.raises(ValueError):
            P.card_flags(GOOD.replace("| source overlap (DESIGN A11.3) | no |", f"| source overlap (DESIGN A11.3) | {bad} |"))
    with pytest.raises(ValueError):                                     # A11.3: the row is required
        P.card_flags(GOOD.replace("| source overlap (DESIGN A11.3) | no |\n", ""))
    assert P.card_flags(GOOD.replace("| data-mined | no |", "| data-mined | yes |"))["data_mined"] is True
    for bad in ("partly", "**yes**", "no (published effect)", "Yes", "", "none"):
        with pytest.raises(ValueError):
            P.card_flags(GOOD.replace("| data-mined | no |", f"| data-mined | {bad} |"))
    with pytest.raises(ValueError):
        P.card_flags(GOOD.replace("| seen family (DESIGN §3.7) | no |", "| seen family (DESIGN §3.7) | none |"))
    for bad in ("9 points", "0", "nine", "3x3"):
        with pytest.raises(ValueError):
            P.card_flags(GOOD.replace("| grid size | 9 |", f"| grid size | {bad} |"))
    with pytest.raises(ValueError):                                     # missing field
        P.card_flags("| data-mined | no |\n| grid size | 9 |\n")
    with pytest.raises(ValueError):                                     # given twice
        P.card_flags(GOOD + "| data-mined | no |\n")


def _job(card, lane="market logic", stage="screen", **kw):
    return dict({"idea_id": "IDEA-T", "card": card, "lane": lane, "stage": stage, "strategy": "strategies/null_random.py:intents",
                 "symbols": ["EURUSD"], "timeframe": "h1", "period": ["2014-11", "2024-12"], "class": "A"}, **kw)


def test_runner_refuses_non_strict_cards_and_routes():
    d = os.path.join(R.REPO, "runs", "_test_cards")
    os.makedirs(d, exist_ok=True)
    good, bad = os.path.join(d, "good.md"), os.path.join(d, "bad.md")
    open(good, "w").write(GOOD)
    open(bad, "w").write(GOOD.replace("| data-mined | no |", "| data-mined | partly |"))
    rel = lambda p: os.path.relpath(p, R.REPO)
    j = R.validate(_job(rel(good)), require_committed=False)
    assert j["card_flags"]["grid_size"] == 9 and j["route"] == "base"
    assert R.validate(_job(rel(good), stage="amber-V2"), require_committed=False)["route"] == "V2"
    with pytest.raises(ValueError):
        R.validate(_job(rel(bad)), require_committed=False)
    with pytest.raises(ValueError):                                     # a grid job must name its route
        R.validate(_job(rel(good), stage="tune"), require_committed=False)
    with pytest.raises(ValueError):                                     # a route that contradicts the stage
        R.validate(_job(rel(good), stage="amber-V1", route="V3"), require_committed=False)
    assert R.validate(_job(rel(good), stage="tune", route="V1"), require_committed=False)["route"] == "V1"
    # the null and referee lanes are not real ideas: no card fields needed or recorded
    assert "card_flags" not in R.validate(_job(rel(bad), lane="null"), require_committed=False)


def _row(idea, stage, lane="market logic", dm=False, sf=False, n=9, route=None, variant=None, tid=None, so=False):
    return {"idea_id": idea, "lane": lane, "stage": stage, "route": route, "variant": variant, "test_id": tid or f"T-{idea}-{stage}",
            "card_flags": None if lane in ("null", "referee") else {"data_mined": dm, "seen_family": sf, "source_overlap": so,
                                                                    "grid_size": n}}


def test_count_k_normal_and_data_mined():
    k9 = P.k_eff(9, 0.688)
    rows = [_row("A", "screen"), _row("A", "amber-V1"), _row("A", "amber-V2"),
            _row("B", "screen", n=27), _row("C", "screen", dm=True, n=12), _row("C", "amber-V1", dm=True, n=12),
            _row("D", "amber-V1")]                                       # D has no screen row: not counted
    no_rho = lambda g, n: None
    k = P.count_k(rows, "A", rho_fn=no_rho)
    assert k["routes"] == 6 and k["ideas"] == 3
    assert abs(k["k"] - (3 * k9 + P.k_eff(27, 0.688) + 2 * P.k_eff(12, 0.688))) < 0.01
    kc = P.count_k(rows, "C", rho_fn=no_rho)                            # data-mined: real test rows, own grid as the floor
    assert kc["k"] == max(7, round(P.k_eff(12, 0.688), 3))
    with pytest.raises(ValueError):
        P.count_k(rows, "D", rho_fn=no_rho)                             # judged idea without a screen row
    # a measured grid correlation replaces the default for that route only
    rows2 = rows + [_row("B", "tune", n=27, route="base")]
    kb = P.count_k(rows2, "A", rho_fn=lambda g, n: 0.2)
    assert kb["per_route"]["B/base"]["measured"] and kb["per_route"]["B/base"]["rho"] == 0.2
    assert not kb["per_route"]["A/base"]["measured"]


def test_null_and_referee_lanes_never_count_toward_k():
    rows = [_row("A", "screen"), _row("M", "screen", dm=True), _row("M", "tune", dm=True, route="base")]
    no_rho = lambda g, n: None
    base_a, base_m = P.count_k(rows, "A", rho_fn=no_rho)["k"], P.count_k(rows, "M", rho_fn=no_rho)["k"]
    noise = []
    for i in range(1200):
        noise += [_row(f"N{i:04d}", "null-screen", lane="null"), _row(f"N{i:04d}", "screen", lane="null"),
                  _row(f"N{i:04d}", "null-grid", lane="null")]
    noise += [_row(f"REF{i}", "referee", lane="referee") for i in range(5)] + [_row("R1", "screen", lane="referee")]
    noise += [_row("A", "locked")]                                       # a locked-period open never counts either
    mixed = noise[:1800] + rows + noise[1800:]
    assert P.count_k(mixed, "A", rho_fn=no_rho)["k"] == base_a
    assert P.count_k(mixed, "M", rho_fn=no_rho)["k"] == base_m == max(3, round(P.k_eff(9, 0.688), 3))
    with pytest.raises(ValueError):
        P.count_k(mixed, "N0001", rho_fn=no_rho)                        # a null strategy is never judged as a real idea


def test_k_eff_exact():
    assert P.k_eff(1, 0.5) == 1.0 and P.k_eff(9, 0.0) == 9.0 and P.k_eff(9, 1.0) == 1.0
    assert abs(P.k_eff(3, 0.688) - 2.257) < 0.02 and abs(P.k_eff(9, 0.688) - 4.813) < 0.04    # 5,000,000-draw simulation
    ks = [P.k_eff(n, 0.688) for n in (3, 9, 12, 27)]
    assert ks == sorted(ks) and P.k_eff(9, 0.3) > P.k_eff(9, 0.688)


def test_route_rho_from_grid():
    t0 = P.month_ms("2017-01")
    rng = np.random.default_rng(2)
    base = rng.normal(0, 1, 400)
    def mk(r):
        e = (t0 + np.arange(400) * 5 * DAY).astype(np.int64)
        return {"entry_t": e, "exit_t": e + 3_600_000, "r_mid": r}
    logs = {f"T{i}": mk(base if i < 2 else rng.normal(0, 1, 400)) for i in range(3)}
    rows = [{"test_id": f"T{i}", "variant": {"p": i}} for i in range(3)]
    load = lambda r: logs[r["test_id"]]
    assert P.route_rho(rows[:2], 3, load=load) is None                  # grid not complete yet
    rho = P.route_rho(rows, 3, load=load)
    assert 0.25 < rho < 0.42                                            # pairs: 1.0, ~0, ~0 -> about 1/3


def mklog(t, r):
    n = len(r)
    return {"entry_t": t, "exit_t": t + 3_600_000, "side": np.ones(n, int), "r_gross": r, "r_net_ftmo": r, "r_net_ic": r,
            "symbol": np.array(["EURUSD"] * n), "session": np.array(["london"] * n), "vol_third": np.array(["mid"] * n),
            "regime": np.array(["range"] * n), "bloc": np.array(["usd"] * n), "r_swap_ftmo": np.zeros(n), "news_flags": np.zeros(n, int)}


def test_g1_luck_bar_safety_and_regime():
    rng = np.random.default_rng(4)
    n = 1500
    t = np.linspace(P.month_ms("2016-11"), P.month_ms("2024-12", 1) - DAY, n).astype(np.int64)
    weak = mklog(t, rng.normal(0.08, 1.0, n))                            # passes trades / PF / years, Sharpe below a high-k bar
    g = P.g1(weak, k=1)
    s = g["daily_sharpe"]
    lo = P.g1(weak, k=1)
    assert lo["luck"]["k"] == 1 and lo["luck"]["bar"] == P.luck_bar(1, None, P.variance_ratio(weak))["bar"]
    hi_k = 10 ** 9
    g = P.g1(weak, k=hi_k)
    assert g["luck"]["bar"] > s and g["failed"] == ["luck"] and not g["near_miss"]
    assert P.verdict(g, {"failed": [], "tests": {}}) == "fail"           # a safety bar: never a near miss
    none = P.g1(weak, k=None)
    assert none["luck"] is None and "luck" not in none["failed"]
    # regime route: sigma0 * sqrt(8.17 / years)
    frm = P.month_ms("2022-03")
    lb = P.luck_bar(100, frm)
    yrs = (P.month_ms("2024-12", 1) - frm) / (365.25 * DAY)
    assert abs(lb["sigma"] - 0.354 * np.sqrt(8.17 / yrs)) < 1e-3 and lb["bar"] > P.luck_bar(100)["bar"]
    gr = P.g1(weak, from_ms=frm, k=100)
    assert gr["luck"]["bar"] == P.luck_bar(100, frm, P.variance_ratio(P.take(weak, weak["entry_t"] >= frm), frm))["bar"]
    with pytest.raises(TypeError):
        P.g1(weak)                                                        # k must be stated (None only for the null calibration)
    with pytest.raises(ValueError):
        P.luck_bar(0.5)


# ------------------------------------------------------------------ DESIGN A11
def test_a11_luck_bar_mu0_zero_and_serial_correlation():
    from statistics import NormalDist
    from engine import metrics as M
    z = NormalDist().inv_cdf(0.95 ** (1 / 100))
    assert P.luck_bar(100)["bar"] == round(0.354 * z, 4)                # mu0 = 0
    assert P.luck_bar(100, vr=0.6)["sigma"] == 0.354                    # max(1, sqrt(VR)): never below sigma0
    assert abs(P.luck_bar(100, vr=2.25)["sigma"] - 0.354 * 1.5) < 1e-4
    assert M.nw_lag(2130) == 7 and M.nw_lag(100) == 4
    rng = np.random.default_rng(11)
    iid = rng.normal(0, 1, 2130)
    assert abs(M.nw_variance_ratio(iid) - 1.0) < 0.15
    ar = np.zeros(2130)
    e = rng.normal(0, 1, 2130)
    for i in range(1, 2130):
        ar[i] = 0.5 * ar[i - 1] + e[i]
    assert M.nw_variance_ratio(ar) > 2.0                                # long-run ratio (1+0.5)/(1-0.5) = 3; Bartlett lag 7 is lower
    # G1 stores k, sigma, VR and the bar; a serially correlated route gets the higher bar
    n = 2130
    t = np.linspace(P.month_ms("2016-11"), P.month_ms("2024-12", 1) - DAY, n).astype(np.int64)
    g_iid = P.g1(mklog(t, 0.05 + iid), k=100)["luck"]
    g_ar = P.g1(mklog(t, 0.05 + ar / 2), k=100)["luck"]
    assert set(g_iid) >= {"k", "sigma", "vr", "bar"} and g_ar["vr"] > 2 and g_ar["bar"] > g_iid["bar"]


def test_a11_stress_rechecks_use_the_route_luck_bar():
    rng = np.random.default_rng(5)
    n = 1500
    t = np.linspace(P.month_ms("2016-11"), P.month_ms("2024-12", 1) - DAY, n).astype(np.int64)
    base = mklog(t, rng.normal(0.12, 1.0, n))
    g = P.g1(base, k=40)
    other = mklog(t, rng.normal(0.12, 1.0, n) + np.repeat(rng.normal(0, 0.8, n // 10), 10))   # a different VR on its own
    assert P.variance_ratio(other) != g["luck"]["vr"]
    re = P.stress_g1(g)(other)
    assert re["luck"] == g["luck"]                                      # same k, sigma, VR and bar as the route's G1
    assert P.g1(other, k=40)["luck"]["bar"] != g["luck"]["bar"]         # (recomputing would have moved the bar)
    # inside G2 the swap0 / fx2015 tests call exactly this function
    seen = []
    fn = P.stress_g1(g)

    def spy(lg):
        r = fn(lg)
        seen.append(r["luck"])
        return r
    base["symbol"] = np.array(["EURUSD", "GBPUSD"] * (n // 2))
    P.g2(base, "M0", "B", True, {"swap0": other, "fx2015": other}, [], spy, declared_symbols=["EURUSD", "GBPUSD"])
    assert len(seen) == 2 and all(x == g["luck"] for x in seen)
    with pytest.raises(ValueError):
        P.g1(other, k=41, luck=g["luck"])                               # a stored bar can't be reused at another k


def test_a11_hold_time_is_a_g1_safety_bar():
    rng = np.random.default_rng(6)
    n = 1500
    t = np.linspace(P.month_ms("2016-11"), P.month_ms("2024-12", 1) - DAY, n).astype(np.int64)
    lg = mklog(t, rng.normal(0.15, 0.5, n))
    assert P.g1(lg, k=None)["pass"]
    quick = dict(lg, exit_t=lg["entry_t"] + np.where(np.arange(n) % 9 == 0, 60_000, 3_600_000))    # 11.1% under 2 min
    g = P.g1(quick, k=None)
    assert g["failed"] == ["hold_time"] and not g["near_miss"] and g["values"]["short_hold_share"] > 0.10
    assert P.verdict(g, {"failed": [], "tests": {}}) == "fail"
    ok = dict(lg, exit_t=lg["entry_t"] + np.where(np.arange(n) % 11 == 0, 60_000, 3_600_000))     # 9.1%: allowed
    assert P.g1(ok, k=None)["pass"]
    edge = dict(lg, exit_t=lg["entry_t"] + np.where(np.arange(n) % 9 == 0, 119_999, 120_000))     # 2:00 exactly is not under
    assert P.g1(edge, k=None)["failed"] == ["hold_time"] and P.short_hold_share(edge) == P.short_hold_share(quick)
    assert "hold_time" in P.SAFETY
    # every news mode is judged the same way (G1 runs per mode on that mode's stitched log)
    assert all(P.g1(quick, k=None)["failed"] == ["hold_time"] for _ in ("M0", "M1", "M2", "M3"))


def test_a11_source_overlap_counts_like_data_mined_and_flags_pin_to_first_screen():
    no_rho = lambda g, n: None
    rows = [_row("A", "screen"), _row("A", "amber-V1"), _row("B", "screen", n=27), _row("S", "screen", so=True, n=12)]
    ks = P.count_k(rows, "S", rho_fn=no_rho)
    assert ks["k"] == max(4, round(P.k_eff(12, 0.688), 3)) and "source_overlap" in ks["method"]
    # a later screen row (card edited after a result) changes nothing: the first screen row decides
    later = rows + [_row("S", "screen", so=False, n=3, tid="T-S-again"), _row("A", "screen", dm=True, n=3, tid="T-A-again")]
    assert P.count_k(later, "S", rho_fn=no_rho)["method"].startswith("real test rows")
    ka = P.count_k(later, "A", rho_fn=no_rho)
    assert ka["method"].startswith("sum of k_eff") and ka["per_route"]["A/base"]["n"] == 9
    # a first screen row without the A11.3 field is refused
    bad = [dict(_row("X", "screen"), card_flags={"data_mined": False, "seen_family": False, "grid_size": 9})]
    with pytest.raises(ValueError):
        P.count_k(bad, "X", rho_fn=no_rho)
