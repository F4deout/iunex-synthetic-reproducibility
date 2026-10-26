"""Frozen E4 start-time tolerance prediction; no generator or history edits."""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np

import build_v21_deployable_controlled as data
import capacity
import model
import run_v21_phase1_history as shared
import simulator_v21_running as sim

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "artifacts" / "synthetic_v21_tolerance_prediction_phase1"
PROTOCOL = ROOT / "SIMULATOR_V21_TOLERANCE_PREDICTION_PROTOCOL.md"
PROTOCOL_HASH = "2b1d8e01176ef58d55979e04d6b137ccf35255540cb19ad78767690252beb588"
SOURCE = ROOT / "artifacts" / "synthetic_v21_deployable_phase1"
CAUSE = ROOT / "artifacts" / "synthetic_v21_deployable_history_cause_audit"
FROZEN = {
    SOURCE / "summary.json": "02798a13bbf6c6fe8d7c8158a6c3e72ea58abb3555db2883e03bdd4762615101",
    SOURCE / "artifact_manifest.json": "3cd3be330e776951de355818ef4c5f3877207d8206bd27a8f870689079f307ac",
    CAUSE / "summary.json": "d4e7b422d5cc6077e0b8e9a1959a62d255ab645e001cff09e5511a08b6ebf343",
    CAUSE / "artifact_manifest.json": "e3fd3a0e16e161e8ca5968c3d6e0bb739f76051e1e3d595d7ce2393fe65dacdb",
}
SEEDS = (110, 220, 330, 440, 550)
KS = data.KS
ALPHAS = (1., 10., 100.)


def verify_locks() -> dict:
    data.check_locks()
    if sim.file_hash(PROTOCOL) != PROTOCOL_HASH:
        raise ValueError("Tolerance protocol changed")
    if PROTOCOL.with_suffix(".sha256").read_text(encoding="ascii").split() != [PROTOCOL_HASH, PROTOCOL.name]:
        raise ValueError("Tolerance sidecar mismatch")
    for path, digest in FROZEN.items():
        if sim.file_hash(path) != digest:
            raise ValueError(f"Frozen result changed: {path}")
    phase = json.loads((SOURCE / "summary.json").read_text(encoding="utf-8"))
    assert tuple(phase["seeds"]) == SEEDS and tuple(phase["k"]) == KS
    splits = json.loads((SOURCE / "split_manifest.json").read_text(encoding="utf-8"))
    assert [x["seed"] for x in splits] == list(SEEDS)
    return {"protocol_sha256": PROTOCOL_HASH,
            "generator_sha256": sim.file_hash(ROOT / "simulator_v21_running.py"),
            "builder_sha256": sim.file_hash(ROOT / "build_v21_deployable_controlled.py"),
            "history_schema_source_sha256": sim.file_hash(ROOT / "build_v21_deployable_controlled.py"),
            "frozen_results": {str(path.relative_to(ROOT)): digest for path, digest in FROZEN.items()},
            "seeds": SEEDS, "k": KS, "alpha_grid": ALPHAS}, {x["seed"]: x for x in splits}, phase


