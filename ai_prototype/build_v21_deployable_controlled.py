"""v2.1 deployable-anchored controlled dataset and parameter-only dry-run audit."""
from __future__ import annotations

import hashlib
import inspect
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

import build_v21_running_datasets as prior
import capacity
import simulator_v21_running as sim

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "artifacts" / "synthetic_v21_deployable_controlled_dryrun"
SEED = 20260921
PROTOCOL = "SIMULATOR_V21_DEPLOYABLE_CONTROLLED_PROTOCOL.md"
PROTOCOL_HASH = "b8052bacf424a845ccec128b1416deb108007b0b34db9d19cd020329becd1479"
GENERATOR_HASH = "d03b854edb53fa95955d440c58c71bf3e7a158c3104753841f073a20046cf586"
OLD_BUILDER_HASH = "353505e9741f0ccf713c24389132e066733b052778bdb1097e626158f41c9f9b"
PHASE1_SUMMARY_HASH = "14219415d70bfbcc4eee8406a523650a838aba39500ce10a97e5a6f5683d5753"
KS = (0, 1, 3, 5, 10, 20)
ALPHAS = (1., 10., 100.)  # fixed small validation-only audit grid
PARAMS = {"baseline_hr": "baseline_hr", "cs_like": "cs", "dprime_like": "dprime",
          "hr_response": "delta_hr", "fast_recovery": "tau_fast"}


def check_locks() -> None:
    prior.check_locks()
    checks = {PROTOCOL: PROTOCOL_HASH, "simulator_v21_running.py": GENERATOR_HASH,
              "build_v21_running_datasets.py": OLD_BUILDER_HASH,
              "artifacts/synthetic_v21_running_phase1_history/summary.json": PHASE1_SUMMARY_HASH}
    for name, expected in checks.items():
        if sim.file_hash(ROOT / name) != expected:
            raise ValueError(f"Frozen file changed: {name}")
    if (ROOT / "SIMULATOR_V21_DEPLOYABLE_CONTROLLED_PROTOCOL.sha256").read_text(encoding="ascii").split() != [PROTOCOL_HASH, PROTOCOL]:
        raise ValueError("Deployable protocol sidecar mismatch")


def assign_speed(u: float, v5_kmh: float) -> float:
    """Workload assignment boundary: no profile, generator state, or outcomes."""
    return float(u * v5_kmh)


def pair_id(cell: str) -> str | None:
    return cell[:2] if cell.startswith(("F", "S")) else None


def observed_log(state: dict, sid: str, fold: str, cell: str, index: int,
                 event_type: str, u: float, v5_kmh: float) -> dict:
    completed = bool(state["completed"])
    return {"dataset": "DEPLOYABLE_CONTROLLED_V1", "subject": sid, "fold": fold,
            "session": f"{sid}-d{index:02d}", "event_id": cell, "event_order": index,
            "event_type": event_type, "pair_id": pair_id(cell), "rest_flag": cell.startswith("R"),
            "u_anchor": u, "v5_kmh": v5_kmh, "commanded_speed_kmh": state["speed_kmh"],
            "actual_speed_kmh": state["speed_kmh"], "planned_minutes": state["planned_minutes"],
            "actual_minutes": state["actual_minutes"], "completed": completed,
            "censored": not completed, "observed_stop_minutes": None if completed else state["actual_minutes"],
            "time_to_limit_lower_bound_minutes": state["planned_minutes"] if completed else None,
            "gap_h": state["gap_h"], "observed_session_mean_hr": state["observed_hr"],
            "hr_quality": None, "source_template_id": None}


