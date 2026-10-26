"""Frozen v2.1-running Phase 1: E1–E3 and supported naturalistic sessions only."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

import numpy as np

import build_v21_running_datasets as data
import capacity
import simulator_v21_running as sim
from validate_simulator_v21_running import OBSERVED_NAMES, history_features

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "artifacts" / "synthetic_v21_running_phase1_history"
FREEZE = ROOT / "SIMULATOR_V21_PHASE1_FREEZE.json"
SEEDS = (110, 220, 330, 440, 550)
KS = (0, 1, 3, 5, 10, 20)
ALPHAS = (1., 10., 100.)
TARGETS = ("WEAK", "BASE", "STRONG", "fatigue", "condition")
PARAMETERS = {"hr_baseline": "baseline_hr", "cs_like": "cs", "dprime_like": "dprime",
              "hr_response": "delta_hr", "fast_recovery": "tau_fast"}
HISTORY_NAMES = ("history_n", "history_hr_mean", "history_speed_mean",
                 "history_hr_slope", "history_hr_sd")
T4 = 2.7764451051977987


def save_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True,
                               allow_nan=False) + "\n", encoding="utf-8")


def ci(values: list[float]) -> dict:
    assert len(values) == 5
    mean, sd = statistics.mean(values), statistics.stdev(values)
    half = T4 * sd / math.sqrt(5)
    return {"mean": mean, "sd": sd, "ci95": [mean - half, mean + half]}


def score(y: np.ndarray, pred: np.ndarray) -> dict:
    residual = y - pred
    sst = float(np.sum((y - y.mean()) ** 2))
    return {"n": len(y), "mae": float(np.mean(np.abs(residual))),
            "rmse": float(np.sqrt(np.mean(residual ** 2))),
            "r2": float(1 - np.sum(residual ** 2) / sst) if sst else None}


def correlation(y: np.ndarray, pred: np.ndarray) -> float | None:
    if len(y) < 2 or np.std(y) < 1e-12 or np.std(pred) < 1e-12:
        return None
    return float(np.corrcoef(y, pred)[0, 1])


def fit_unbounded(rows: list[dict], names: tuple[str, ...], alpha: float) -> dict:
    x = np.array([[r["features"].get(n) if r["features"].get(n) is not None else np.nan
                   for n in names] for r in rows], dtype=float)
    y = np.array([r["target"] for r in rows], dtype=float)
    med = np.array([np.median(col[np.isfinite(col)]) if np.isfinite(col).any() else 0.
                    for col in x.T])
    x = np.where(np.isfinite(x), x, med)
    mean, sd = x.mean(0), x.std(0)
    sd[sd < 1e-8] = 1.
    z = np.column_stack([np.ones(len(x)), (x - mean) / sd])
    penalty = np.diag([0.] + [alpha] * len(names))
    beta = np.linalg.solve(z.T @ z + penalty, z.T @ y)
    return {"names": names, "median": med, "mean": mean, "sd": sd, "beta": beta}


def predict_unbounded(model: dict, rows: list[dict]) -> np.ndarray:
    x = np.array([[r["features"].get(n) if r["features"].get(n) is not None else np.nan
                   for n in model["names"]] for r in rows], dtype=float)
    x = np.where(np.isfinite(x), x, model["median"])
    z = np.column_stack([np.ones(len(x)), (x - model["mean"]) / model["sd"]])
    return z @ model["beta"]


def verify_freeze() -> dict:
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    assert tuple(freeze["seeds"]) == SEEDS and tuple(freeze["k"]) == KS
    assert tuple(freeze["alpha_grid"]) == ALPHAS
    assert tuple(freeze["observed_features"]) == OBSERVED_NAMES
    assert tuple(freeze["history_recovery_features"]) == HISTORY_NAMES
    assert tuple(freeze["targets"]) == TARGETS
    assert freeze["ci_t_df4"] == T4
    for name, expected in freeze["frozen_hashes"].items():
        if sim.file_hash(ROOT / name) != expected:
            raise ValueError(f"Frozen input changed: {name}")
    data.check_locks()
    return freeze


def feature_rows(dataset_rows: list[dict], k: int) -> tuple[list[dict], list[dict]]:
    """Reuse locked feature engineering; E rows never enter another E row's history."""
    by_subject: dict[str, list[dict]] = defaultdict(list)
    for row in dataset_rows:
        by_subject[row["subject"]].append(row)
    result, recovery = [], []
    for sid, rows in sorted(by_subject.items()):
        calibration = sorted((r for r in rows if r["event_type"] == "calibration"),
                             key=lambda r: r["index"])
        evaluation = sorted((r for r in rows if r["event_type"] == "evaluation"),
                            key=lambda r: r["index"])
        assert len(calibration) == 20 and len(evaluation) == 4
        for current in evaluation:
            row = history_features(calibration + [current], k)[-1]
            assert row["session"] == current["session"]
            assert row["history_sources"] == [r["session"] for r in calibration[-k:]] if k else not row["history_sources"]
            assert all(i < 20 for i in row["history_indices"])
            assert not any("-c2" in s or "-n2" in s for s in row["history_sources"])
            assert all(n not in row["observed"] for n in ("x", "cs", "dprime", "true_hr", "labels"))
            result.append({"subject": sid, "session": current["session"], "fold": current["fold"],
                           "cell": current["protocol_cell_id"] or "NATURALISTIC", "completed": current["completed"],
                           "features": row["observed"], "labels": current["labels"]})
        ref = next((r for r in result if r["subject"] == sid), None)
        assert ref is not None
        recovery.append({"subject": sid, "fold": ref["fold"],
                         "features": {name: ref["features"][name] for name in HISTORY_NAMES}})
    return result, recovery


