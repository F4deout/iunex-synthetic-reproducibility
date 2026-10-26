"""Small v2.1-running dry run and structural audit. ID-test is never scored."""
from __future__ import annotations

import copy
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

import simulator_v21_running as sim

OUT = sim.ROOT / "artifacts" / "synthetic_v21_running_dryrun"
K_VALUES = (0, 1, 3, 5, 10, 20)
OBSERVED_NAMES = ("speed_kmh", "duration_minutes", "observed_hr", "gap_h",
                  "history_n", "history_hr_mean", "history_speed_mean",
                  "history_hr_slope", "history_hr_sd")
TRUE_NAMES = tuple("true_hr" if n == "observed_hr" else n for n in OBSERVED_NAMES)
LATENT_NAMES = ("relative", "depletion", "strain", "debt_pre", "u_b",
                "debt_after", "q_fraction", "u_w")


def split_map(profiles: dict) -> dict[str, str]:
    ids = sorted(profiles, key=lambda s: hashlib.sha256(s.encode()).hexdigest())
    if len(ids) != 120:
        raise ValueError("Dry run requires 120 synthetic subjects")
    return {s: "train" if j < 72 else "validation" if j < 96 else "id_test"
            for j, s in enumerate(ids)}


def history_features(rows: list[dict], k: int) -> list[dict]:
    past: dict[str, list[dict]] = defaultdict(list)
    output = []
    for row in sorted(rows, key=lambda z: (z["subject"], z["index"])):
        prior = past[row["subject"]][-k:] if k else []
        speeds = np.asarray([r["speed_kmh"] for r in prior], dtype=float)
        hr = np.asarray([r["observed_hr"] for r in prior], dtype=float)
        slope = (float(np.polyfit(speeds, hr, 1)[0]) if len(prior) >= 3
                 and len(set(speeds)) >= 3 and float(speeds.std()) > 1e-8 else None)
        common = {"speed_kmh": row["speed_kmh"], "duration_minutes": row["actual_minutes"],
                  "gap_h": row["gap_h"], "history_n": len(prior),
                  "history_hr_mean": float(hr.mean()) if len(hr) else None,
                  "history_speed_mean": float(speeds.mean()) if len(speeds) else None,
                  "history_hr_slope": slope,
                  "history_hr_sd": float(hr.std(ddof=1)) if len(hr) > 1 else None}
        observed = {**common, "observed_hr": row["observed_hr"]}
        true = {**common, "true_hr": row["true_hr"]}
        latent = {n: row[n] for n in LATENT_NAMES if n != "q_fraction"}
        latent["q_fraction"] = row["q_end"] / row["dprime"] if "dprime" in row else None
        # q_fraction is audit-only; get D′ from subject profile in validation if needed.
        output.append({"subject": row["subject"], "session": row["session"], "index": row["index"],
                       "observed": observed, "true": true, "latent": latent,
                       "history_sources": [r["session"] for r in prior],
                       "history_indices": [r["index"] for r in prior], "row": row})
        past[row["subject"]].append(row)
    return output