def build(seed: int = SEED) -> dict:
    check_locks()
    templates = prior.source_templates()
    tfold, _ = prior.template_folds(templates)
    sfold = prior.subject_folds()
    rng = np.random.default_rng(seed)
    profiles = prior.profiles_for_folds(templates, tfold, sfold, rng, sim.scenario())
    source_profiles = capacity.profiles()
    for sid, p in profiles.items():
        source = source_profiles.get(p["source_subject"])
        if not source or source["status"] != "dated_reference" or not source["reference_date"]:
            raise ValueError("STOP: independently dated 5 km anchor unavailable")
        source_workouts = [t for t in templates if t["source_subject"] == p["source_subject"]]
        if not source_workouts or any(t["date"] <= source["reference_date"] for t in source_workouts):
            raise ValueError("STOP: 5 km anchor not prior to source exercise")
        if not math.isfinite(p["v5_kmh"]) or p["v5_kmh"] <= 0:
            raise ValueError("STOP: invalid 5 km speed/unit")
    p = sim.scenario()
    observed, audit = [], []
    for sid in sorted(profiles):
        profile = profiles[sid]
        q, debt = profile["dprime"], 0.
        for index, (cell, u, minutes, gap, event_type) in enumerate(prior.controlled_schedule(sid)):
            command = assign_speed(u, profile["v5_kmh"])
            state = prior.observed_event(profile, q, debt, gap, command, minutes, rng, p,
                                         rest=cell.startswith("R"))
            row = observed_log(state, sid, sfold[sid], cell, index, event_type, u, profile["v5_kmh"])
            observed.append(row)
            audit.append({"subject": sid, "session": row["session"], "event_id": cell,
                          "fold": sfold[sid], "true_cs": profile["cs"], "true_dprime": profile["dprime"],
                          "true_tau_fast": profile["tau_fast"], "true_tau_slow": profile["tau_slow"],
                          "true_hr": state["true_hr"], "q_start": state["q_start"],
                          "q_end": state["q_end"], "strain": state["strain"],
                          "debt_pre": state["debt_pre"], "debt_after": state["debt_after"],
                          "hypothetical_limit_minutes": state["limit_minutes"],
                          "labels": state["labels"]})
            q, debt = state["q_end"], state["debt_after"]
    return {"seed": seed, "profiles_audit_only": profiles, "subject_split": sfold,
            "observed_events": observed, "audit_only": audit,
            "generation_hash": sim.canonical_hash((profiles, observed, audit))}


def linear_slope(x: list[float], y: list[float], minimum: int = 2) -> float | None:
    if len(x) < minimum or len(set(x)) < minimum or float(np.std(x)) < 1e-10:
        return None
    return float(np.polyfit(x, y, 1)[0])


