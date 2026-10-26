"""Frozen BASE Phase 1 for objective physiological/performance history value."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "vendor"))
from scipy.optimize import minimize
from scipy.special import log_ndtr

import simulator_rq1_physiological_history_value as sim

OUT = ROOT / "artifacts" / "rq1_physiological_history_value_phase1"
SEEDS = (110, 220, 330, 440, 550)
DATASETS = ("NATURALISTIC", "CONTROLLED_CHANGE")
KS = (0, 5, 10, 20, 30, 50, 75, 100)
CONDITIONS = sim.CONDITIONS
RIDGE_ALPHAS = (1.0, 10.0, 100.0)
LOGISTIC_CS = (0.1, 1.0, 10.0)
AFT_ALPHAS = (0.1, 1.0, 10.0)
CONTINUOUS_TARGETS = (
    "pre_fatigue_latent",
    "pre_condition_construct",
    "post_burden_latent",
    "pre_fatigue",
    "pre_condition",
    "post_burden",
    "recovery_delay_h",
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_analysis_lock() -> None:
    for number in (1, 2):
        lock_path = ROOT / f"RQ1_PHYSIOLOGICAL_HISTORY_VALUE_AMENDMENT_{number:02d}.lock.json"
        lock = json.loads(lock_path.read_text(encoding="utf-8-sig"))
        if sha(ROOT / lock["amendment"]) != lock["sha256"]:
            raise RuntimeError(f"changed amendment: {lock['amendment']}")
    sim.verify_preregistration()


def mae(y, p):
    return float(np.mean(np.abs(y - p)))


def rmse(y, p):
    return float(np.sqrt(np.mean((y - p) ** 2)))


def r2(y, p):
    denom = float(np.sum((y - y.mean()) ** 2))
    return float(1 - np.sum((y - p) ** 2) / denom) if denom else float("nan")


def ci(values):
    a = np.asarray(values, float)
    mean = float(a.mean())
    sd = float(a.std(ddof=1)) if len(a) > 1 else 0.0
    half = 2.7764451051977987 * sd / math.sqrt(len(a)) if len(a) > 1 else 0.0
    return {"mean": mean, "sd": sd, "ci95": [mean - half, mean + half]}


def feature_keys(rows):
    excluded = {"session_id", "subject_id", "fold", "session_index", "task_type", "targets", "audit_targets"}
    keys = [k for k, v in rows[0].items() if k not in excluded and (isinstance(v, (int, float)) or v is None)]
    return keys + [f"task_{task}" for task in sim.TASKS]


def matrix(rows, keys):
    return np.asarray([
        [float(row["task_type"] == key[5:]) if key.startswith("task_") else np.nan if row.get(key) is None else float(row[key]) for key in keys]
        for row in rows
    ], float)


def fit_transform(x):
    med = np.nanmedian(x, axis=0)
    med = np.where(np.isfinite(med), med, 0)
    filled = np.where(np.isnan(x), med, x)
    mean, sd = filled.mean(axis=0), filled.std(axis=0)
    sd = np.where(sd < 1e-9, 1, sd)
    return (filled - mean) / sd, (med, mean, sd)


def transform(x, state):
    med, mean, sd = state
    return (np.where(np.isnan(x), med, x) - mean) / sd


def ridge_predict(x, y, xp, alpha):
    xa, xpa = np.c_[np.ones(len(x)), x], np.c_[np.ones(len(xp)), xp]
    reg = np.eye(xa.shape[1]) * alpha
    reg[0, 0] = 0
    return xpa @ np.linalg.solve(xa.T @ xa + reg, xa.T @ y)


def target_value(row, target):
    if target in row["audit_targets"]:
        return row["audit_targets"][target]
    return row["targets"][target]


def fit_continuous(rows):
    keys = feature_keys(rows)
    x = matrix(rows, keys)
    y = np.asarray([[target_value(row, target) for target in CONTINUOUS_TARGETS] for row in rows], float)
    folds = np.asarray([row["fold"] for row in rows])
    train, validation, test = folds == "train", folds == "validation", folds == "test"
    xt, state = fit_transform(x[train])
    xv = transform(x[validation], state)
    validation_predictions = {alpha: ridge_predict(xt, y[train], xv, alpha) for alpha in RIDGE_ALPHAS}
    selected = {}
    for index, target in enumerate(CONTINUOUS_TARGETS):
        selected[target] = min(RIDGE_ALPHAS, key=lambda alpha: mae(y[validation, index], validation_predictions[alpha][:, index]))
    fit = train | validation
    xf, state = fit_transform(x[fit])
    xe = transform(x[test], state)
    predictions = np.empty((sum(test), len(CONTINUOUS_TARGETS)))
    for alpha in set(selected.values()):
        target_indices = [i for i, target in enumerate(CONTINUOUS_TARGETS) if selected[target] == alpha]
        predictions[:, target_indices] = ridge_predict(xf, y[fit][:, target_indices], xe, alpha)
    truth = y[test]
    metrics = {
        target: {"mae": mae(truth[:, i], predictions[:, i]), "rmse": rmse(truth[:, i], predictions[:, i]), "r2": r2(truth[:, i], predictions[:, i]), "alpha": selected[target], "n": int(sum(test))}
        for i, target in enumerate(CONTINUOUS_TARGETS)
    }
    test_rows = [row for row in rows if row["fold"] == "test"]
    raw = {row["session_id"]: {target: float(predictions[i, j]) for j, target in enumerate(CONTINUOUS_TARGETS)} for i, row in enumerate(test_rows)}
    return metrics, raw, keys


def logistic_predict(x, y, xp, c):
    alpha = 1.0 / c
    xa, xpa = np.c_[np.ones(len(x)), x], np.c_[np.ones(len(xp)), xp]
    beta = np.zeros(xa.shape[1])
    for _ in range(80):
        prob = 1 / (1 + np.exp(-np.clip(xa @ beta, -30, 30)))
        weight = np.clip(prob * (1 - prob), 1e-5, None)
        grad = xa.T @ (prob - y)
        grad[1:] += alpha * beta[1:]
        hessian = xa.T @ (xa * weight[:, None])
        hessian[1:, 1:] += alpha * np.eye(len(beta) - 1)
        step = np.linalg.solve(hessian + 1e-7 * np.eye(len(beta)), grad)
        beta -= step
        if np.max(np.abs(step)) < 1e-7:
            break
    return 1 / (1 + np.exp(-np.clip(xpa @ beta, -30, 30)))


def ece10(y, p):
    total = 0.0
    for lo in np.linspace(0, 0.9, 10):
        mask = (p >= lo) & (p < lo + 0.1 if lo < 0.9 else p <= 1)
        if mask.any():
            total += mask.mean() * abs(float(y[mask].mean()) - float(p[mask].mean()))
    return float(total)


def fit_completion(rows):
    keys = feature_keys(rows)
    x = matrix(rows, keys)
    y = np.asarray([row["targets"]["completed"] for row in rows], float)
    folds = np.asarray([row["fold"] for row in rows])
    train, validation, test = folds == "train", folds == "validation", folds == "test"
    xt, state = fit_transform(x[train])
    xv = transform(x[validation], state)
    selected = min(LOGISTIC_CS, key=lambda c: float(np.mean((logistic_predict(xt, y[train], xv, c) - y[validation]) ** 2)))
    fit = train | validation
    xf, state = fit_transform(x[fit])
    xe = transform(x[test], state)
    pred = logistic_predict(xf, y[fit], xe, selected)
    truth = y[test]
    test_rows = [row for row in rows if row["fold"] == "test"]
    return {"brier": float(np.mean((pred - truth) ** 2)), "ece10": ece10(truth, pred), "C": selected, "n": int(sum(test)), "positive_rate": float(truth.mean())}, {row["session_id"]: float(pred[i]) for i, row in enumerate(test_rows)}


def fit_stopped_time(rows):
    stopped = [row for row in rows if row["targets"]["stop_time_min"] is not None]
    keys = feature_keys(rows)
    x = matrix(stopped, keys)
    y = np.asarray([row["targets"]["stop_time_min"] for row in stopped], float)
    folds = np.asarray([row["fold"] for row in stopped])
    train, validation, test = folds == "train", folds == "validation", folds == "test"
    xt, state = fit_transform(x[train])
    xv = transform(x[validation], state)
    selected = min(RIDGE_ALPHAS, key=lambda alpha: mae(y[validation], ridge_predict(xt, y[train], xv, alpha)))
    fit = train | validation
    xf, state = fit_transform(x[fit])
    xe = transform(x[test], state)
    pred = ridge_predict(xf, y[fit], xe, selected)
    truth = y[test]
    test_rows = [row for row in stopped if row["fold"] == "test"]
    return {"mae": mae(truth, pred), "rmse": rmse(truth, pred), "r2": r2(truth, pred), "alpha": selected, "n": int(sum(test))}, {row["session_id"]: float(pred[i]) for i, row in enumerate(test_rows)}


def _aft_objective(theta, x, log_time, event, alpha):
    beta, log_sigma = theta[:-1], theta[-1]
    sigma = math.exp(float(log_sigma))
    mu = x @ beta
    uncensored = event == 1
    z = (log_time - mu) / sigma
    nll = np.empty(len(log_time))
    nll[uncensored] = log_sigma + 0.5 * z[uncensored] ** 2 + 0.5 * math.log(2 * math.pi)
    a = (mu[~uncensored] - log_time[~uncensored]) / sigma
    nll[~uncensored] = -log_ndtr(a)
    loss = float(nll.sum() + 0.5 * alpha * np.sum(beta[1:] ** 2))
    grad_mu = np.empty(len(log_time))
    grad_log_sigma = np.empty(len(log_time))
    grad_mu[uncensored] = (mu[uncensored] - log_time[uncensored]) / sigma ** 2
    grad_log_sigma[uncensored] = 1 - z[uncensored] ** 2
    log_phi = -0.5 * a ** 2 - 0.5 * math.log(2 * math.pi)
    ratio = np.exp(np.clip(log_phi - log_ndtr(a), -50, 50))
    grad_mu[~uncensored] = -ratio / sigma
    grad_log_sigma[~uncensored] = ratio * a
    grad_beta = x.T @ grad_mu
    grad_beta[1:] += alpha * beta[1:]
    gradient = np.r_[grad_beta, grad_log_sigma.sum()]
    return loss, gradient


def _aft_fit(x, time, event, alpha, initial=None):
    xa = np.c_[np.ones(len(x)), x]
    log_time = np.log(np.clip(time, 1 / 60, None))
    if initial is None:
        # Start from the corresponding ridge solution instead of the all-zero
        # slope vector.  This changes neither the AFT likelihood nor any
        # preregistered parameter; it only avoids an ill-conditioned optimizer
        # path when the history design matrix contains many correlated terms.
        penalty = np.eye(xa.shape[1]) * alpha
        penalty[0, 0] = 0.0
        try:
            beta = np.linalg.solve(xa.T @ xa + penalty, xa.T @ log_time)
        except np.linalg.LinAlgError:
            beta = np.linalg.pinv(xa.T @ xa + penalty) @ xa.T @ log_time
        residual = log_time - xa @ beta
        event_residual = residual[event == 1]
        sigma_start = float(np.std(event_residual if len(event_residual) > 1 else residual))
        theta = np.r_[beta, math.log(max(sigma_start, 0.2))]
    else:
        theta = initial
    # Scaling both the objective and gradient by n preserves the exact optimum
    # while keeping stopping tolerances comparable across train/refit sizes.
    def scaled_objective(t):
        loss, gradient = _aft_objective(t, xa, log_time, event, alpha)
        return loss / len(xa), gradient / len(xa)

    result = minimize(scaled_objective, theta, jac=True, method="L-BFGS-B", bounds=[(None, None)] * xa.shape[1] + [(math.log(0.03), math.log(5.0))], options={"maxiter": 2000, "ftol": 1e-10, "gtol": 1e-6})
    converged = bool(result.success or np.max(np.abs(result.jac)) < 1e-4)
    return result.x, converged, str(result.message), int(result.nit), float(np.max(np.abs(result.jac)))


def _aft_nll(theta, x, time, event, alpha=0.0):
    xa = np.c_[np.ones(len(x)), x]
    return _aft_objective(theta, xa, np.log(np.clip(time, 1 / 60, None)), event, alpha)[0] / len(time)


def _c_index(time, event, predicted_time):
    concordant = comparable = 0.0
    for i in np.flatnonzero(event == 1):
        mask = time > time[i]
        if mask.any():
            comparable += int(mask.sum())
            concordant += float(np.sum(predicted_time[i] < predicted_time[mask])) + 0.5 * float(np.sum(predicted_time[i] == predicted_time[mask]))
    return float(concordant / comparable) if comparable else float("nan")


def fit_aft(rows):
    keys = feature_keys(rows)
    x = matrix(rows, keys)
    time = np.asarray([row["targets"]["stop_time_min"] if row["targets"]["stop_time_min"] is not None else row["planned_duration_min"] for row in rows], float)
    event = np.asarray([row["targets"]["stop_time_min"] is not None for row in rows], int)
    folds = np.asarray([row["fold"] for row in rows])
    train, validation, test = folds == "train", folds == "validation", folds == "test"
    xt, state = fit_transform(x[train])
    xv = transform(x[validation], state)
    candidates = {}
    for alpha in AFT_ALPHAS:
        theta, success, message, iterations, max_gradient = _aft_fit(xt, time[train], event[train], alpha)
        candidates[alpha] = (float(_aft_nll(theta, xv, time[validation], event[validation])), theta, success, message, iterations, max_gradient)
    selected = min(AFT_ALPHAS, key=lambda alpha: candidates[alpha][0])
    fit = train | validation
    xf, state = fit_transform(x[fit])
    xe = transform(x[test], state)
    initial = candidates[selected][1]
    if len(initial) != xf.shape[1] + 2:
        initial = None
    theta, success, message, iterations, max_gradient = _aft_fit(xf, time[fit], event[fit], selected, initial)
    pred_time = np.exp(np.c_[np.ones(len(xe)), xe] @ theta[:-1])
    stopped = event[test] == 1
    metrics = {
        "c_index": _c_index(time[test], event[test], pred_time),
        "censored_nll": float(_aft_nll(theta, xe, time[test], event[test])),
        "observed_stop_mae": mae(time[test][stopped], pred_time[stopped]),
        "alpha": selected,
        "optimizer_success": success,
        "optimizer_message": message,
        "optimizer_iterations": iterations,
        "optimizer_max_abs_gradient": max_gradient,
        "n": int(sum(test)),
        "events": int(sum(event[test])),
        "censored": int(sum(1 - event[test])),
    }
    test_rows = [row for row in rows if row["fold"] == "test"]
    return metrics, {row["session_id"]: float(pred_time[i]) for i, row in enumerate(test_rows)}


def aft_in_scope(condition, k):
    return condition in {"C1", "C5"} or k == 20


def run_config(data, condition, k):
    rows = sim.history_rows(data, condition, k)
    continuous, raw_continuous, keys = fit_continuous(rows)
    completion, raw_completion = fit_completion(rows)
    stopped_time, raw_stopped = fit_stopped_time(rows)
    aft, raw_aft = (fit_aft(rows) if aft_in_scope(condition, k) else ({"status": "NOT_IN_PREREGISTERED_AFT_SCOPE"}, {}))
    raw = []
    for row in (x for x in rows if x["fold"] == "test"):
        sid = row["session_id"]
        raw.append({
            "session_id": sid,
            "subject_id": row["subject_id"],
            "truth_continuous": {target: float(target_value(row, target)) for target in CONTINUOUS_TARGETS},
            "prediction_continuous": raw_continuous[sid],
            "truth_completed": int(row["targets"]["completed"]),
            "prediction_completed": raw_completion[sid],
            "truth_stop_time_min": row["targets"]["stop_time_min"],
            "prediction_stopped_only_min": raw_stopped.get(sid),
            "prediction_aft_median_min": raw_aft.get(sid),
        })
    return {"continuous": continuous, "completion": completion, "stopped_time": stopped_time, "aft": aft, "feature_count": len(keys)}, raw


def summarize(results):
    summary = {}
    for dataset in DATASETS:
        summary[dataset] = {}
        for k in KS:
            summary[dataset][str(k)] = {}
            for condition in CONDITIONS:
                base_condition = "C1"
                entry = {"continuous": {}, "completion": {}, "stopped_time": {}, "aft": {}}
                for target in CONTINUOUS_TARGETS:
                    values = [results[str(seed)][dataset][str(k)][condition]["continuous"][target]["mae"] for seed in SEEDS]
                    base = [results[str(seed)][dataset][str(k)][base_condition]["continuous"][target]["mae"] for seed in SEEDS]
                    diff = [b - v for b, v in zip(base, values)]
                    entry["continuous"][target] = {"mae": ci(values), "C1_minus_condition": ci(diff), "improved_seeds": sum(x > 0 for x in diff)}
                values = [results[str(seed)][dataset][str(k)][condition]["completion"]["brier"] for seed in SEEDS]
                base = [results[str(seed)][dataset][str(k)][base_condition]["completion"]["brier"] for seed in SEEDS]
                diff = [b - v for b, v in zip(base, values)]
                entry["completion"] = {"brier": ci(values), "C1_minus_condition": ci(diff), "improved_seeds": sum(x > 0 for x in diff)}
                values = [results[str(seed)][dataset][str(k)][condition]["stopped_time"]["mae"] for seed in SEEDS]
                base = [results[str(seed)][dataset][str(k)][base_condition]["stopped_time"]["mae"] for seed in SEEDS]
                diff = [b - v for b, v in zip(base, values)]
                entry["stopped_time"] = {"mae": ci(values), "C1_minus_condition": ci(diff), "improved_seeds": sum(x > 0 for x in diff)}
                if aft_in_scope(condition, k):
                    values = [results[str(seed)][dataset][str(k)][condition]["aft"]["c_index"] for seed in SEEDS]
                    entry["aft"] = {"c_index": ci(values), "optimizer_all_success": all(results[str(seed)][dataset][str(k)][condition]["aft"]["optimizer_success"] for seed in SEEDS)}
                summary[dataset][str(k)][condition] = entry
    return summary


def phase1_decisions(summary):
    decisions = {}
    for dataset in DATASETS:
        decisions[dataset] = {}
        primary = summary[dataset]["20"]["C5"]
        for target in ("pre_fatigue_latent", "pre_condition_construct", "post_burden_latent"):
            d = primary["continuous"][target]["C1_minus_condition"]
            decisions[dataset][target] = {
                "difference": d,
                "improved_seeds": primary["continuous"][target]["improved_seeds"],
                "meets_direction_and_ci": primary["continuous"][target]["improved_seeds"] == 5 and d["ci95"][0] > 0,
                "meets_0_02_threshold": d["mean"] >= 0.02,
            }
        for target, block in (("recovery_delay_h", primary["continuous"]["recovery_delay_h"]), ("completion", primary["completion"]), ("stopped_time", primary["stopped_time"])):
            d = block["C1_minus_condition"]
            decisions[dataset][target] = {"difference": d, "improved_seeds": block["improved_seeds"], "direction_and_ci": block["improved_seeds"] == 5 and d["ci95"][0] > 0}
    decisions["overall_note"] = "Phase 1 direction only; final protocol classification also requires history identity/time-order destruction and sensitivity analyses."
    return decisions


def main(quick=False):
    verify_analysis_lock()
    OUT.mkdir(parents=True, exist_ok=True)
    seeds = SEEDS[:1] if quick else SEEDS
    datasets = DATASETS[:1] if quick else DATASETS
    ks = (0, 20) if quick else KS
    conditions = ("C1", "C5", "C6", "C7") if quick else CONDITIONS
    results, split_manifest = {}, {}
    raw_path = OUT / ("raw_predictions_quick.jsonl.gz" if quick else "raw_predictions.jsonl.gz")
    with gzip.open(raw_path, "wt", encoding="utf-8") as raw_file:
        for seed in seeds:
            results[str(seed)], split_manifest[str(seed)] = {}, {}
            for dataset in datasets:
                data = sim.generate(seed, dataset, "BASE")
                results[str(seed)][dataset], split_manifest[str(seed)][dataset] = {}, {
                    fold: sorted({x["subject_id"] for x in data["observed"] if x["fold"] == fold}) for fold in ("train", "validation", "test")
                }
                for k in ks:
                    results[str(seed)][dataset][str(k)] = {}
                    for condition in conditions:
                        metrics, raw = run_config(data, condition, k)
                        results[str(seed)][dataset][str(k)][condition] = metrics
                        for row in raw:
                            row.update({"seed": seed, "dataset": dataset, "k": k, "condition": condition})
                            raw_file.write(json.dumps(row, ensure_ascii=False) + "\n")
    payload = {
        "version": "rq1-physiological-history-value-phase1-01",
        "quick": quick,
        "seeds": list(seeds),
        "datasets": list(datasets),
        "history_lengths": list(ks),
        "conditions": list(conditions),
        "results": results,
        "summary": summarize(results) if not quick else {},
        "decisions": phase1_decisions(summarize(results)) if not quick else {},
        "hashes": {
            "protocol": sha(ROOT / "RQ1_PHYSIOLOGICAL_HISTORY_VALUE_PROTOCOL.md"),
            "parameters": sha(sim.PARAM),
            "amendment_01": sha(ROOT / "RQ1_PHYSIOLOGICAL_HISTORY_VALUE_AMENDMENT_01.md"),
            "amendment_02": sha(ROOT / "RQ1_PHYSIOLOGICAL_HISTORY_VALUE_AMENDMENT_02.md"),
            "generator": sha(ROOT / "simulator_rq1_physiological_history_value.py"),
            "runner": sha(Path(__file__)),
        },
    }
    suffix = "_quick" if quick else ""
    (OUT / f"results{suffix}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / f"split_manifest{suffix}.json").write_text(json.dumps(split_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if not quick:
        with (OUT / "summary.csv").open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["dataset", "k", "condition", "target", "metric", "mean", "sd", "ci_low", "ci_high", "C1_minus_condition", "diff_ci_low", "diff_ci_high", "improved_seeds"])
            for dataset in DATASETS:
                for k in KS:
                    for condition in CONDITIONS:
                        entry = payload["summary"][dataset][str(k)][condition]
                        for target in CONTINUOUS_TARGETS:
                            value, diff = entry["continuous"][target]["mae"], entry["continuous"][target]["C1_minus_condition"]
                            writer.writerow([dataset, k, condition, target, "MAE", value["mean"], value["sd"], *value["ci95"], diff["mean"], *diff["ci95"], entry["continuous"][target]["improved_seeds"]])
                        value, diff = entry["completion"]["brier"], entry["completion"]["C1_minus_condition"]
                        writer.writerow([dataset, k, condition, "completed", "Brier", value["mean"], value["sd"], *value["ci95"], diff["mean"], *diff["ci95"], entry["completion"]["improved_seeds"]])
                        value, diff = entry["stopped_time"]["mae"], entry["stopped_time"]["C1_minus_condition"]
                        writer.writerow([dataset, k, condition, "stop_time", "MAE", value["mean"], value["sd"], *value["ci95"], diff["mean"], *diff["ci95"], entry["stopped_time"]["improved_seeds"]])
    print(json.dumps({"quick": quick, "output": str(OUT), "configs": sum(len(results[str(s)][d][str(k)]) for s in seeds for d in datasets for k in ks)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true")
    main(parser.parse_args().quick)