def rows_for_seed(generated: dict) -> dict[int, list[dict]]:
    observed = generated["observed_events"]
    e4 = {r["session"]: r for r in observed if r["event_id"] == "E4"}
    assert len(e4) == 120
    histories, _ = data.histories(observed)
    by_session = {r["session"]: r for r in observed}
    result = {k: [] for k in KS}
    for h in histories:
        if h["cell"] != "E4":
            continue
        e = e4[h["evaluation_session"]]
        assert h["subject"] == e["subject"] and h["fold"] == e["fold"]
        assert h["features"]["v5_kmh"] == e["v5_kmh"]
        assert len(h["history_sessions"]) == h["k"]
        assert all(by_session[s]["subject"] == e["subject"] and
                   by_session[s]["event_type"] == "calibration" and
                   by_session[s]["event_order"] < 20 for s in h["history_sessions"])
        assert e["censored"] and not e["completed"] and e["observed_stop_minutes"] is not None
        assert e["observed_stop_minutes"] > 0 and e["observed_stop_minutes"] < e["planned_minutes"] == 12
        assert e["commanded_speed_kmh"] == data.assign_speed(1.10, e["v5_kmh"])
        # Predictor boundary: current E4 contributes only its known order.
        history = h["features"] if h["k"] else {"v5_kmh": h["features"]["v5_kmh"]}
        features = {**history, "evaluation_order": e["event_order"]}
        forbidden = {"observed_stop_minutes", "actual_minutes", "completed", "censored",
                     "observed_session_mean_hr", "true_cs", "true_dprime", "q_start", "q_end",
                     "tau_fast", "tau_slow", "strain", "debt_pre", "debt_after", "target"}
        assert not (set(features) & forbidden)
        result[h["k"]].append({"subject": e["subject"], "session": e["session"],
                                "fold": e["fold"], "features": features,
                                "time_minutes": e["observed_stop_minutes"]})
    first_keys = None
    for k in KS:
        result[k].sort(key=lambda r: (r["subject"], r["session"]))
        keys = [(r["subject"], r["session"]) for r in result[k]]
        assert len(keys) == len(set(keys)) == 120
        if first_keys is None:
            first_keys = keys
        else:
            assert keys == first_keys
            assert all(a["time_minutes"] == b["time_minutes"]
                       for a, b in zip(result[0], result[k]))
        assert all(r["features"]["v5_kmh"] > 0 for r in result[k])
    return result


def fit_log_ridge(rows: list[dict], names: list[str], alpha: float) -> dict:
    transformed = [{"features": r["features"], "target": math.log(r["time_minutes"])} for r in rows]
    return capacity.fit(transformed, names, alpha)


def predict_minutes(fitted: dict, rows: list[dict]) -> np.ndarray:
    x = model.matrix(rows, fitted["names"])
    z = model.transform(x, np.asarray(fitted["median"]), np.asarray(fitted["mean"]),
                        np.asarray(fitted["scale"]))
    prediction = np.exp(z @ np.asarray(fitted["coef"]))
    assert np.isfinite(prediction).all() and (prediction > 0).all()
    return prediction


def score(truth: np.ndarray, prediction: np.ndarray) -> dict:
    error = truth - prediction
    sst = float(np.sum((truth - truth.mean()) ** 2))
    return {"n": len(truth), "mae": float(np.mean(np.abs(error))),
            "rmse": float(np.sqrt(np.mean(error ** 2))),
            "r2": float(1 - np.sum(error ** 2) / sst) if sst else None}