def rows_for(rows: list[dict], target: str, fold: str, controlled: bool) -> list[dict]:
    selected = []
    for row in rows:
        if row["fold"] != fold or not row["completed"]:
            continue
        if controlled and row["cell"] not in ("E1", "E2", "E3"):
            continue
        if row["labels"][target] is None:
            continue
        selected.append({"subject": row["subject"], "session": row["session"],
                         "features": row["features"], "target": row["labels"][target]})
    return selected


def e4_audit(rows: list[dict], profiles: dict) -> dict:
    e4 = [r for r in rows if r["protocol_cell_id"] == "E4"]
    assert len(e4) == 120 and all(not r["completed"] and r["limit_minutes"] is not None for r in e4)
    t = np.array([r["limit_minutes"] for r in e4])
    cs = np.array([profiles[r["subject"]]["cs"] for r in e4])
    dprime = np.array([profiles[r["subject"]]["dprime"] for r in e4])
    rank = lambda a: np.argsort(np.argsort(a, kind="stable"), kind="stable")
    q = np.quantile(t, [.05, .5, .95])
    return {"n": 120, "complete": 0, "censored": 120,
            "time_to_limit_minutes": {"mean": float(t.mean()), "sd": float(t.std(ddof=1)),
                                      "q05": float(q[0]), "median": float(q[1]), "q95": float(q[2])},
            "correlation": {name: {"pearson": correlation(t, value),
                                   "spearman": correlation(rank(t), rank(value))}
                            for name, value in (("cs_like", cs), ("dprime_like", dprime),
                                                ("dprime_over_cs", dprime / cs))}}