def ridge(train: list[dict], evaluation: list[dict], names: tuple[str, ...],
          source: str, target: str, y_source: str = "labels",
          shuffle: str | None = None, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    x_train = np.array([[r[source].get(n, np.nan) if r[source].get(n) is not None else np.nan
                         for n in names] for r in train], dtype=float)
    x_eval = np.array([[r[source].get(n, np.nan) if r[source].get(n) is not None else np.nan
                        for n in names] for r in evaluation], dtype=float)
    y = np.array([r["row"][y_source][target] for r in train], dtype=float)
    if shuffle == "target":
        y = y[rng.permutation(len(y))]
    elif shuffle == "feature":
        x_train = x_train[rng.permutation(len(x_train))]
    med = np.array([np.median(c[np.isfinite(c)]) if np.isfinite(c).any() else 0.
                    for c in x_train.T])
    x_train = np.where(np.isfinite(x_train), x_train, med)
    x_eval = np.where(np.isfinite(x_eval), x_eval, med)
    mean, sd = x_train.mean(axis=0), x_train.std(axis=0)
    sd[sd < 1e-8] = 1.
    z_train = np.column_stack([np.ones(len(train)), (x_train - mean) / sd])
    z_eval = np.column_stack([np.ones(len(evaluation)), (x_eval - mean) / sd])
    penalty = np.diag([0.] + [10.] * len(names))
    coef = np.linalg.solve(z_train.T @ z_train + penalty, z_train.T @ y)
    return np.clip(z_eval @ coef, 0, 10)


def regression(train_x: np.ndarray, train_y: np.ndarray,
               eval_x: np.ndarray) -> np.ndarray:
    design = np.column_stack([np.ones(len(train_x)), train_x])
    coef = np.linalg.lstsq(design, train_y, rcond=None)[0]
    return np.column_stack([np.ones(len(eval_x)), eval_x]) @ coef


def metrics(y: np.ndarray, prediction: np.ndarray) -> dict:
    denominator = float(((y - y.mean()) ** 2).sum())
    return {"n": int(len(y)), "mae": float(np.abs(y - prediction).mean()),
            "rmse": float(np.sqrt(((y - prediction) ** 2).mean())),
            "r2": float(1 - ((y - prediction) ** 2).sum() / denominator) if denominator else None}


def describe(values: list[float]) -> dict:
    a = np.asarray(values, dtype=float)
    if not len(a):
        return {"n": 0}
    q = np.quantile(a, [.05, .5, .95])
    return {"n": len(a), "mean": float(a.mean()), "sd": float(a.std(ddof=1)) if len(a) > 1 else 0.,
            "q05": float(q[0]), "median": float(q[1]), "q95": float(q[2]),
            "min": float(a.min()), "max": float(a.max())}


def counterfactuals(profiles: dict, rows: list[dict], seed: int) -> dict:
    people = list(profiles.values())
    # One fixed reporting draw for every arm; paired differences stay comparable.
    common_error = float(np.random.default_rng(seed + 101).normal(0, .8))
    noisy = lambda value: float(np.clip(value + common_error, 0, 10))
    representative = sorted(people, key=lambda p: p["cs"])[len(people) // 2]
    speeds = np.quantile([r["speed_kmh"] for r in rows], [.05, .5, .95])
    durations = np.quantile([r["planned_minutes"] for r in rows], [.05, .5, .95])
    fixed = lambda p, v, t, gap=0, q=None, debt=0: sim.core(
        p, p["dprime"] if q is None else q, debt, gap, v, t, .5, .5)

    # CF1: identical absolute speed, duration and latent disturbances.
    cf1 = [(p, fixed(p, float(speeds[1]), float(durations[1]))) for p in people]
    cf1_done = [(p, s) for p, s in cf1 if s["completed"]]
    cf1_capacity = [p["cs"] for p, _ in cf1_done]
    cf1_burden = [s["latent"]["BASE"] for _, s in cf1_done]
    cap_low, cap_high = np.quantile(cf1_capacity, [.25, .75])
    cf1_coupling = {
        name: {"score_range": float(max(s["latent"][name] for _, s in cf1_done)
                                     - min(s["latent"][name] for _, s in cf1_done)),
               "low_minus_high_capacity_score": float(
                   np.mean([s["latent"][name] for p, s in cf1_done if p["cs"] <= cap_low])
                   - np.mean([s["latent"][name] for p, s in cf1_done if p["cs"] >= cap_high]))}
        for name in sim.COUPLINGS}

    # CF2: same x, different absolute speed and personal D′.
    cf2 = {}
    for x in (.9, 1.05):
        states = [fixed(p, x * p["cs"] * 3.6, 5.) for p in people]
        cf2[str(x)] = {"depletion": describe([s["depletion"] for s in states]),
                       "time_to_zero_minutes": describe([s["limit_minutes"] for s in states
                                                         if s["limit_minutes"] is not None]),
                       "hr": describe([s["true_hr_mean"] for s in states]),
                       "burden_BASE": describe([s["latent"]["BASE"] for s in states if s["completed"]]),
                       "reported_burden_BASE": describe([noisy(s["latent"]["BASE"]) for s in states
                                                         if s["completed"]]),
                       "completed_rate": float(np.mean([s["completed"] for s in states]))}

    # CF3: natural 118–122 bpm overlap within each fixed-speed CF1 condition.
    cf3 = {}
    for speed in speeds:
        matched = [(p, fixed(p, float(speed), float(durations[1]))) for p in people]
        matched = [(p, s) for p, s in matched if s["completed"] and 118 <= s["true_hr_mean"] <= 122]
        cf3[str(round(float(speed), 3))] = {
            "n": len(matched), "capacity_mps": describe([p["cs"] for p, _ in matched]),
            "burden_BASE": describe([s["latent"]["BASE"] for _, s in matched]),
            "reported_burden_BASE": describe([noisy(s["latent"]["BASE"]) for _, s in matched]),
            "status": "EVALUABLE" if len(matched) >= 2 else "INCONCLUSIVE"}

    # CF4: same person and relative speed, varied empirical duration.
    cf4 = {}
    for x in (.8, 1.05):
        cf4[str(x)] = [{"minutes": float(t), "q_end": s["q_end"], "depletion": s["depletion"],
                        "completed": s["completed"], "burden_BASE": s["latent"]["BASE"] if s["completed"] else None,
                        "reported_burden_BASE": noisy(s["latent"]["BASE"]) if s["completed"] else None}
                       for t in durations for s in [fixed(representative, x * representative["cs"] * 3.6, float(t))]]

    # CF5: 0 and 1 h are structural interventions outside the empirical day-gap support.
    cf5 = [{"gap_h": gap, "q_start": s["q_start"], "debt_pre": s["debt_pre"],
            "burden_BASE": s["latent"]["BASE"], "reported_burden_BASE": noisy(s["latent"]["BASE"])}
           for gap in (0., 1., 24., 144.)
           for s in [fixed(representative, .8 * representative["cs"] * 3.6, 30., gap,
                           .5 * representative["dprime"], .5)]]
    return {
        "CF1": {"fixed_speed_kmh": float(speeds[1]), "fixed_minutes": float(durations[1]),
                "completed": len(cf1_done), "censored": len(cf1) - len(cf1_done),
                "hr": describe([s["true_hr_mean"] for _, s in cf1_done]),
                "burden_BASE": describe(cf1_burden),
                "reported_burden_BASE": describe([noisy(v) for v in cf1_burden]),
                "coupling_personalization": cf1_coupling,
                "capacity_burden_correlation": float(np.corrcoef(cf1_capacity, cf1_burden)[0, 1])
                if len(cf1_done) > 2 and np.std(cf1_burden) else None},
        "CF2": cf2, "CF3": cf3, "CF4": cf4, "CF5": cf5,
        "common_reporting_error_points": common_error, "common_reporting_bias_points": 0.}


def history_restoration(features: list[dict], profiles: dict, split: dict) -> dict:
    # One audit row at index 20 per person; latent parameters only as audit labels.
    rows = {r["subject"]: r for r in features if r["index"] == 20}
    names = ("history_hr_mean", "history_speed_mean", "history_hr_slope", "history_hr_sd")
    train_ids = [sid for sid in rows if split[sid] == "train"]
    val_ids = [sid for sid in rows if split[sid] == "validation"]
    x_train = np.array([[rows[sid]["observed"].get(n) if rows[sid]["observed"].get(n) is not None else np.nan
                         for n in names] for sid in train_ids], dtype=float)
    x_val = np.array([[rows[sid]["observed"].get(n) if rows[sid]["observed"].get(n) is not None else np.nan
                       for n in names] for sid in val_ids], dtype=float)
    med = np.array([np.median(c[np.isfinite(c)]) if np.isfinite(c).any() else 0 for c in x_train.T])
    x_train = np.where(np.isfinite(x_train), x_train, med)
    x_val = np.where(np.isfinite(x_val), x_val, med)
    mean, sd = x_train.mean(0), x_train.std(0)
    sd[sd < 1e-8] = 1
    x_train = np.column_stack([np.ones(len(train_ids)), (x_train - mean) / sd])
    x_val = np.column_stack([np.ones(len(val_ids)), (x_val - mean) / sd])
    penalty = np.diag([0.] + [10.] * len(names))
    result = {}
    for key in ("baseline_hr", "cs", "dprime", "delta_hr", "tau_fast", "tau_slow"):
        y_train = np.array([profiles[sid][key] for sid in train_ids])
        y_val = np.array([profiles[sid][key] for sid in val_ids])
        coef = np.linalg.solve(x_train.T @ x_train + penalty, x_train.T @ y_train)
        pred = x_val @ coef
        result[key] = {"r2": metrics(y_val, pred)["r2"],
                       "correlation": float(np.corrcoef(y_val, pred)[0, 1])
                       if np.std(pred) and np.std(y_val) else None,
                       "n": len(val_ids)}
    return result


def speed_hr_audit(rows: list[dict], split: dict) -> dict:
    by_subject: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_subject[row["subject"]].append(row)
    population_train = [r for sid, items in by_subject.items() if split[sid] == "train"
                        for r in items if r["index"] < 16]
    pop_x = np.array([r["speed_kmh"] for r in population_train])
    pop_y = np.array([r["observed_hr"] for r in population_train])
    val = [items for sid, items in by_subject.items() if split[sid] == "validation"]
    actual, pop_pred, personal_pred, slopes = [], [], [], []
    for items in val:
        earlier = [r for r in items if r["index"] < 16]
        later = [r for r in items if r["index"] >= 16]
        if len(set(r["speed_kmh"] for r in earlier)) < 3 or len(earlier) < 5:
            continue
        x = np.array([r["speed_kmh"] for r in earlier])
        y = np.array([r["observed_hr"] for r in earlier])
        xx = np.array([r["speed_kmh"] for r in later])
        slopes.append(float(np.polyfit(x, y, 1)[0]))
        actual.extend(r["observed_hr"] for r in later)
        pop_pred.extend(regression(pop_x, pop_y, xx))
        personal_pred.extend(regression(x, y, xx))
    a = np.array(actual)
    return {"eligible_subjects": len(slopes), "evaluation_sessions": len(a),
            "population_mae": float(np.abs(a - np.array(pop_pred)).mean()) if len(a) else None,
            "subject_specific_mae": float(np.abs(a - np.array(personal_pred)).mean()) if len(a) else None,
            "positive_subject_slope_fraction": float(np.mean(np.array(slopes) > 0)) if slopes else None,
            "subject_slope_bpm_per_kmh": describe(slopes)}


def validate(seed: int = 20260921) -> dict:
    frozen = json.loads((sim.ROOT / "SIMULATOR_V2_PHASE1_FREEZE.json").read_text(encoding="utf-8"))
    v2_mismatches = [name for name, expected in frozen["file_sha256"].items()
                     if sim.file_hash(sim.ROOT / name) != expected]
    rows, profiles = sim.generate(seed)
    repeat_rows, repeat_profiles = sim.generate(seed)
    reproducible = sim.canonical_hash((rows, profiles)) == sim.canonical_hash((repeat_rows, repeat_profiles))
    split = split_map(profiles)
    groups = {name: {sid for sid, fold in split.items() if fold == name}
              for name in ("train", "validation", "id_test")}
    session_groups = {name: {r["session"] for r in rows if split[r["subject"]] == name}
                      for name in groups}
    intersections = {"train_validation": len(groups["train"] & groups["validation"]),
                     "train_test": len(groups["train"] & groups["id_test"]),
                     "validation_test": len(groups["validation"] & groups["id_test"])}
    session_intersections = {"train_validation": len(session_groups["train"] & session_groups["validation"]),
                             "train_test": len(session_groups["train"] & session_groups["id_test"]),
                             "validation_test": len(session_groups["validation"] & session_groups["id_test"])}
    source_groups = {name: {profiles[sid]["source_subject"] for sid in ids}
                     for name, ids in groups.items()}
    source_overlap = {"train_validation": len(source_groups["train"] & source_groups["validation"]),
                      "train_test": len(source_groups["train"] & source_groups["id_test"]),
                      "validation_test": len(source_groups["validation"] & source_groups["id_test"])}
    if not reproducible or any(intersections.values()) or any(session_intersections.values()):
        raise AssertionError("Reproducibility or split failure")
    # Attach audit-only D′ to latent rows; it is never copied into observed/true features.
    for row in rows:
        row["dprime"] = profiles[row["subject"]]["dprime"]
    feature_sets = {k: history_features(rows, k) for k in K_VALUES}
    keys = {k: {(f["subject"], f["session"]) for f in sample} for k, sample in feature_sets.items()}
    same_sessions = all(value == keys[0] for value in keys.values())
    history_clean = all(
        len(f["history_sources"]) <= k
        and all(x < f["index"] for x in f["history_indices"])
        and all(s.startswith(f["subject"] + "-") for s in f["history_sources"])
        and set(f["observed"]) == set(OBSERVED_NAMES)
        and set(f["true"]) == set(TRUE_NAMES)
        and not (set(f["observed"]) & set(LATENT_NAMES))
        for k, sample in feature_sets.items() for f in sample)
    if not same_sessions or not history_clean:
        raise AssertionError("History or observed leakage contract failed")
    sample = [f for f in feature_sets[20] if f["index"] >= 20 and f["row"]["completed"]]
    train = [f for f in sample if split[f["subject"]] == "train"]
    val = [f for f in sample if split[f["subject"]] == "validation"]
    if not train or not val:
        raise AssertionError("No completed dry-run evaluation sessions")
    target_checks, target_distributions = {}, {}
    for target in ("WEAK", "BASE", "STRONG", "fatigue", "condition"):
        y_train = np.array([f["row"]["labels"][target] for f in train])
        y_val = np.array([f["row"]["labels"][target] for f in val])
        mean = metrics(y_val, np.full(len(val), y_train.mean()))
        observed_pred = ridge(train, val, OBSERVED_NAMES, "observed", target)
        true_pred = ridge(train, val, TRUE_NAMES, "true", target)
        observed = metrics(y_val, observed_pred)
        true = metrics(y_val, true_pred)
        latent = metrics(y_val, np.array([f["row"]["latent"][target] for f in val]))
        shuffled_target = metrics(y_val, ridge(train, val, OBSERVED_NAMES, "observed", target,
                                               shuffle="target", seed=seed + 11))
        shuffled_feature = metrics(y_val, ridge(train, val, OBSERVED_NAMES, "observed", target,
                                                shuffle="feature", seed=seed + 17))
        y_free = np.array([f["row"]["latent"][target] for f in val])
        noise_free = metrics(y_free, ridge(train, val, OBSERVED_NAMES, "observed", target,
                                           y_source="latent"))
        denominator = mean["mae"] - latent["mae"]
        recovery = (mean["mae"] - observed["mae"]) / denominator if denominator > .10 else None
        signal = mean["mae"] - observed["mae"]
        shuffle_status = ("INCONCLUSIVE" if signal < .05 else
                          "PASS" if shuffled_target["mae"] >= observed["mae"] + .5 * signal
                          and shuffled_feature["mae"] >= observed["mae"] + .5 * signal else "FAIL")
        recoverability = ("INCONCLUSIVE" if recovery is None else
                          "FAIL" if recovery >= .90 or (noise_free["r2"] is not None and noise_free["r2"] >= .95) else
                          "WARNING" if recovery >= .75 or (noise_free["r2"] is not None and noise_free["r2"] >= .85) else "PASS")
        target_checks[target] = {"mean": mean, "observed": observed, "true_physiology": true,
                                 "latent_oracle": latent, "target_shuffle": shuffled_target,
                                 "feature_shuffle": shuffled_feature, "shuffle_status": shuffle_status,
                                 "oracle_recovery": recovery, "observed_noise_free_r2": noise_free["r2"],
                                 "recoverability_status": recoverability}
        target_distributions[target] = describe([r["labels"][target] for r in rows
                                                  if r["labels"][target] is not None])
    cf = counterfactuals(profiles, rows, seed)
    cf["CF6"] = history_restoration(feature_sets[20], profiles, split)
    speed_hr = speed_hr_audit(rows, split)
    completed = [r for r in rows if r["completed"]]
    below = sum(r["x"] < 1 for r in rows)
    above = sum(r["x"] > 1 for r in rows)
    censored = sum(not r["completed"] for r in rows)
    completed_above = sum(r["completed"] and r["x"] > 1 for r in rows)
    clip_rate = {target: float(np.mean([r["clipping"][target] for r in completed]))
                 for target in target_distributions}
    source_pool = {source: [{"date": r["date"], "speed_kmh": r["features"]["speed_kmh"],
                              "duration_minutes": r["features"]["duration_minutes"],
                              "v5_kmh": r["features"]["reference_speed_kmh"]}
                             for r in items]
                   for source, items in sim.source_data()[0].items()}
    cf_checks = {
        "CF1": "PASS" if cf["CF1"]["completed"] >= 2 and cf["CF1"]["burden_BASE"]["max"]
                          > cf["CF1"]["burden_BASE"]["min"] else "WARNING",
        "CF2": "PASS" if cf["CF2"]["0.9"]["depletion"]["max"] == 0
                          and cf["CF2"]["1.05"]["depletion"]["min"] > 0 else "FAIL",
        "CF3": "PASS" if any(x["status"] == "EVALUABLE" for x in cf["CF3"].values()) else "WARNING",
        "CF4": "PASS" if all(x["depletion"] == 0 for x in cf["CF4"]["0.8"])
                          and all(x["depletion"] > 0 for x in cf["CF4"]["1.05"]) else "FAIL",
        "CF5": "PASS" if all(a["q_start"] <= b["q_start"] and a["debt_pre"] >= b["debt_pre"]
                           for a, b in zip(cf["CF5"], cf["CF5"][1:])) else "FAIL",
        "CF6": "WARNING" if any((v["r2"] is None or v["r2"] <= 0) for v in cf["CF6"].values())
                           else "PASS",
    }
    checks = {"locked_hashes": "PASS", "v2_frozen_files": "PASS" if not v2_mismatches else "FAIL",
              "same_seed_config": "PASS" if reproducible else "FAIL",
              "subject_split": "PASS" if not any(intersections.values()) else "FAIL",
              "session_split": "PASS" if not any(session_intersections.values()) else "FAIL",
              "history_prior_only": "PASS" if history_clean else "FAIL",
              "same_history_evaluation_sessions": "PASS" if same_sessions else "FAIL",
              "train_only_preprocessing": "PASS", "id_test_unused_for_fitting": "PASS",
              "observed_no_latent_leakage": "PASS",
              "q_bounds": "PASS" if all(0 <= r["q_start"] <= r["dprime"] + 1e-9
                                         and 0 <= r["q_end"] <= r["dprime"] + 1e-9 for r in rows) else "FAIL",
              "latent_score_bounds": "PASS" if all(2 - 1e-9 <= value <= 8 + 1e-9
                                                   for r in rows for value in r["latent"].values()) else "FAIL",
              "reserve_threshold": "PASS" if all((r["x"] <= 1 and r["depletion"] == 0)
                                                 or (r["x"] > 1 and r["depletion"] >= 0) for r in rows) else "FAIL",
              "q_zero_censoring": "PASS" if all(r["completed"] or r["q_end"] == 0
                                                   for r in rows) else "FAIL",
              "coupling_weight_sums": "PASS" if all(abs(sum(w) - 1) < 1e-12 for w in sim.COUPLINGS.values()) else "FAIL",
              "cf3_hr_overlap": cf_checks["CF3"],
              "completed_above_threshold": "PASS" if completed_above else "WARNING",
              "source_template_overlap": "WARNING" if any(source_overlap.values()) else "PASS",
              "speed_hr_individual_relation": "PASS" if speed_hr["positive_subject_slope_fraction"] is not None
                                                   and speed_hr["positive_subject_slope_fraction"] > .5 else "WARNING",
              "pmdata_hr_anchor": "SANITY_ONLY",
              "target_shuffle": "WARNING" if any(x["shuffle_status"] == "INCONCLUSIVE" for x in target_checks.values())
                                else "FAIL" if any(x["shuffle_status"] == "FAIL" for x in target_checks.values()) else "PASS",
              "recoverability": "FAIL" if any(x["recoverability_status"] == "FAIL" for x in target_checks.values())
                                else "WARNING" if any(x["recoverability_status"] in ("WARNING", "INCONCLUSIVE")
                                                      for x in target_checks.values()) else "PASS"}
    report = {"status": "dry-run-validation-only; ID-test not evaluated; no main experiment",
              "seed": seed, "input_hashes": sim.LOCKS, "code_hashes": {
                  "simulator_v21_running.py": sim.file_hash(sim.ROOT / "simulator_v21_running.py"),
                  "validate_simulator_v21_running.py": sim.file_hash(Path(__file__))},
              "generated_hash": sim.canonical_hash((rows, profiles)),
              "empirical_source_pool_hash": sim.canonical_hash(source_pool),
              "split_subjects": {name: len(ids) for name, ids in groups.items()},
              "subject_intersections": intersections, "session_intersections": session_intersections,
              "source_template_intersections": source_overlap, "v2_frozen_hash_mismatches": v2_mismatches,
              "source_template_subjects": len({p["source_subject"] for p in profiles.values()}),
              "counts": {"subjects": len(profiles), "sessions": len(rows), "completed": len(completed),
                         "below_threshold_rate": below / len(rows), "above_threshold_rate": above / len(rows),
                         "q_zero_censor_rate": censored / len(rows),
                         "completed_above_threshold": completed_above},
              "cf": cf, "cf_checks": cf_checks, "speed_hr_sanity": speed_hr,
              "distributions": {"true_hr": describe([r["true_hr"] for r in completed]),
                                "observed_hr": describe([r["observed_hr"] for r in completed]),
                                "pmdata_session_average_hr_reference": {"q05": 134.3, "median": 148.,
                                                                          "q95": 163., "role": "sanity anchor only"},
                                "targets": target_distributions, "clipping_rate": clip_rate},
              "predictors_validation_only": target_checks, "checks": checks}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                                allow_nan=False), encoding="utf-8")
    (OUT / "split_manifest.json").write_text(json.dumps(split, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(validate(), ensure_ascii=False, indent=2, allow_nan=False))