def history_features(calibration: list[dict], k: int, v5_kmh: float) -> tuple[dict, dict]:
    window = calibration[-k:] if k else []
    rest = [r for r in window if r["rest_flag"]]
    runs = [r for r in window if not r["rest_flag"]]
    complete = [r for r in runs if r["completed"]]
    stopped = [r for r in runs if r["censored"]]
    f = {"v5_kmh": v5_kmh, "n_events": len(window), "n_rest": len(rest),
         "n_completed": len(complete), "n_stopped": len(stopped),
         "rest_hr_mean": float(np.mean([r["observed_session_mean_hr"] for r in rest])) if rest else None,
         "rest_hr_last": rest[-1]["observed_session_mean_hr"] if rest else None}
    xs = [r["actual_speed_kmh"] for r in runs]
    ys = [r["observed_session_mean_hr"] for r in runs]
    slope = linear_slope(xs, ys, 3)
    f.update({"hr_speed_slope": slope,
              "hr_speed_intercept": float(np.mean(ys) - slope * np.mean(xs)) if slope is not None else None,
              "hr_speed_resid_sd": float(np.std(np.asarray(ys) -
                    (float(np.mean(ys) - slope * np.mean(xs)) + slope * np.asarray(xs)), ddof=1))
                    if slope is not None else None,
              "observed_speed_min": min(xs) if xs else None,
              "observed_speed_max": max(xs) if xs else None})
    longest = max(complete, key=lambda r: (r["planned_minutes"], -r["event_order"])) if complete else None
    f.update({"max_completed_planned_minutes": longest["planned_minutes"] if longest else None,
              "max_completed_speed_kmh": longest["actual_speed_kmh"] if longest else None,
              "median_observed_stop_minutes": float(np.median([r["observed_stop_minutes"] for r in stopped])) if stopped else None,
              "mean_stopped_speed_kmh": float(np.mean([r["actual_speed_kmh"] for r in stopped])) if stopped else None})
    by_cell = {r["event_id"]: r for r in window}
    pair_failure = "missing_G5_or_G6"
    c = d = None
    if "G5" in by_cell and "G6" in by_cell:
        a, b = by_cell["G5"], by_cell["G6"]
        pair_failure = "not_two_observed_stops"
        if a["censored"] and b["censored"]:
            t1, t2 = a["observed_stop_minutes"] * 60, b["observed_stop_minutes"] * 60
            pair_failure = "stop_times_too_close"
            if abs(t1 - t2) >= 60:
                v1, v2 = a["actual_speed_kmh"] / 3.6, b["actual_speed_kmh"] / 3.6
                c = (v2 * t2 - v1 * t1) / (t2 - t1)
                d = (v1 - c) * t1
                pair_failure = "nonphysical_or_nonfinite"
                if not math.isfinite(c) or not math.isfinite(d) or c <= 0 or d <= 0:
                    c = d = None
                else:
                    pair_failure = "valid"
    f.update({"cs_pair_candidate_mps": c, "dprime_pair_candidate_m": d,
              "cs_pair_valid": int(c is not None)})
    pair_counts = {"fast": 0, "slow": 0}
    for family, gaps in (("F", (1, 4, 16)), ("S", (6, 24, 72))):
        gap_x, stop_y, hr_y = [], [], []
        for i, gap in enumerate(gaps, 1):
            lead, probe = by_cell.get(f"{family}{i}a"), by_cell.get(f"{family}{i}b")
            prefix = f"{family.lower()}{gap}"
            valid = lead is not None and probe is not None
            f[prefix + "_pair_valid"] = int(valid)
            f[prefix + "_lead_actual_minutes"] = lead["actual_minutes"] if valid else None
            f[prefix + "_lead_completed"] = int(lead["completed"]) if valid else None
            f[prefix + "_probe_completed"] = int(probe["completed"]) if valid else None
            f[prefix + "_probe_stop_minutes"] = probe["observed_stop_minutes"] if valid else None
            f[prefix + "_probe_hr_minus_lead_hr"] = (probe["observed_session_mean_hr"] -
                                                     lead["observed_session_mean_hr"]) if valid else None
            if valid:
                pair_counts["fast" if family == "F" else "slow"] += 1
                hr_y.append(f[prefix + "_probe_hr_minus_lead_hr"])
                if probe["censored"]:
                    gap_x.append(math.log(gap))
                    stop_y.append(probe["observed_stop_minutes"])
        if family == "F":
            f["fast_pair_count"] = pair_counts["fast"]
            f["fast_stop_vs_log_gap_slope"] = linear_slope(gap_x, stop_y, 2)
        else:
            f["slow_pair_count"] = pair_counts["slow"]
            observed_gaps = [math.log(gap) for i, gap in enumerate(gaps, 1)
                             if f[f"s{gap}_pair_valid"]]
            f["slow_hr_vs_log_gap_slope"] = linear_slope(observed_gaps, hr_y, 2)
    f.update({"last_gap_h": window[-1]["gap_h"] if window else None,
              "mean_gap_h": float(np.mean([r["gap_h"] for r in window])) if window else None,
              "observed_hr_count": len(window), "hr_quality_count": None})
    return f, {"cs_pair_reason": pair_failure,
               "history_sessions": [r["session"] for r in window]}


