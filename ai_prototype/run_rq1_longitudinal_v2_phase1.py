"""Frozen RQ1 longitudinal v2 Phase 1: five-seed BASE record-count experiment."""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
from pathlib import Path

import numpy as np

import simulator_rq1_longitudinal_v2 as sim
import audit_rq1_longitudinal_v2_recoverability as audit
from validate_rq1_longitudinal_v2 import _fit_transform, _mae, _r2, _ridge_predict

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "artifacts" / "rq1_longitudinal_v2_phase1_corrected"
SEEDS = (110, 220, 330, 440, 550)
KS = (0, 5, 10, 20, 30, 50, 75, 100)
TARGETS = ("burden_WEAK", "burden_BASE", "burden_STRONG", "fatigue", "condition")
MODES = ("current", "sensor_only", "sensor_context", "self_report", "full")


def sha(path: Path): return hashlib.sha256(path.read_bytes()).hexdigest()
def rmse(y, p): return float(np.sqrt(np.mean((y-p)**2)))


def feature_keys(row, mode, target):
    current = list(audit.CURRENT)
    sensor = [k for k in row if k.startswith("history_") and any(x in k for x in ("hr_bpm_", "temperature_c_", "spo2_pct_"))]
    context = [k for k in row if k.startswith("history_") and ("actual_duration" in k or k.endswith("_n") or k.endswith("_hr_mean"))]
    reports = [k for k in row if k.startswith(f"history_{target}_")]
    if mode == "current": return current
    if mode == "sensor_only": return current + sensor
    if mode == "sensor_context": return current + sensor + context
    if mode == "self_report": return current + reports
    if mode == "full": return current + sensor + context + reports
    raise ValueError(mode)


def complete_target_history(data, rows, k):
    """Apply the frozen mean/last self-report schema to every registered target."""
    source = {}
    for r in data["observed"]:
        source.setdefault(r["subject_id"], []).append(r)
    index = {}
    for subject_rows in source.values():
        subject_rows.sort(key=lambda r: r["timestamp"])
        for i, r in enumerate(subject_rows): index[r["session_id"]] = (subject_rows, i)
    for rec in rows:
        subject_rows, i = index[rec["session_id"]]
        past = subject_rows[max(0, i-k):i] if k else []
        for target in TARGETS:
            values = [p["targets"][target] for p in past if p["targets"].get(target) is not None]
            rec[f"history_{target}_mean"] = float(np.mean(values)) if values else None
            rec[f"history_{target}_last"] = float(values[-1]) if values else None
    return rows


def fit_predict(rows, target, mode):
    keys = feature_keys(rows[0], mode, target)
    X = audit._matrix(rows, keys)
    y = np.asarray([r["targets"][target] for r in rows], float)
    folds = np.asarray([r["fold"] for r in rows])
    best = None
    for alpha in (1.0, 10.0, 100.0):
        xt, xv = _fit_transform(X[folds == "train"], X[folds == "validation"])
        pred = _ridge_predict(xt, y[folds == "train"], xv, alpha)
        score = _mae(y[folds == "validation"], pred)
        if best is None or score < best[0]: best = (score, alpha)
    fit = folds != "test"
    xt, xe = _fit_transform(X[fit], X[folds == "test"])
    pred = _ridge_predict(xt, y[fit], xe, best[1])
    test_rows, truth = [r for r in rows if r["fold"] == "test"], y[folds == "test"]
    metrics = {"mae": _mae(truth, pred), "rmse": rmse(truth, pred), "r2": _r2(truth, pred),
               "alpha": best[1], "n_test": int(len(truth))}
    raw = [(r["session_id"], r["subject_id"], float(t), float(p)) for r, t, p in zip(test_rows, truth, pred)]
    return metrics, raw


def simple(rows, target, field):
    truth, pred = [], []
    for r in rows:
        if r["fold"] != "test": continue
        value = r.get(f"history_{target}_{field}")
        if value is not None:
            truth.append(r["targets"][target]); pred.append(value)
    if not truth: return None
    y, p = np.asarray(truth), np.asarray(pred)
    return {"mae": _mae(y, p), "rmse": rmse(y, p), "r2": _r2(y, p), "n_test": len(y)}