def main() -> None:
    freeze = verify_freeze()
    if OUT.exists():
        raise FileExistsError(f"Refusing to overwrite Phase 1 artifacts: {OUT}")
    seed_metrics, predictions, parameter_metrics, parameter_predictions = [], [], [], []
    manifests, e4_results, validation = [], [], []
    for seed in SEEDS:
        generated = data.build(seed)
        sfold, tfolds = generated["subject_manifest"], generated["template_manifest"]
        assert generated["validation"]["status"] == {"naturalistic_builder": "PASS", "controlled_builder": "PASS"}
        assert all(v == 0 for group in ("template_intersections", "subject_intersections", "session_intersections")
                   for v in generated["validation"][group].values())
        manifests.append({"seed": seed, "subject_folds": sfold, "template_folds": tfolds,
                          "generation_hash": sim.canonical_hash((generated["naturalistic"],
                                                                 generated["controlled"], generated["profiles_audit_only"]))})
        e4_results.append({"seed": seed, **e4_audit(generated["controlled"], generated["profiles_audit_only"])})
        for dataset_name, dataset_rows in (("CONTROLLED_PERSONALIZATION", generated["controlled"]),
                                           ("NATURALISTIC", generated["naturalistic"])):
            by_k = {k: feature_rows(dataset_rows, k) for k in KS}
            for target in TARGETS:
                reference_keys, baseline_errors = None, None
                for k in KS:
                    features, _ = by_k[k]
                    train = rows_for(features, target, "train", dataset_name == "CONTROLLED_PERSONALIZATION")
                    val = rows_for(features, target, "validation", dataset_name == "CONTROLLED_PERSONALIZATION")
                    keys = [(r["subject"], r["session"]) for r in rows_for(
                        features, target, "id_test", dataset_name == "CONTROLLED_PERSONALIZATION")]
                    if reference_keys is None:
                        reference_keys = keys
                    else:
                        assert keys == reference_keys
                    assert train and val and keys
                    assert not ({r["subject"] for r in train + val} & {sid for sid, f in sfold.items() if f == "id_test"})
                    trials = []
                    for alpha in ALPHAS:
                        candidate = capacity.fit(train, list(OBSERVED_NAMES), alpha)
                        trial = score(np.array([r["target"] for r in val]), capacity.predict(candidate, val))
                        trials.append((trial["mae"], alpha))
                    alpha = min(trials)[1]
                    model = capacity.fit(train + val, list(OBSERVED_NAMES), alpha)
                    test = rows_for(features, target, "id_test", dataset_name == "CONTROLLED_PERSONALIZATION")
                    truth = np.array([r["target"] for r in test])
                    pred = capacity.predict(model, test)
                    result = score(truth, pred)
                    errors = np.abs(truth - pred)
                    if baseline_errors is None:
                        baseline_errors = errors
                    paired = baseline_errors - errors
                    assert abs(float(paired.mean()) - (float(baseline_errors.mean()) - result["mae"])) < 1e-10
                    seed_metrics.append({"seed": seed, "dataset": dataset_name, "target": target, "k": k,
                                         **result, "selected_alpha": alpha,
                                         "validation_alpha_mae": [{"alpha": a, "mae": m} for m, a in trials],
                                         "k0_minus_k_mae": float(paired.mean()),
                                         "seed_direction": "improved" if paired.mean() > 1e-12 else
                                         "worse" if paired.mean() < -1e-12 else "equal",
                                         "test_keys_hash": sim.canonical_hash(keys)})
                    for row, y, prediction, difference in zip(test, truth, pred, paired):
                        predictions.append({"seed": seed, "dataset": dataset_name, "target": target, "k": k,
                                            "subject": row["subject"], "session": row["session"],
                                            "truth": float(y), "prediction": float(prediction),
                                            "k0_abs_error_minus_k_abs_error": float(difference)})
            if dataset_name == "CONTROLLED_PERSONALIZATION":
                for k in KS:
                    _, recovery = by_k[k]
                    for name, profile_name in PARAMETERS.items():
                        r = [{"subject": item["subject"], "features": item["features"],
                              "target": generated["profiles_audit_only"][item["subject"]][profile_name]}
                             for item in recovery]
                        train = [item for item in r if sfold[item["subject"]] == "train"]
                        val = [item for item in r if sfold[item["subject"]] == "validation"]
                        test = [item for item in r if sfold[item["subject"]] == "id_test"]
                        assert [len(train), len(val), len(test)] == [72, 24, 24]
                        trials = []
                        for alpha in ALPHAS:
                            candidate = fit_unbounded(train, HISTORY_NAMES, alpha)
                            prediction = predict_unbounded(candidate, val)
                            trials.append((score(np.array([x["target"] for x in val]), prediction)["rmse"], alpha))
                        alpha = min(trials)[1]
                        model = fit_unbounded(train + val, HISTORY_NAMES, alpha)
                        truth = np.array([x["target"] for x in test])
                        pred = predict_unbounded(model, test)
                        metric = score(truth, pred)
                        parameter_metrics.append({"seed": seed, "k": k, "parameter": name, **metric,
                                                  "correlation": correlation(truth, pred), "selected_alpha": alpha})
                        for row, y, prediction in zip(test, truth, pred):
                            parameter_predictions.append({"seed": seed, "k": k, "parameter": name,
                                                          "subject": row["subject"], "truth": float(y),
                                                          "prediction": float(prediction)})
        validation.append({"seed": seed, "status": "PASS",
                           "controlled_E4_excluded_from_score": True,
                           "naturalistic_validation_test_above_threshold": [
                               generated["validation"]["naturalistic_folds"][fold]["above_threshold"]
                               for fold in ("validation", "id_test")]})
        print(f"Phase 1 seed {seed} complete", flush=True)
    summary = {}
    for dataset_name in ("CONTROLLED_PERSONALIZATION", "NATURALISTIC"):
        summary[dataset_name] = {}
        for target in TARGETS:
            summary[dataset_name][target] = {}
            for k in KS:
                items = [r for r in seed_metrics if r["dataset"] == dataset_name and r["target"] == target and r["k"] == k]
                assert len(items) == 5
                summary[dataset_name][target][str(k)] = {metric: ci([r[metric] for r in items])
                                                         for metric in ("mae", "rmse", "r2", "k0_minus_k_mae")}
                summary[dataset_name][target][str(k)]["seed_directions"] = {str(r["seed"]): r["seed_direction"] for r in items}
    recovery_summary = {}
    for name in PARAMETERS:
        recovery_summary[name] = {}
        for k in KS:
            items = [r for r in parameter_metrics if r["parameter"] == name and r["k"] == k]
            recovery_summary[name][str(k)] = {metric: ci([r[metric] for r in items]) for metric in ("mae", "rmse", "r2")}
            correlations = [r["correlation"] for r in items]
            recovery_summary[name][str(k)]["correlation"] = ci(correlations) if all(x is not None for x in correlations) else None
    OUT.mkdir(parents=True)
    save_json(OUT / "summary.json", {"seeds": SEEDS, "k": KS, "ci": "two-sided Student t across five seeds, df=4",
                                     "difference_sign": "positive k0_minus_k_mae means history improves",
                                     "targets": summary, "parameter_recovery": recovery_summary,
                                     "e4_tolerance": e4_results, "validation": validation})
    save_json(OUT / "seed_metrics.json", seed_metrics)
    save_json(OUT / "parameter_seed_metrics.json", parameter_metrics)
    save_json(OUT / "split_manifest.json", manifests)
    save_json(OUT / "freeze_used.json", freeze)
    for name, items in (("raw_predictions.csv", predictions),
                        ("parameter_predictions.csv", parameter_predictions)):
        with (OUT / name).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(items[0]))
            writer.writeheader()
            writer.writerows(items)
    save_json(OUT / "artifact_manifest.json", {"freeze_sha256": sim.file_hash(FREEZE),
                                                "runner_sha256": sim.file_hash(ROOT / "run_v21_phase1_history.py"),
                                                "file_sha256": {p.name: sim.file_hash(p) for p in OUT.iterdir() if p.is_file()}})


if __name__ == "__main__":
    main()