def histories(observed: list[dict]) -> tuple[list[dict], list[dict]]:
    by_subject = defaultdict(list)
    for row in observed:
        by_subject[row["subject"]].append(row)
    feature_rows, reasons = [], []
    for sid, rows in sorted(by_subject.items()):
        cal = sorted((r for r in rows if r["event_type"] == "calibration"),
                     key=lambda r: r["event_order"])
        evals = sorted((r for r in rows if r["event_type"] == "evaluation"),
                       key=lambda r: r["event_order"])
        assert len(cal) == 20 and len(evals) == 4
        for k in KS:
            f, meta = history_features(cal, k, cal[0]["v5_kmh"])
            assert all(int(s.rsplit("-", 1)[1][1:]) < 20 for s in meta["history_sessions"])
            for e in evals:
                feature_rows.append({"subject": sid, "fold": e["fold"], "k": k,
                                     "evaluation_session": e["session"], "cell": e["event_id"],
                                     "v5_kmh": f["v5_kmh"], "features": f,
                                     "history_sessions": meta["history_sessions"]})
            reasons.append({"subject": sid, "fold": cal[0]["fold"], "k": k,
                            "cs_pair_reason": meta["cs_pair_reason"]})
    return feature_rows, reasons


def metric(y: np.ndarray, pred: np.ndarray) -> dict:
    ss = float(np.sum((y - y.mean()) ** 2))
    return {"r2": float(1 - np.sum((y - pred) ** 2) / ss) if ss else None,
            "correlation": float(np.corrcoef(y, pred)[0, 1]) if np.std(pred) > 1e-10 and np.std(y) > 1e-10 else None,
            "mae": float(np.mean(np.abs(y - pred)))}


def fit_ridge(rows: list[dict], names: list[str], alpha: float) -> dict:
    x = np.array([[r["features"].get(n) if r["features"].get(n) is not None else np.nan
                   for n in names] for r in rows], dtype=float)
    y = np.array([r["target"] for r in rows])
    med = np.array([np.median(c[np.isfinite(c)]) if np.isfinite(c).any() else 0.
                    for c in x.T])
    x = np.where(np.isfinite(x), x, med)
    mean, sd = x.mean(0), x.std(0)
    sd[sd < 1e-8] = 1.
    z = np.column_stack([np.ones(len(x)), (x - mean) / sd])
    coef = np.linalg.solve(z.T @ z + np.diag([0.] + [alpha] * len(names)), z.T @ y)
    return {"names": names, "median": med, "mean": mean, "sd": sd, "coef": coef}


def predict_ridge(model: dict, rows: list[dict]) -> np.ndarray:
    x = np.array([[r["features"].get(n) if r["features"].get(n) is not None else np.nan
                   for n in model["names"]] for r in rows], dtype=float)
    x = np.where(np.isfinite(x), x, model["median"])
    return np.column_stack([np.ones(len(x)), (x - model["mean"]) / model["sd"]]) @ model["coef"]


def parameter_recovery(feature_rows: list[dict], profiles: dict) -> list[dict]:
    unique = {(r["subject"], r["k"]): r for r in feature_rows if r["cell"] == "E1"}
    names = list(next(iter(unique.values()))["features"])
    results = []
    for k in KS:
        for parameter, key in PARAMS.items():
            values = [{"subject": r["subject"], "fold": r["fold"], "features": r["features"],
                       "target": profiles[r["subject"]][key]}
                      for (sid, kk), r in unique.items() if kk == k]
            train = [r for r in values if r["fold"] == "train"]
            val = [r for r in values if r["fold"] == "validation"]
            test = [r for r in values if r["fold"] == "id_test"]
            assert [len(train), len(val), len(test)] == [72, 24, 24]
            trial = [(float(np.mean((np.array([r["target"] for r in val]) -
                      predict_ridge(fit_ridge(train, names, a), val)) ** 2)), a) for a in ALPHAS]
            alpha = min(trial)[1]
            model = fit_ridge(train + val, names, alpha)
            truth = np.array([r["target"] for r in test])
            result = metric(truth, predict_ridge(model, test))
            results.append({"k": k, "parameter": parameter, "selected_alpha": alpha,
                            "n_test_subjects": 24, **result})
    return results