def mean_ci(values):
    a = np.asarray(values, float); mean = float(a.mean()); sd = float(a.std(ddof=1))
    half = 2.7764451051977987 * sd / math.sqrt(len(a))
    return {"mean": mean, "sd": sd, "ci95": [mean-half, mean+half]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    seed_results, predictions, split_manifest = {}, [], {}
    for seed in SEEDS:
        data = sim.generate(seed, "BASE")
        by_k = {k: complete_target_history(data, sim.history_features(data, k), k) for k in KS}
        eval_sets = {k: {r["session_id"] for r in rows} for k, rows in by_k.items()}
        if len({frozenset(x) for x in eval_sets.values()}) != 1: raise AssertionError("evaluation sessions differ by k")
        split_manifest[str(seed)] = {f: sorted({r["subject_id"] for r in data["observed"] if r["fold"] == f}) for f in ("train", "validation", "test")}
        seed_results[str(seed)] = {}
        for target in TARGETS:
            seed_results[str(seed)][target] = {}
            for k in KS:
                rows = [r for r in by_k[k] if r["targets"].get(target) is not None]
                entry = {"models": {}, "simple": {}}
                for mode in MODES:
                    metrics, raw = fit_predict(rows, target, mode)
                    entry["models"][mode] = metrics
                    for session, subject, truth, pred in raw:
                        predictions.append({"seed": seed, "target": target, "k": k, "mode": mode,
                                            "session_id": session, "subject_id": subject, "truth": truth, "prediction": pred})
                entry["simple"]["last"] = simple(rows, target, "last")
                entry["simple"]["mean"] = simple(rows, target, "mean")
                seed_results[str(seed)][target][str(k)] = entry

    summary = {}
    for target in TARGETS:
        summary[target] = {}
        baseline = [seed_results[str(s)][target]["0"]["models"]["current"]["mae"] for s in SEEDS]
        for k in KS:
            summary[target][str(k)] = {}
            for mode in MODES:
                vals = [seed_results[str(s)][target][str(k)]["models"][mode]["mae"] for s in SEEDS]
                diffs = [b-v for b, v in zip(baseline, vals)]
                direction = ["IMPROVED" if d > 0 else "WORSE" if d < 0 else "TIED" for d in diffs]
                summary[target][str(k)][mode] = {"mae": mean_ci(vals), "k0_current_minus_model": mean_ci(diffs),
                                                  "seed_direction": direction}
            for field in ("last", "mean"):
                vals = [seed_results[str(s)][target][str(k)]["simple"][field] for s in SEEDS]
                if all(v is not None for v in vals):
                    maes = [v["mae"] for v in vals]
                    summary[target][str(k)][f"simple_{field}"] = {"mae": mean_ci(maes)}

    patterns = {}
    for target in TARGETS:
        vals = [summary[target][str(k)]["full"]["mae"]["mean"] for k in KS]
        adjacent = [vals[i-1]-vals[i] for i in range(1, len(vals))]
        if sum(x >= .02 for x in adjacent[-3:]) >= 2: label = "CONTINUED_IMPROVEMENT"
        elif all(abs(x) < .02 for x in adjacent[-2:]): label = "PLATEAU"
        elif any(x <= -.02 for x in adjacent): label = "DETERIORATION"
        else: label = "INCONSISTENT"
        patterns[target] = {"full_history": label, "adjacent_mae_improvement": adjacent}

    result = {"version": "rq1-longitudinal-v2-phase1-base-02", "seeds": list(SEEDS), "history_lengths": list(KS),
              "targets": list(TARGETS), "modes": list(MODES), "seed_results": seed_results,
              "summary": summary, "patterns": patterns,
              "interpretation_rule": "Full/self-report gains and sensor-context gains must be reported separately.",
              "generator_sha256": sha(ROOT / "simulator_rq1_longitudinal_v2.py"),
              "parameter_sha256": sha(ROOT / "RQ1_LONGITUDINAL_V2_FINAL_PARAMETERS.json"),
              "validation_amendment_sha256": sha(ROOT / "RQ1_LONGITUDINAL_V2_VALIDATION_AMENDMENT_01.md")}
    (OUT / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "split_manifest.json").write_text(json.dumps(split_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    with gzip.open(OUT / "raw_predictions.jsonl.gz", "wt", encoding="utf-8") as f:
        for row in predictions: f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (OUT / "summary.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["target", "k", "mode", "mae_mean", "mae_sd", "ci_low", "ci_high", "k0_minus_mean", "k0_minus_ci_low", "k0_minus_ci_high", "improved_seeds"])
        for target in TARGETS:
            for k in KS:
                for mode in MODES:
                    x = summary[target][str(k)][mode]
                    w.writerow([target, k, mode, x["mae"]["mean"], x["mae"]["sd"], *x["mae"]["ci95"],
                                x["k0_current_minus_model"]["mean"], *x["k0_current_minus_model"]["ci95"], x["seed_direction"].count("IMPROVED")])
    print(json.dumps({"summary": summary, "patterns": patterns}, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
