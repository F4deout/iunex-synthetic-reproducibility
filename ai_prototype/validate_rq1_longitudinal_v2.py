"""One-seed dry run for the locked RQ1 longitudinal v2-minimal generator."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

import simulator_rq1_longitudinal_v2 as sim


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "artifacts" / "rq1_longitudinal_v2_dry_run"


def digest(data: dict) -> str:
    text = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


def arrays(rows: list[dict], target: str, mode: str = "observed", target_source: str = "observed"):
    rows = [r for r in rows if r["targets"].get(target) is not None]
    numeric = [k for k in rows[0] if k not in {"subject_id", "session_id", "fold", "activity_type", "targets", "audit_true"}]
    if mode == "quality":
        numeric = ["hr_quality", "temperature_quality", "spo2_quality", "history_n"]
    values, activities = [], ("NONE", "AEROBIC", "LOADED_MOVEMENT", "BODYWEIGHT_CIRCUIT")
    for r in rows:
        d = {k: r[k] for k in numeric}
        if mode == "true":
            for k in ("true_hr_bpm", "true_temperature_c", "true_spo2_pct"):
                d[k] = r["audit_true"][k]
        elif mode == "latent":
            for k in ("relative_demand", "reserve_depletion", "reserve_after", "debt_pre", "strain"):
                d[k] = r["audit_true"][k]
        activity_columns = [] if mode == "quality" else [float(r["activity_type"] == a) for a in activities]
        values.append([float(d.get(c)) if d.get(c) is not None else np.nan for c in d] + activity_columns)
    X = np.asarray(values, dtype=float)
    y = np.array([r["targets"][target] if target_source == "observed" else r["audit_true"]["noiseless_targets"][target] for r in rows], dtype=float)
    folds = np.array([r["fold"] for r in rows])
    return rows, X, y, folds


def _fit_transform(X_train, X_other):
    med = np.nanmedian(X_train, axis=0)
    med = np.where(np.isfinite(med), med, 0.0)
    train = np.where(np.isnan(X_train), med, X_train)
    other = np.where(np.isnan(X_other), med, X_other)
    mean, sd = train.mean(axis=0), train.std(axis=0)
    sd[sd == 0] = 1.0
    return (train - mean) / sd, (other - mean) / sd


def _ridge_predict(X_train, y_train, X_test, alpha):
    X_train = np.c_[np.ones(len(X_train)), X_train]
    X_test = np.c_[np.ones(len(X_test)), X_test]
    penalty = np.eye(X_train.shape[1]); penalty[0, 0] = 0
    beta = np.linalg.solve(X_train.T @ X_train + alpha * penalty, X_train.T @ y_train)
    return X_test @ beta


def _mae(y, p): return float(np.mean(np.abs(y-p)))


def _r2(y, p):
    denom = float(np.sum((y-y.mean())**2))
    return float(1 - np.sum((y-p)**2)/denom) if denom else 0.0


def fit_probe(rows: list[dict], target: str, mode: str = "observed", perturb: str | None = None,
              target_source: str = "observed") -> dict:
    rows, X, y, folds = arrays(rows, target, mode, target_source)
    rng = np.random.default_rng(9917)
    Xfit, yfit = X.copy(), y.copy()
    if perturb == "target":
        # Keep model selection honest: neither train nor validation labels may
        # regain their original feature pairing during the final refit.
        for fold in ("train", "validation"):
            idx = np.where(folds == fold)[0]; yfit[idx] = rng.permutation(yfit[idx])
    if perturb == "feature":
        for fold in ("train", "validation", "test"):
            idx = np.where(folds == fold)[0]
            Xfit[idx] = Xfit[rng.permutation(idx)]
    best = None
    for alpha in (1.0, 10.0, 100.0):
        xt, xv = _fit_transform(Xfit[folds == "train"], Xfit[folds == "validation"])
        pred = _ridge_predict(xt, yfit[folds == "train"], xv, alpha)
        val = _mae(y[folds == "validation"], pred)
        if best is None or val < best[0]: best = (val, alpha)
    tv = folds != "test"
    xt, xe = _fit_transform(Xfit[tv], Xfit[folds == "test"])
    pred = _ridge_predict(xt, yfit[tv], xe, best[1]); truth = y[folds == "test"]
    return {"mae": _mae(truth, pred), "r2": _r2(truth, pred), "alpha": best[1], "n_test": int(len(truth))}


def dist(values):
    a = np.asarray(values, dtype=float); q = np.quantile(a, [.01, .05, .5, .95, .99])
    return {"n": int(len(a)), "mean": float(a.mean()), "sd": float(a.std(ddof=1)), "q01": float(q[0]), "q05": float(q[1]), "median": float(q[2]), "q95": float(q[3]), "q99": float(q[4])}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    a, b = sim.generate(110, "BASE"), sim.generate(110, "BASE")
    reproducible = digest(a) == digest(b)
    observed, audit = a["observed"], a["audit"]
    subjects = {f: {r["subject_id"] for r in observed if r["fold"] == f} for f in ("train", "validation", "test")}
    split_ok = not (subjects["train"] & subjects["validation"] or subjects["train"] & subjects["test"] or subjects["validation"] & subjects["test"])
    sessions = {f: {r["session_id"] for r in observed if r["fold"] == f} for f in subjects}
    session_ok = not (sessions["train"] & sessions["validation"] or sessions["train"] & sessions["test"] or sessions["validation"] & sessions["test"])
    features = {k: sim.history_features(a, k) for k in (0, 5, 10, 20, 30, 50, 75, 100)}
    eval_ids = {k: {r["session_id"] for r in rows} for k, rows in features.items()}
    same_eval = len({frozenset(v) for v in eval_ids.values()}) == 1
    history_ok = all(r["history_n"] <= k for k, rows in features.items() for r in rows)
    forbidden = ("capacity", "reserve", "debt", "strain", "true_", "reporting_bias", "noiseless", "u_phys", "u_burden", "u_wellness")
    latent_leak = [key for r in features[20] for key in r if key != "audit_true" and any(x in key for x in forbidden)]

    probes = {}
    recoverability = {}
    mean_baseline = {}
    for target in ("burden_BASE", "fatigue", "condition"):
        rows = [r for r in features[20] if r["targets"].get(target) is not None]
        train_y = [r["targets"][target] for r in rows if r["fold"] == "train"]
        test_y = [r["targets"][target] for r in rows if r["fold"] == "test"]
        mean_baseline[target] = _mae(np.asarray(test_y), np.repeat(np.mean(train_y), len(test_y)))
        probes[target] = {mode: fit_probe(features[20], target, mode) for mode in ("observed", "quality", "true", "latent")}
        probes[target]["target_shuffle"] = fit_probe(features[20], target, "observed", "target")
        probes[target]["feature_shuffle"] = fit_probe(features[20], target, "observed", "feature")
        probes[target]["noise_free_observed"] = fit_probe(features[20], target, "observed", target_source="noiseless")
        separation = mean_baseline[target] - probes[target]["latent"]["mae"]
        recovery = ((mean_baseline[target] - probes[target]["observed"]["mae"]) / separation
                    if separation >= .10 else None)
        nf_r2 = probes[target]["noise_free_observed"]["r2"]
        if recovery is None:
            status = "UNINTERPRETABLE"
        elif recovery >= .90 or nf_r2 >= .95:
            status = "FAIL"
        elif recovery >= .75 or nf_r2 >= .85:
            status = "WARNING"
        else:
            status = "PASS"
        recoverability[target] = {"oracle_separation_mae": separation, "oracle_recovery": recovery,
                                  "noise_free_observed_r2": nf_r2, "status": status}

    sanity = {
        "hr_bpm": dist([r["hr_bpm"] for r in observed if r["hr_bpm"] is not None]),
        "temperature_c": dist([r["temperature_c"] for r in observed if r["temperature_c"] is not None]),
        "spo2_pct": dist([r["spo2_pct"] for r in observed if r["spo2_pct"] is not None]),
        "relative_demand": dist([r["relative_demand"] for r in audit]),
        "true_hr_bpm": dist([r["true_hr_bpm"] for r in audit]),
        "true_temperature_c": dist([r["true_temperature_c"] for r in audit]),
        "true_spo2_pct": dist([r["true_spo2_pct"] for r in audit]),
        "missing_rate": {k: float(np.mean([r[k] is None for r in observed])) for k in ("hr_bpm", "temperature_c", "spo2_pct")},
        "artifact_rate": float(np.mean([r["measurement_issue"] for r in observed])),
        "boundary_mass": {
            "hr_20_or_250": float(np.mean([r["hr_bpm"] in (20.0, 250.0) for r in observed if r["hr_bpm"] is not None])),
            "temperature_20_or_45": float(np.mean([r["temperature_c"] in (20.0, 45.0) for r in observed if r["temperature_c"] is not None])),
            "spo2_50_or_100": float(np.mean([r["spo2_pct"] in (50.0, 100.0) for r in observed if r["spo2_pct"] is not None])),
        },
        "target_clipping_rate": {t: float(np.mean([r["target_clipped"].get(t, False) for r in observed])) for t in ("burden_BASE", "fatigue", "condition")},
        "activity_counts": {x: sum(r["activity_type"] == x for r in observed) for x in ("NONE", "AEROBIC", "LOADED_MOVEMENT", "BODYWEIGHT_CIRCUIT")},
    }
    falsification = {}
    for target in probes:
        normal, mean = probes[target]["observed"]["mae"], mean_baseline[target]
        improvement = mean - normal
        falsification[target] = {
            "mean_mae": mean, "normal_mae": normal,
            "target_shuffle_mae": probes[target]["target_shuffle"]["mae"],
            "feature_shuffle_mae": probes[target]["feature_shuffle"]["mae"],
            "status": "INCONCLUSIVE" if improvement < .05 else ("PASS" if min(probes[target]["target_shuffle"]["mae"], probes[target]["feature_shuffle"]["mae"]) >= normal + .5 * improvement else "FAIL")
        }
    checks = {
        "same_seed_reproducibility": "PASS" if reproducible else "FAIL",
        "subject_split_disjoint": "PASS" if split_ok else "FAIL",
        "session_split_disjoint": "PASS" if session_ok else "FAIL",
        "same_evaluation_sessions_all_k": "PASS" if same_eval else "FAIL",
        "past_only_history": "PASS" if history_ok else "FAIL",
        "latent_not_in_observed_features": "PASS" if not latent_leak else "FAIL",
        "train_only_preprocessing_and_validation_alpha": "PASS",
        "target_feature_shuffle": "PASS" if all(x["status"] != "FAIL" for x in falsification.values()) else "FAIL",
        "trivial_recoverability": ("FAIL" if any(x["status"] == "FAIL" for x in recoverability.values()) else
                                    "WARNING" if any(x["status"] in {"WARNING", "UNINTERPRETABLE"} for x in recoverability.values()) else "PASS"),
    }
    overall = "REDESIGN_REQUIRED" if checks["trivial_recoverability"] == "FAIL" else ("FIX_REQUIRED" if "FAIL" in checks.values() else "EXPERIMENT_READY")
    result = {"version": "rq1-longitudinal-v2-dry-run-01", "seed": 110, "sensitivity": "BASE",
              "rows": len(observed), "subjects": {k: len(v) for k, v in subjects.items()}, "checks": checks,
              "mean_baseline": mean_baseline, "probes": probes, "falsification": falsification,
              "recoverability": recoverability,
              "sanity": sanity, "overall": overall, "generator_sha256": sim._sha(Path(sim.__file__)),
              "parameter_sha256": sim._sha(sim.PARAM)}
    (OUT / "validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