def audit(result: dict, features: list[dict], reasons: list[dict]) -> dict:
    observed, profiles, sfold = result["observed_events"], result["profiles_audit_only"], result["subject_split"]
    assert len(observed) == 120 * 24
    assert [Counter(sfold.values())[x] for x in ("train", "validation", "id_test")] == [72, 24, 24]
    assert list(inspect.signature(assign_speed).parameters) == ["u", "v5_kmh"]
    assert set(assign_speed.__code__.co_names) == {"float"} and assign_speed.__closure__ is None
    assert all(abs(r["commanded_speed_kmh"] - r["u_anchor"] * r["v5_kmh"]) < 1e-10 for r in observed)
    assert all(r["commanded_speed_kmh"] == r["actual_speed_kmh"] and r["source_template_id"] is None for r in observed)
    forbidden = {"cs", "dprime", "q_start", "q_end", "tau_fast", "tau_slow", "strain", "debt_pre",
                 "debt_after", "true_hr", "hypothetical_limit_minutes", "labels", "target"}
    assert all(not forbidden.intersection(r) for r in observed)
    assert all(r["observed_stop_minutes"] is None and r["time_to_limit_lower_bound_minutes"] == r["planned_minutes"]
               if r["completed"] else r["observed_stop_minutes"] == r["actual_minutes"] and
               r["time_to_limit_lower_bound_minutes"] is None for r in observed)
    group = {fold: {r["session"] for r in observed if r["fold"] == fold}
             for fold in ("train", "validation", "id_test")}
    assert not (group["train"] & group["validation"] or group["train"] & group["id_test"]
                or group["validation"] & group["id_test"])
    assert all(all(not s.endswith(tuple(f"d{i:02d}" for i in range(20, 24))) for s in r["history_sessions"])
               for r in features)
    for sid in profiles:
        rows = [r for r in observed if r["subject"] == sid]
        assert len(rows) == 24
        assert [(r["event_id"], r["u_anchor"], r["planned_minutes"], r["gap_h"], r["event_type"])
                for r in rows] == prior.controlled_schedule(sid)
    by_cell = defaultdict(list)
    for r in observed:
        by_cell[r["event_id"]].append(r)
    support = {cell: {"n": len(rows), "completed": sum(r["completed"] for r in rows),
                      "stopped": sum(r["censored"] for r in rows)} for cell, rows in sorted(by_cell.items())}
    anchors = defaultdict(list)
    for p in profiles.values():
        anchors[p["v5_kmh"]].append(p["cs"] / (p["v5_kmh"] / 3.6))
    conditional = {str(v): {"n": len(values), "rho_sd": float(np.std(values, ddof=1)) if len(values) > 1 else None,
                            "rho_min": min(values), "rho_max": max(values)} for v, values in anchors.items()}
    assert any(len(v) > 1 and np.std(v) > 1e-8 for v in anchors.values())
    subject_rows = []
    for sid, p in profiles.items():
        rows = [r for r in observed if r["subject"] == sid and r["event_type"] == "calibration"]
        subject_rows.append((sid, p["v5_kmh"] / 3.6, np.mean([r["commanded_speed_kmh"] for r in rows]) / 3.6,
                             p["cs"]))
    trainval = [r for r in subject_rows if sfold[r[0]] != "id_test"]
    test = [r for r in subject_rows if sfold[r[0]] == "id_test"]
    y = np.array([r[3] for r in trainval])
    z1 = np.array([[1., r[1]] for r in trainval])
    z2 = np.array([[1., r[1], r[2], .86] for r in trainval])
    beta1 = np.linalg.lstsq(z1, y, rcond=None)[0]
    beta2 = np.linalg.lstsq(z2, y, rcond=None)[0]
    truth = np.array([r[3] for r in test])
    pred1 = np.array([[1., r[1]] for r in test]) @ beta1
    pred2 = np.array([[1., r[1], r[2], .86] for r in test]) @ beta2
    assignment = {"v5_only": metric(truth, pred1), "v5_plus_mean_command_and_u": metric(truth, pred2),
                  "max_absolute_prediction_difference_mps": float(np.max(np.abs(pred1 - pred2))),
                  "max_abs_mean_command_minus_0_86_v5_kmh": float(max(abs(r[2] * 3.6 - .86 * r[1] * 3.6)
                                                                       for r in subject_rows)),
                  "conditional_rho_by_v5": conditional}
    grouped = defaultdict(list)
    for r in features:
        if r["cell"] == "E1":
            grouped[r["k"]].append(r)
    count_exclude = {"v5_kmh", "n_events", "n_rest", "n_completed", "n_stopped",
                     "fast_pair_count", "slow_pair_count", "observed_hr_count", "cs_pair_valid"}
    validity = {}
    for k, rows in grouped.items():
        keys = list(rows[0]["features"])
        value_keys = [key for key in keys if key not in count_exclude and not key.endswith("_pair_valid")
                      and not key.endswith("_completed")]
        counts = [sum(r["features"][key] is not None for key in value_keys) for r in rows]
        validity[str(k)] = {"measurement_feature_count_mean": float(np.mean(counts)),
                            "measurement_feature_count_min": min(counts),
                            "measurement_feature_count_max": max(counts),
                            "per_feature_valid_fraction": {key: sum(r["features"][key] is not None for r in rows) / len(rows)
                                                           for key in value_keys},
                            "cs_pair_valid": sum(r["features"]["cs_pair_valid"] for r in rows) / len(rows),
                            "fast_slope_valid": sum(r["features"]["fast_stop_vs_log_gap_slope"] is not None for r in rows) / len(rows),
                            "slow_slope_valid": sum(r["features"]["slow_hr_vs_log_gap_slope"] is not None for r in rows) / len(rows)}
    reason_counts = {str(k): dict(Counter(r["cs_pair_reason"] for r in reasons if r["k"] == k)) for k in KS}
    leakage = "PASS" if assignment["max_absolute_prediction_difference_mps"] < 1e-8 and all(
        v["rho_sd"] is None or v["rho_sd"] > 1e-8 for v in conditional.values() if v["n"] > 1) else "WARNING"
    return {"builder": "PASS", "assignment_latent_access": 0, "assignment_formula": "u*v5_kmh",
            "design_induced_proxy_leakage": leakage, "assignment_only_cs": assignment,
            "event_support": support, "history_validity": validity,
            "cs_pair_failure_reasons": reason_counts,
            "subject_session_split": "PASS", "history_evaluation_target_leakage": "PASS",
            "completed_hypothetical_limit_blocked": "PASS"}


