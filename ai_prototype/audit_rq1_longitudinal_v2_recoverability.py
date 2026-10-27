"""Read-only root-cause audit of v2-minimal recoverability. Generator is untouched."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

import simulator_rq1_longitudinal_v2 as sim
from validate_rq1_longitudinal_v2 import _fit_transform, _mae, _r2, _ridge_predict


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "artifacts" / "rq1_longitudinal_v2_recoverability_audit"
ACTIVITIES = ("NONE", "AEROBIC", "LOADED_MOVEMENT", "BODYWEIGHT_CIRCUIT")
CURRENT = ("current_demand", "planned_duration_min", "recovery_interval_days", "v5_kmh",
           "hr_bpm", "temperature_c", "spo2_pct", "hr_quality", "temperature_quality", "spo2_quality")


def _sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()


def _keys(row: dict, group: str, target: str) -> list[str]:
    current = list(CURRENT)
    sensor = [k for k in row if k.startswith("history_") and not any(t in k for t in ("burden_", "fatigue", "condition"))]
    target_history = [k for k in row if k.startswith("history_") and any(t in k for t in ("burden_", "fatigue", "condition"))]
    if group == "current": return current
    if group == "sensor_history": return current + sensor
    if group == "target_history": return current + target_history
    if group == "full": return current + sensor + target_history
    if group == "quality": return ["hr_quality", "temperature_quality", "spo2_quality"]
    raise ValueError(group)


def _matrix(rows: list[dict], keys: list[str]):
    X = []
    for r in rows:
        X.append([float(r.get(k)) if r.get(k) is not None else np.nan for k in keys] +
                 [float(r["activity_type"] == a) for a in ACTIVITIES])
    return np.asarray(X, dtype=float)


def _fit(rows: list[dict], keys: list[str], y: np.ndarray) -> dict:
    folds = np.array([r["fold"] for r in rows])
    X = _matrix(rows, keys)
    best = None
    for alpha in (1.0, 10.0, 100.0):
        xt, xv = _fit_transform(X[folds == "train"], X[folds == "validation"])
        pred = _ridge_predict(xt, y[folds == "train"], xv, alpha)
        mae = _mae(y[folds == "validation"], pred)
        if best is None or mae < best[0]: best = (mae, alpha)
    fit = folds != "test"
    xt, xe = _fit_transform(X[fit], X[folds == "test"])
    pred = _ridge_predict(xt, y[fit], xe, best[1])
    truth = y[folds == "test"]
    return {"mae": _mae(truth, pred), "r2": _r2(truth, pred), "alpha": best[1], "n_test": int(len(truth))}


def _simple(rows: list[dict], target: str, which: str) -> dict:
    truth, pred = [], []
    for r in rows:
        if r["fold"] != "test" or r["targets"].get(target) is None: continue
        key = f"history_{target}_{which}"
        if r.get(key) is None: continue
        truth.append(r["targets"][target]); pred.append(r[key])
    return {"mae": _mae(np.asarray(truth), np.asarray(pred)), "r2": _r2(np.asarray(truth), np.asarray(pred)), "n_test": len(truth)}


def _corr(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    return float(np.corrcoef(x[ok], y[ok])[0, 1]) if ok.sum() > 2 else None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    data = sim.generate(110, "BASE")
    rows = sim.history_features(data, 20)
    result = {"version": "rq1-longitudinal-v2-recoverability-root-cause-audit-01",
              "scope": "read-only single-seed BASE audit; no parameter/generator change", "targets": {}, "method_findings": []}
    for target in ("burden_BASE", "fatigue", "condition"):
        usable = [r for r in rows if r["targets"].get(target) is not None]
        y = np.asarray([r["targets"][target] for r in usable], float)
        folds = np.asarray([r["fold"] for r in usable])
        train_mean = float(y[folds != "test"].mean())
        mean_mae = _mae(y[folds == "test"], np.repeat(train_mean, (folds == "test").sum()))
        models = {g: _fit(usable, _keys(usable[0], g, target), y) for g in ("current", "sensor_history", "target_history", "full", "quality")}
        no = np.asarray([r["audit_true"]["noiseless_targets"][target] for r in usable], float)
        bias = np.asarray([r["audit_true"]["reporting_bias"][target] for r in usable], float)
        conditional = np.clip(no + bias, 0, 10)
        latent_mae = _mae(y[folds == "test"], conditional[folds == "test"])
        sensor_sep = mean_mae - latent_mae
        observed_recovery = (mean_mae - models["sensor_history"]["mae"]) / sensor_sep
        full_recovery = (mean_mae - models["full"]["mae"]) / sensor_sep
        noise_free_sensor = _fit(usable, _keys(usable[0], "sensor_history", target), conditional)
        noise_free_full = _fit(usable, _keys(usable[0], "full", target), conditional)
        pure_models = {g: _fit(usable, _keys(usable[0], g, target), no)
                       for g in ("current", "sensor_history", "target_history", "full")}
        pure_mean = float(no[folds != "test"].mean())
        pure_mean_mae = _mae(no[folds == "test"], np.repeat(pure_mean, (folds == "test").sum()))
        past_mean_key = f"history_{target}_mean"
        result["targets"][target] = {
            "mean_mae": mean_mae, "models": models,
            "simple_last": _simple(usable, target, "last"), "simple_mean20": _simple(usable, target, "mean"),
            "deterministic_latent_oracle_mae": latent_mae,
            "recoverability_protocol_compliant_sensor_history": observed_recovery,
            "recoverability_full_history_not_valid_for_old_oracle_rule": full_recovery,
            "noise_free_sensor_history_r2": noise_free_sensor["r2"],
            "noise_free_full_history_r2": noise_free_full["r2"],
            "pure_noiseless_subjective_state": {"mean_mae": pure_mean_mae, "models": pure_models},
            "past_target_mean_vs_current_reporting_bias_r": _corr([r.get(past_mean_key) for r in usable], bias),
            "observed_minus_noiseless_vs_current_reporting_bias_r": _corr(y-no, bias),
        }

    # Can observable history recover the two latent quantities that matter most?
    capacity_y = np.asarray([r["audit_true"]["capacity_log_change"] for r in rows], float)
    condition_bias_y = np.asarray([r["audit_true"]["reporting_bias"]["condition"] for r in rows], float)
    result["latent_recovery"] = {
        "sensor_history_to_capacity_change": _fit(rows, _keys(rows[0], "sensor_history", "condition"), capacity_y),
        "sensor_history_to_condition_reporting_bias": _fit(rows, _keys(rows[0], "sensor_history", "condition"), condition_bias_y),
        "target_history_to_condition_reporting_bias": _fit(rows, _keys(rows[0], "target_history", "condition"), condition_bias_y),
        "full_history_to_condition_reporting_bias": _fit(rows, _keys(rows[0], "full", "condition"), condition_bias_y),
    }

    protocol_status = []
    for target, item in result["targets"].items():
        recovery, nf = item["recoverability_protocol_compliant_sensor_history"], item["noise_free_sensor_history_r2"]
        status = "FAIL" if recovery >= .90 or nf >= .95 else "WARNING" if recovery >= .75 or nf >= .85 else "PASS"
        item["corrected_trivial_recoverability_status"] = status; protocol_status.append(status)
    result["method_findings"] = [
        "The first dry-run validator incorrectly included past target summaries in the observed model used for the legacy trivial-recoverability ratio.",
        "The first validator used a learned latent-feature Ridge rather than the preregistered deterministic conditional-mean oracle.",
        "The first noise-free probe removed reporting bias as well as session noise, although the protocol removes session label noise only.",
    ]
    full_observed_gains, pure_gains = [], []
    observed_history_increment, pure_history_increment = [], []
    for item in result["targets"].values():
        full_observed_gains.append(item["mean_mae"] - item["models"]["full"]["mae"])
        observed_history_increment.append(item["models"]["current"]["mae"] - item["models"]["full"]["mae"])
        pure = item["pure_noiseless_subjective_state"]
        pure_gains.append(pure["mean_mae"] - pure["models"]["full"]["mae"])
        pure_history_increment.append(pure["models"]["current"]["mae"] - pure["models"]["full"]["mae"])
    result["classification"] = {
        "validator": "METHOD_FIX_REQUIRED" if "FAIL" not in protocol_status else "GENERATOR_REDESIGN_REQUIRED",
        "information_path": "REPORTING_STYLE_DOMINANT" if np.mean(full_observed_gains) > 2 * max(np.mean(pure_gains), 1e-9) else "MIXED_STATE_AND_REPORTING",
        "full_observed_mean_gain": float(np.mean(full_observed_gains)),
        "pure_noiseless_state_mean_gain": float(np.mean(pure_gains)),
        "observed_history_increment_over_current": float(np.mean(observed_history_increment)),
        "pure_state_history_increment_over_current": float(np.mean(pure_history_increment)),
    }
    out = OUT / "audit.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