def main() -> None:
    if OUT.exists():
        raise FileExistsError(f"Refusing to overwrite tolerance results: {OUT}")
    freeze, frozen_splits, phase = verify_locks()
    prepared, validation = {}, []
    # Complete every support/split/leakage check before fitting any predictor.
    for seed in SEEDS:
        generated = data.build(seed)
        assert generated["generation_hash"] == frozen_splits[seed]["generation_hash"]
        assert generated["subject_split"] == frozen_splits[seed]["folds"]
        assert Counter(generated["subject_split"].values()) == {"train": 72, "validation": 24, "id_test": 24}
        by_k = rows_for_seed(generated)
        keys = [(r["subject"], r["session"]) for r in by_k[0]]
        prepared[seed] = by_k
        validation.append({"seed": seed, "status": "PASS", "same_generation_hash": True,
                           "same_subject_split": True, "same_E4_keys_all_k": True,
                           "event_observed": 120, "right_censored": 0,
                           "evaluation_keys_hash": sim.canonical_hash(keys),
                           "predictor_latent_and_future_access": 0})
    metrics, raw = [], []
    for seed in SEEDS:
        by_k = prepared[seed]
        fold_rows = by_k[0]
        train_times = [r["time_minutes"] for r in fold_rows if r["fold"] == "train"]
        train_median = float(np.median(train_times))
        baseline_error = None
        k0_error = None
        test_keys = None
        for condition in ("train_median", *KS):
            k = 0 if condition == "train_median" else condition
            rows = by_k[k]
            train = [r for r in rows if r["fold"] == "train"]
            val = [r for r in rows if r["fold"] == "validation"]
            test = [r for r in rows if r["fold"] == "id_test"]
            assert [len(train), len(val), len(test)] == [72, 24, 24]
            keys = [(r["subject"], r["session"]) for r in test]
            if test_keys is None:
                test_keys = keys
            else:
                assert keys == test_keys
            truth = np.array([r["time_minutes"] for r in test], dtype=float)
            if condition == "train_median":
                prediction = np.full(len(test), train_median)
                alpha, trials = None, []
            else:
                names = list(rows[0]["features"])
                assert names == ["v5_kmh", "evaluation_order"] if k == 0 else True
                trials = [{"alpha": a, "validation_mae_minutes": score(
                    np.array([r["time_minutes"] for r in val]),
                    predict_minutes(fit_log_ridge(train, names, a), val))["mae"]}
                    for a in ALPHAS]
                alpha = min(trials, key=lambda x: (x["validation_mae_minutes"], x["alpha"]))["alpha"]
                fitted = fit_log_ridge(train + val, names, alpha)
                prediction = predict_minutes(fitted, test)
            errors = np.abs(truth - prediction)
            if baseline_error is None:
                baseline_error = errors
            if condition == 0:
                k0_error = errors
            paired = None if k0_error is None else k0_error - errors
            result = score(truth, prediction)
            metrics.append({"seed": seed, "condition": condition, **result,
                            "selected_alpha": alpha, "validation_trials": trials,
                            "train_median_minutes": train_median,
                            "median_minus_condition_mae": float((baseline_error - errors).mean()),
                            "k0_minus_k_mae": None if paired is None else float(paired.mean()),
                            "seed_direction": None if paired is None else
                            ("improved" if paired.mean() > 1e-12 else
                             "worse" if paired.mean() < -1e-12 else "equal"),
                            "prediction_range_minutes": [float(prediction.min()), float(prediction.max())],
                            "test_keys_hash": sim.canonical_hash(keys)})
            raw.extend({"seed": seed, "condition": condition, "subject": r["subject"],
                        "session": r["session"], "truth_minutes": float(y),
                        "prediction_minutes": float(p),
                        "k0_abs_error_minus_condition": None if paired is None else float(d)}
                       for r, y, p, d in zip(test, truth, prediction,
                                             [None] * len(test) if paired is None else paired))
        print(f"Tolerance seed {seed} complete", flush=True)
    summary = {}
    for condition in ("train_median", *KS):
        items = [r for r in metrics if r["condition"] == condition]
        label = str(condition)
        summary[label] = {name: shared.ci([r[name] for r in items])
                          for name in ("mae", "rmse", "r2", "median_minus_condition_mae")}
        if condition != "train_median":
            summary[label]["k0_minus_k_mae"] = shared.ci([r["k0_minus_k_mae"] for r in items])
            summary[label]["seed_directions"] = {str(r["seed"]): r["seed_direction"] for r in items}
    recovery = phase["parameter_recovery_audit_only"]
    side_by_side = {str(k): {"tolerance_mae": summary[str(k)]["mae"],
        "parameter_recovery_r2": {name: values[str(k)]["r2"] for name, values in recovery.items()}}
        for k in KS}
    OUT.mkdir(parents=True)
    shared.save_json(OUT / "summary.json", {"dataset": "DEPLOYABLE_CONTROLLED_V1/E4",
        "endpoint": "observed_stop_minutes; 600/600 events, 0 right censored",
        "prediction_origin": "before E4 starts", "seeds": SEEDS, "k": KS,
        "ci": "two-sided Student t across five seed-level results, df=4",
        "paired_sign": "positive k0-minus-k MAE means history improves",
        "baseline_and_k": summary, "parameter_recovery_side_by_side": side_by_side,
        "validation": validation})
    shared.save_json(OUT / "seed_metrics.json", metrics)
    shared.save_json(OUT / "validation.json", validation)
    shared.save_json(OUT / "freeze_used.json", freeze)
    with (OUT / "raw_predictions.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(raw[0]))
        writer.writeheader()
        writer.writerows(raw)
    shared.save_json(OUT / "artifact_manifest.json", {"runner_sha256": sim.file_hash(ROOT / "run_v21_tolerance_prediction.py"),
        "file_sha256": {p.name: sim.file_hash(p) for p in OUT.iterdir() if p.is_file()}})


if __name__ == "__main__":
    main()