def main() -> None:
    if OUT.exists():
        raise FileExistsError(f"Refusing to overwrite dry-run results: {OUT}")
    first, second = build(SEED), build(SEED)
    assert first["generation_hash"] == second["generation_hash"]
    features, reasons = histories(first["observed_events"])
    report = audit(first, features, reasons)
    report["same_seed_config_reproducibility"] = "PASS"
    report["generation_hash"] = first["generation_hash"]
    report["parameter_recovery_audit_only"] = parameter_recovery(features, first["profiles_audit_only"])
    OUT.mkdir(parents=True)
    for name, value in (("validation.json", report), ("observed_events.json", first["observed_events"]),
                        ("audit_only.json", first["audit_only"]),
                        ("profiles_audit_only.json", first["profiles_audit_only"]),
                        ("subject_split.json", first["subject_split"]),
                        ("history_features.json", features), ("history_reasons.json", reasons)):
        (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True,
                                           allow_nan=False), encoding="utf-8")
    (OUT / "artifact_hashes.json").write_text(json.dumps({p.name: sim.file_hash(p) for p in OUT.iterdir()
                                                            if p.is_file()}, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"builder": report["builder"], "design_induced_proxy_leakage": report["design_induced_proxy_leakage"],
                      "assignment_only_cs": {k: v for k, v in report["assignment_only_cs"].items()
                                             if k != "conditional_rho_by_v5"},
                      "event_support": report["event_support"],
                      "history_validity": {k: {q: v for q, v in row.items() if q != "per_feature_valid_fraction"}
                                           for k, row in report["history_validity"].items()},
                      "parameter_recovery_audit_only": report["parameter_recovery_audit_only"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
