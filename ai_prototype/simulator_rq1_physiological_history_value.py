"""Preregistered RQ1 physiological/performance history dry-run generator.

Predictors receive current observations and strictly past observed records only.
Latent values live in a separate audit table.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

import simulator_pretask_model as pretask

ROOT = Path(__file__).resolve().parent
PARAM = ROOT / "RQ1_PHYSIOLOGICAL_HISTORY_VALUE_PARAMETERS.json"
LOCK = ROOT / "RQ1_PHYSIOLOGICAL_HISTORY_VALUE_PREREGISTRATION_LOCK.json"
AMENDMENT_LOCK = ROOT / "RQ1_PHYSIOLOGICAL_HISTORY_VALUE_AMENDMENT_01.lock.json"
CALIBRATION = ROOT / "artifacts" / "rq1_longitudinal_v2_calibration" / "calibration.json"
TASKS = tuple(pretask.TASKS)
CONDITIONS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_preregistration() -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8-sig"))
    changed = [x["path"] for x in lock["files"] if sha(ROOT / x["path"]) != x["sha256"]]
    amendment = json.loads(AMENDMENT_LOCK.read_text(encoding="utf-8-sig"))
    if sha(ROOT / amendment["amendment"]) != amendment["sha256"]:
        changed.append(amendment["amendment"])
    if changed:
        raise RuntimeError(f"locked preregistration changed: {changed}")
    pretask.verify_lock()


def _subject_group(index: int) -> tuple[str, str]:
    if index < 72:
        fold, local, size = "train", index, 24
    elif index < 96:
        fold, local, size = "validation", index - 72, 8
    else:
        fold, local, size = "test", index - 96, 8
    group = "IMPROVEMENT" if local < size else "STABLE" if local < 2 * size else "DECLINE"
    return fold, group


def _gap_distribution() -> tuple[np.ndarray, np.ndarray]:
    cal = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    counts = cal["observation_cadence_days"]["wellness"]["day_gap_counts"]
    values = np.asarray([int(x) for x in counts], dtype=int)
    weights = np.asarray(list(counts.values()), dtype=float)
    return values, weights / weights.sum()


def _draw_gap(rng: np.random.Generator, level: str, values: np.ndarray, probs: np.ndarray) -> int:
    gap = int(rng.choice(values, p=probs))
    if level == "LOW":
        return min(gap, 3)
    if level == "HIGH":
        return min(gap * 3, 45)
    return gap


def generate(seed: int = 110, dataset: str = "NATURALISTIC", sensitivity: str = "BASE") -> dict:
    verify_preregistration()
    if dataset not in {"NATURALISTIC", "CONTROLLED_CHANGE"}:
        raise ValueError(dataset)
    if sensitivity not in {"LOW", "BASE", "HIGH"}:
        raise ValueError(sensitivity)

    p = json.loads(PARAM.read_text(encoding="utf-8"))
    old = json.loads(pretask.PARAM.read_text(encoding="utf-8"))
    gap_values, gap_probs = _gap_distribution()
    n_cal, n_eval = p["sessions"]["calibration"], p["sessions"]["evaluation"]
    observed, audit, profiles = [], [], []
    ms = p["physiology_and_measurement"]["measurement_sensitivity"][sensitivity]
    response_sd = p["subject_heterogeneity"]["physiological_response_sd_bpm"][sensitivity]
    recovery_sd = p["subject_heterogeneity"]["recovery_individual_log_sd"][sensitivity]
    report = p["reporting_process_secondary_only"]
    state = p["latent_state_and_task_outcome"]

    for index in range(p["subjects"]["total"]):
        sid = f"PHV-{index + 1:03d}"
        fold, change_group = _subject_group(index)
        rng_seed = int(hashlib.sha256(f"{seed}|{dataset}|{sid}".encode()).hexdigest()[:16], 16)
        rng = np.random.default_rng(rng_seed)
        common = float(rng.normal())
        capacities = {}
        rho = old["subject"]["cross_task_capacity_correlation"]
        for task in TASKS:
            z = rho * common + math.sqrt(1 - rho * rho) * float(rng.normal())
            capacities[task] = float(math.exp(old["subject"]["capacity_log_sd"] * z))
        tolerance = float(rng.lognormal(old["subject"]["tolerance_minutes_log_mean"], old["subject"]["tolerance_minutes_log_sd"]))
        tau_fast = float(p["subject_heterogeneity"]["fast_recovery_time_constant_minutes"][sensitivity] * rng.lognormal(0, recovery_sd))
        tau_slow = float(p["subject_heterogeneity"]["slow_recovery_time_constant_hours"][sensitivity] * rng.lognormal(0, recovery_sd))
        hr_base = float(rng.normal(p["physiology_and_measurement"]["resting_hr_mean_bpm"], p["physiology_and_measurement"]["resting_hr_between_subject_sd_bpm"]))
        temp_base = float(rng.normal(p["physiology_and_measurement"]["temperature_mean_c"], p["physiology_and_measurement"]["temperature_between_subject_sd_c"]))
        spo2_base = float(np.clip(rng.normal(p["physiology_and_measurement"]["spo2_mean_pct"], p["physiology_and_measurement"]["spo2_between_subject_sd_pct"]), 94, 99.5))
        task_hr_delta = {task: float(rng.normal(0, response_sd)) for task in TASKS}
        slopes = {name: float(rng.lognormal(0, old["subject"]["perception_slope_log_sd"])) for name in ("fatigue", "condition", "burden")}
        stable_bias = {name: float(rng.normal(0, report["stable_bias_sd_points"][sensitivity])) for name in slopes}
        drift = {name: 0.0 for name in slopes}
        shift = {name: 0.0 for name in slopes}
        anchor = float(np.clip(1.0 + 0.55 * common + rng.normal(0, 0.20), 0.35, 2.2))
        profiles.append({
            "subject_id": sid,
            "fold": fold,
            "change_group": change_group,
            "observed_anchor": anchor,
            "capacity": capacities,
            "tolerance_minutes": tolerance,
            "tau_fast_minutes": tau_fast,
            "tau_slow_hours": tau_slow,
            "hr_baseline": hr_base,
            "temperature_baseline": temp_base,
            "spo2_baseline": spo2_base,
            "task_hr_response_delta": task_hr_delta,
            "reporting_bias": stable_bias,
        })

        debt, log_capacity_change, day = 0.0, 0.0, 0
        for j in range(n_cal + n_eval):
            gap_days = _draw_gap(rng, sensitivity, gap_values, gap_probs)
            day += gap_days
            if dataset == "NATURALISTIC":
                dyn = p["datasets"]["NATURALISTIC"]["capacity_dynamics_per_30_days"][sensitivity]
                log_capacity_change += float(rng.normal(0, dyn["continuous_change_sd"] * math.sqrt(gap_days / 30)))
                event = rng.random() < 1 - (1 - dyn["event_probability"]) ** (gap_days / 30)
                if event:
                    log_capacity_change += float(rng.normal(0, dyn["event_magnitude_sd"]))
            else:
                dyn_sd = p["datasets"]["CONTROLLED_CHANGE"]["continuous_change_sd_per_30_days"][sensitivity]
                log_capacity_change += float(rng.normal(0, dyn_sd * math.sqrt(gap_days / 30)))
                event = j == n_cal and change_group != "STABLE"
                if event:
                    sign = 1 if change_group == "IMPROVEMENT" else -1
                    log_capacity_change += sign * p["datasets"]["CONTROLLED_CHANGE"]["signed_log_capacity_shift"][sensitivity]

            for target in ("fatigue", "condition", "burden"):
                drift[target] += float(rng.normal(0, report["drift_sd_per_30_days"][sensitivity] * math.sqrt(gap_days / 30)))
                prob = report["shift_probability_per_30_days"][sensitivity]
                if rng.random() < 1 - (1 - prob) ** (gap_days / 30):
                    shift[target] += float(rng.normal(0, report["shift_sd_points"][sensitivity]))

            debt_pre = float(debt * math.exp(-24 * gap_days / tau_slow))
            sleep = float(np.clip(rng.beta(2, 5), 0, 1))
            stress = float(np.clip(rng.beta(2, 4), 0, 1))
            unobserved = float(np.clip(0.5 + rng.normal(0, state["session_unobserved_sd"]), 0, 1))
            wstate = state["pretask_state_weights"]
            pre_fatigue_latent = float(np.clip(wstate["debt"] * debt_pre + wstate["sleep"] * sleep + wstate["stress"] * stress + wstate["unobserved"] * unobserved, 0, 1))

            true_hr = hr_base + old["physiology"]["fatigue_hr_gain_bpm"] * pre_fatigue_latent + old["physiology"]["stress_hr_gain_bpm"] * stress + rng.normal(0, 1.3)
            true_temp = temp_base + 0.25 * pre_fatigue_latent + 0.10 * stress + rng.normal(0, 0.04)
            true_spo2 = float(np.clip(spo2_base - 0.5 * pre_fatigue_latent + rng.normal(0, 0.15), 90, 99.8))
            hr, q_hr, m_hr, a_hr = pretask._measure(rng, true_hr, ms["hr_sd_bpm"], ms["missing_probability"], ms["artifact_probability"], 3, (25, 240))
            temp, q_temp, m_temp, a_temp = pretask._measure(rng, true_temp, ms["temperature_sd_c"], ms["missing_probability"], ms["artifact_probability"], 4, (30, 43))
            spo2, q_spo2, m_spo2, a_spo2 = pretask._measure(rng, true_spo2, ms["spo2_sd_pct"], ms["missing_probability"], ms["artifact_probability"], 4, (70, 100))

            fatigue_score, fatigue_noiseless = pretask._report(rng, pre_fatigue_latent, slopes["fatigue"], stable_bias["fatigue"], drift["fatigue"] + shift["fatigue"], report["session_noise_sd_points"][sensitivity], True)
            condition_score, condition_noiseless = pretask._report(rng, pre_fatigue_latent, slopes["condition"], stable_bias["condition"], drift["condition"] + shift["condition"], report["session_noise_sd_points"][sensitivity], False)

            task = TASKS[(j + index) % len(TASKS)]
            demand_levels = p["task_design"]["planned_demand_levels"]
            durations = p["task_design"]["planned_duration_minutes"]
            planned_level = float(demand_levels[(j * 3 + index) % len(demand_levels)])
            planned_duration = float(durations[(j * 5 + index) % len(durations)])
            external_demand = planned_level * anchor
            effective_capacity = capacities[task] * math.exp(log_capacity_change) * (1 - state["fatigue_capacity_penalty"] * pre_fatigue_latent)
            relative = float(external_demand / max(effective_capacity, 0.05))
            latent_limit = math.inf if relative <= state["relative_demand_threshold"] else tolerance / max(relative - state["relative_demand_threshold"], 0.02)
            behavioral_multiplier = float(rng.lognormal(0, state["behavioral_stop_log_sd"]))
            actual = planned_duration if math.isinf(latent_limit) else min(planned_duration, latent_limit * behavioral_multiplier)
            completed = bool(actual >= planned_duration - 1e-9)
            depletion = float(np.clip(max(relative - 1, 0) * actual / max(tolerance, 1), 0, 1))
            duration_term = actual / max(durations)
            outcome_unobserved = float(rng.uniform(0, 1))
            wb = state["post_burden_weights"]
            burden_latent = float(np.clip(wb["relative_demand"] * np.clip(relative / 1.8, 0, 1) + wb["duration"] * duration_term + wb["pre_fatigue"] * pre_fatigue_latent + wb["depletion"] * depletion + wb["unobserved"] * outcome_unobserved, 0, 1))
            burden_score, burden_noiseless = pretask._report(rng, burden_latent, slopes["burden"], stable_bias["burden"], drift["burden"] + shift["burden"], report["session_noise_sd_points"][sensitivity], True)
            recovery_delay = float(max(0, state["recovery_delay_base_hours"] + state["recovery_delay_burden_gain_hours"] * burden_latent * (tau_slow / 24) + rng.normal(0, 1.2)))
            debt = float(np.clip(debt_pre + 0.45 * burden_latent + 0.25 * depletion, 0, 1))

            true_post_hr = float(true_hr + (45 + task_hr_delta[task]) * burden_latent)
            true_recovery_hr = float(hr_base + (true_post_hr - hr_base) * math.exp(-10 / tau_fast) + 12 * debt)
            post_hr, q_post, m_post, a_post = pretask._measure(rng, true_post_hr, ms["hr_sd_bpm"], ms["missing_probability"], ms["artifact_probability"], 3, (25, 240))
            recovery_hr, q_recovery, m_recovery, a_recovery = pretask._measure(rng, true_recovery_hr, ms["hr_sd_bpm"], ms["missing_probability"], ms["artifact_probability"], 3, (25, 240))

            session_id = f"{dataset[:3]}-{seed}-{sid}-{j:03d}"
            observed.append({
                "session_id": session_id,
                "subject_id": sid,
                "fold": fold,
                "session_index": j,
                "day": day,
                "phase": "calibration" if j < n_cal else "evaluation",
                "task_type": task,
                "planned_demand": planned_level,
                "external_demand": external_demand,
                "planned_duration_min": planned_duration,
                "observed_anchor": anchor,
                "gap_days": gap_days,
                "current_hr_bpm": hr,
                "current_temperature_c": temp,
                "current_spo2_pct": spo2,
                "quality_hr": q_hr,
                "quality_temperature": q_temp,
                "quality_spo2": q_spo2,
                "targets": {
                    "pre_fatigue": fatigue_score,
                    "pre_condition": condition_score,
                    "completed": int(completed),
                    "stop_time_min": None if completed else float(actual),
                    "post_burden": burden_score,
                    "recovery_delay_h": recovery_delay,
                },
                "history_observable": {
                    "actual_duration_min": float(actual),
                    "completed": int(completed),
                    "observed_stop_time_min": None if completed else float(actual),
                    "recovery_delay_h": recovery_delay,
                    "post_hr_bpm": post_hr,
                    "post_hr_quality": q_post,
                    "recovery_hr_bpm": recovery_hr,
                    "recovery_hr_quality": q_recovery,
                    "recovery_measurement_min": 10.0,
                    "pre_fatigue": fatigue_score,
                    "pre_condition": condition_score,
                    "post_burden": burden_score,
                },
            })
            audit.append({
                "session_id": session_id,
                "subject_id": sid,
                "fold": fold,
                "change_group": change_group,
                "capacity_event": bool(event),
                "capacity_log_change": float(log_capacity_change),
                "effective_capacity": float(effective_capacity),
                "relative_demand": relative,
                "tolerance_minutes": tolerance,
                "debt_pre": debt_pre,
                "depletion": depletion,
                "pre_fatigue_latent": pre_fatigue_latent,
                "post_burden_latent": burden_latent,
                "fatigue_noiseless": fatigue_noiseless,
                "condition_noiseless": condition_noiseless,
                "burden_noiseless": burden_noiseless,
                "true_hr_bpm": float(true_hr),
                "true_temperature_c": float(true_temp),
                "true_spo2_pct": float(true_spo2),
                "true_post_hr_bpm": true_post_hr,
                "true_recovery_hr_bpm": true_recovery_hr,
                "current_missing_count": int(m_hr) + int(m_temp) + int(m_spo2),
                "current_artifact_count": int(a_hr) + int(a_temp) + int(a_spo2),
                "history_hr_missing_count": int(m_post) + int(m_recovery),
                "history_hr_artifact_count": int(a_post) + int(a_recovery),
                "post_recovery_measurement_applied": True,
            })

    return {
        "seed": seed,
        "dataset": dataset,
        "sensitivity": sensitivity,
        "observed": observed,
        "audit": audit,
        "profiles_audit_only": profiles,
        "parameter_sha256": sha(PARAM),
        "preregistration_lock_sha256": sha(LOCK),
        "amendment_sha256": sha(ROOT / json.loads(AMENDMENT_LOCK.read_text(encoding="utf-8-sig"))["amendment"]),
    }


def _stats(out: dict, name: str, values: list[float | int | None]) -> None:
    clean = [float(x) for x in values if x is not None]
    out[f"hist_{name}_mean"] = float(np.mean(clean)) if clean else None
    out[f"hist_{name}_sd"] = float(np.std(clean)) if len(clean) > 1 else None
    out[f"hist_{name}_last"] = clean[-1] if clean else None
    out[f"hist_{name}_n"] = len(clean)


def history_rows(data: dict, condition: str, k: int) -> list[dict]:
    if condition not in CONDITIONS:
        raise ValueError(condition)
    audit_by_id = {x["session_id"]: x for x in data["audit"]}
    by_subject: dict[str, list[dict]] = {}
    for row in data["observed"]:
        by_subject.setdefault(row["subject_id"], []).append(row)
    output = []
    for rows in by_subject.values():
        rows.sort(key=lambda x: x["session_index"])
        for i, current in enumerate(rows):
            if current["phase"] != "evaluation":
                continue
            past = rows[max(0, i - k):i] if k else []
            if any(x["session_index"] >= current["session_index"] for x in past):
                raise AssertionError("current/future history leakage")
            out = {
                "session_id": current["session_id"],
                "subject_id": current["subject_id"],
                "fold": current["fold"],
                "session_index": current["session_index"],
                "task_type": current["task_type"],
                "planned_demand": current["planned_demand"],
                "external_demand": current["external_demand"],
                "planned_duration_min": current["planned_duration_min"],
                "observed_anchor": current["observed_anchor"],
                "gap_days": current["gap_days"],
                "current_hr_bpm": current["current_hr_bpm"],
                "current_temperature_c": current["current_temperature_c"],
                "current_spo2_pct": current["current_spo2_pct"],
                "quality_hr": current["quality_hr"],
                "quality_temperature": current["quality_temperature"],
                "quality_spo2": current["quality_spo2"],
                "history_n": len(past),
                "targets": current["targets"],
                "audit_targets": {
                    "pre_fatigue_latent": audit_by_id[current["session_id"]]["pre_fatigue_latent"],
                    "pre_condition_construct": 1 - audit_by_id[current["session_id"]]["pre_fatigue_latent"],
                    "post_burden_latent": audit_by_id[current["session_id"]]["post_burden_latent"],
                },
            }
            sensor = bool(past) and condition in {"C2", "C5", "C6"}
            performance = bool(past) and condition in {"C3", "C5", "C6"}
            recovery = bool(past) and condition in {"C4", "C5", "C6"}
            self_report = bool(past) and condition in {"C6", "C7"}
            if sensor:
                for field in ("current_hr_bpm", "current_temperature_c", "current_spo2_pct"):
                    _stats(out, field, [x[field] for x in past])
                _stats(out, "post_hr_bpm", [x["history_observable"]["post_hr_bpm"] for x in past])
                for task in TASKS:
                    subset = [x for x in past if x["task_type"] == task]
                    _stats(out, f"{task.lower()}_post_hr_bpm", [x["history_observable"]["post_hr_bpm"] for x in subset])
            if performance:
                for field in ("actual_duration_min", "completed", "observed_stop_time_min"):
                    _stats(out, field, [x["history_observable"][field] for x in past])
                for task in TASKS:
                    subset = [x for x in past if x["task_type"] == task]
                    _stats(out, f"{task.lower()}_completion", [x["history_observable"]["completed"] for x in subset])
                    _stats(out, f"{task.lower()}_duration", [x["history_observable"]["actual_duration_min"] for x in subset])
            if recovery:
                _stats(out, "recovery_delay_h", [x["history_observable"]["recovery_delay_h"] for x in past])
                _stats(out, "recovery_hr_bpm", [x["history_observable"]["recovery_hr_bpm"] for x in past])
                changes = []
                for x in past:
                    post = x["history_observable"]["post_hr_bpm"]
                    rec = x["history_observable"]["recovery_hr_bpm"]
                    changes.append(None if post is None or rec is None else post - rec)
                _stats(out, "ten_min_hr_recovery", changes)
            if self_report:
                for field in ("pre_fatigue", "pre_condition", "post_burden"):
                    _stats(out, field, [x["history_observable"][field] for x in past])
            forbidden = ("capacity", "tolerance", "reserve", "debt", "strain", "latent", "true_", "reporting_bias", "noiseless")
            feature_keys = [x for x in out if x not in {"targets", "audit_targets"}]
            if any(any(token in key for token in forbidden) for key in feature_keys):
                raise AssertionError("latent key in predictor feature")
            output.append(out)
    return output


if __name__ == "__main__":
    sample = generate()
    rows = history_rows(sample, "C5", 20)
    print(json.dumps({"observed_rows": len(sample["observed"]), "evaluation_rows": len(rows), "subjects": len(sample["profiles_audit_only"])}, indent=2))
