"""Locked RQ1 longitudinal v2-minimal generator. No model experiment here."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from openpyxl import load_workbook

import simulator_rq1_state_mixture as state
import simulator_v22_multi_activity as v22
import simulator_v23_task_capacity as v23


ROOT = Path(__file__).resolve().parent
PARAM = ROOT / "RQ1_LONGITUDINAL_V2_FINAL_PARAMETERS.json"
CAL = ROOT / "artifacts" / "rq1_longitudinal_v2_calibration" / "calibration.json"
BASE_CAL = ROOT / "artifacts" / "simulator_v2_calibration_v1" / "calibration.json"
LOCK = ROOT / "RQ1_LONGITUDINAL_V2_IMPLEMENTATION_LOCK.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_lock() -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    changed = [x["path"] for x in lock["files"]
               if _sha(ROOT / x["path"]) != x["sha256"]]
    if changed:
        raise RuntimeError(f"locked input changed: {changed}")


def _v5_values() -> list[float]:
    source = ROOT / "data" / "pmdata" / "participant-overview.xlsx"
    cal = json.loads(CAL.read_text(encoding="utf-8"))
    if _sha(source) != cal["source"]["participant_overview_sha256"]:
        raise RuntimeError("PMData participant overview changed")
    rows = list(load_workbook(source, data_only=True).active.values)[2:]
    values = []
    for row in rows:
        try:
            minutes = float(row[7]) + float(row[8]) / 60
            values.append(300 / minutes)  # 5 km in km/h
        except (TypeError, ValueError):
            pass
    if len(values) != 15:
        raise RuntimeError("expected 15 valid independent 5 km records")
    return values


def _gap_values() -> tuple[np.ndarray, np.ndarray]:
    counts = json.loads(CAL.read_text(encoding="utf-8"))["observation_cadence_days"]["wellness"]["day_gap_counts"]
    days = np.array([int(x) for x in counts], dtype=int)
    probs = np.array([counts[str(x)] for x in days], dtype=float)
    return days, probs / probs.sum()


def _draw_gap(rng: np.random.Generator, sensitivity: str, days: np.ndarray, probs: np.ndarray) -> int:
    value = int(rng.choice(days, p=probs))
    if sensitivity == "LOW":
        return min(value, 3)
    if sensitivity == "HIGH":
        return min(value * 3, 45)
    return value


def _score(z: float, bias: float, noise: float) -> tuple[float, float, bool]:
    noiseless = float(np.clip(2 + 6 * z, 0, 10))
    observed = float(np.clip(noiseless + bias + noise, 0, 10))
    return noiseless, observed, observed in (0.0, 10.0)


def generate(seed: int = 110, sensitivity: str = "BASE") -> dict:
    verify_lock()
    p = json.loads(PARAM.read_text(encoding="utf-8"))
    old = json.loads(v22.PARAM_PATH.read_text(encoding="utf-8"))
    base_cal = json.loads(BASE_CAL.read_text(encoding="utf-8"))
    baselines = [x["median_bpm"] for x in base_cal["parameters"]["P01"]["subjects"].values()]
    aerobic_reference = v23._aerobic_reference()
    v5_pool, (gap_days, gap_probs) = _v5_values(), _gap_values()
    rng = np.random.default_rng(seed)
    observed, audit, profiles = [], [], []
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    target_names = ("burden_WEAK", "burden_BASE", "burden_STRONG", "fatigue", "condition")
    n_sessions = max(p["history_lengths"]) + p["target_evaluation_events_per_subject"]

    for index in range(p["subjects"]["total"]):
        sid = f"RQ1V2-{index + 1:03d}"
        fold = "train" if index < 72 else "validation" if index < 96 else "test"
        prng = np.random.default_rng(int(hashlib.sha256(f"{seed}|{sid}|profile".encode()).hexdigest()[:16], 16))
        v5 = float(prng.choice(v5_pool))
        aerobic = float(prng.choice(aerobic_reference))
        tc = p["task_capacity"]
        shared, task_sd, corr = tc["shared_aerobic_loading"][sensitivity], tc["task_specific_log_sd"][sensitivity], tc["cross_task_residual_correlation"][sensitivity]
        za, zl = float(prng.normal()), float(prng.normal())
        zc = float(corr * zl + math.sqrt(1 - corr**2) * prng.normal())
        base_capacity = {
            "AEROBIC": aerobic,
            "LOADED_MOVEMENT": math.exp(shared * math.log(aerobic) + task_sd * zl),
            "BODYWEIGHT_CIRCUIT": math.exp(shared * math.log(aerobic) + task_sd * zc),
        }
        tol_sd = {"LOW": .15, "BASE": .30, "HIGH": .45}[sensitivity]
        tol_corr = {"LOW": 0.0, "BASE": .25, "HIGH": .50}[sensitivity]
        zs = {"AEROBIC": za, "LOADED_MOVEMENT": zl, "BODYWEIGHT_CIRCUIT": zc}
        tolerance = {a: math.exp(tol_sd * (tol_corr * z + math.sqrt(1 - tol_corr**2) * prng.normal())) for a, z in zs.items()}
        base_subject = state._subject(prng, index + 1, fold)
        hr_baseline = float(prng.choice(baselines))
        response = {a: float(prng.normal(0, p["physiology"]["subject_response_sd_bpm"][sensitivity])) for a in base_capacity}
        stable_bias = {t: float(prng.normal(0, p["reporting_process"][sensitivity]["stable_bias_sd"])) for t in target_names}
        drift = {t: 0.0 for t in target_names}
        shift = {t: 0.0 for t in target_names}
        reserve = {a: 1.0 for a in base_capacity}
        debt, capacity_log_change = 0.0, 0.0
        timestamp = start + timedelta(minutes=index)
        previous_end = timestamp
        profile = {"subject_id": sid, "fold": fold, "v5_kmh": v5, "initial_aerobic_reference": aerobic,
                   "base_capacity": base_capacity, "tolerance": tolerance, "hr_baseline": hr_baseline,
                   "temp_baseline": base_subject.temp_baseline, "spo2_baseline": base_subject.spo2_baseline,
                   "hr_response_delta": response, "stable_reporting_bias": stable_bias}
        profiles.append(profile)

        for seq in range(1, n_sessions + 1):
            gap = _draw_gap(rng, sensitivity, gap_days, gap_probs)
            timestamp += timedelta(days=gap)
            dyn = p["capacity_dynamics_per_30_days"][sensitivity]
            capacity_log_change += float(rng.normal(0, dyn["continuous_change_sd"] * math.sqrt(gap / 30)))
            if rng.random() < 1 - (1 - dyn["event_probability"]) ** (gap / 30):
                capacity_log_change += float(rng.normal(0, dyn["event_magnitude_sd"]))
            rp = p["reporting_process"][sensitivity]
            for target in target_names:
                drift[target] += float(rng.normal(0, rp["drift_sd_per_30_days"] * math.sqrt(gap / 30)))
                if rng.random() < 1 - (1 - rp["shift_probability_per_30_days"]) ** (gap / 30):
                    shift[target] += float(rng.normal(0, rp["shift_sd"]))

            activity = str(rng.choice(p["activity_support_design"]["categories"], p=p["activity_support_design"]["probabilities"]))
            duration, demand, workload = 0.0, 0.0, {"kind": "none"}
            if activity == "AEROBIC":
                u = float(rng.choice(p["aerobic_activity"]["external_demand_multipliers_of_v5"]))
                duration = float(rng.choice(p["aerobic_activity"]["duration_minutes"]))
                demand, workload = u, {"kind": "aerobic", "u_v5": u, "speed_kmh": u * v5}
                ref, half = 44.85, 44.85
            elif activity == "LOADED_MOVEMENT":
                row = old["loaded_march"]["calibration"][int(rng.integers(len(old["loaded_march"]["calibration"])))]
                duration, demand = float(row[4]), v22._march_demand(row, old["loaded_march"], sensitivity.lower())
                workload = {"kind": "loaded_movement", "speed_kmh": row[1], "load_ratio": row[2], "grade_pct": row[3]}
                ref, half = old["loaded_march"]["reference_duration_min"], old["loaded_march"]["half_duration_min"]
            elif activity == "BODYWEIGHT_CIRCUIT":
                row = old["bodyweight_circuit"]["calibration"][int(rng.integers(len(old["bodyweight_circuit"]["calibration"])))]
                duration, demand = float(row[3]), v22._circuit_demand(row, old["bodyweight_circuit"], sensitivity.lower())
                workload = {"kind": "bodyweight_circuit", "work_sec": row[1], "rest_sec": row[2]}
                ref, half = old["bodyweight_circuit"]["duration_reference_min"], old["bodyweight_circuit"]["half_duration_min"]
            else:
                ref = half = 1.0

            capacity = base_capacity.get(activity, 1.0) * math.exp(capacity_log_change)
            relative = demand / capacity if activity != "NONE" else 0.0
            tau_fast = p["recovery"]["fast_time_constant_minutes"][sensitivity]
            for name in reserve:
                reserve[name] = 1 - (1 - reserve[name]) * math.exp(-(gap * 1440) / tau_fast)
            tau_slow = p["recovery"]["slow_time_constant_hours"][sensitivity]
            debt_pre = debt * math.exp(-(gap * 24) / tau_slow)
            reserve_pre = reserve.get(activity, 1.0)
            rate = max(relative - 1.0, 0.0) / (ref * tolerance.get(activity, 1.0))
            actual = duration if rate == 0 or rate * duration <= reserve_pre else max(1 / 60, reserve_pre / rate)
            completed = bool(actual >= duration - 1e-12)
            depletion = min(reserve_pre, rate * actual)
            reserve_after = max(0.0, reserve_pre - depletion)
            if activity != "NONE":
                reserve[activity] = reserve_after
            rterm = relative / (1 + relative) if relative > 0 else 0.0
            dterm = actual / (actual + half) if actual > 0 else 0.0
            u_phys, u_burden, u_wellness = (float(x) for x in rng.normal(0, .12, 3))
            sw = p["latent_state"]["strain_weights_relative_duration_depletion_debt_unobserved"]
            strain = float(np.clip(sum(w*x for w, x in zip(sw, (rterm, dterm, depletion, debt_pre, u_phys))), 0, 1))
            exposure = relative * actual / ref if activity != "NONE" else 0.0
            debt = float(np.clip(1 - (1 - debt_pre) * math.exp(-p["latent_state"]["slow_debt_gain"][sensitivity] * exposure), 0, 1))

            phys_sd = p["physiology"]["physiology_sd_bpm"][sensitivity]
            true_hr = hr_baseline + (p["physiology"]["hr_gain_bpm"][sensitivity] + response.get(activity, 0.0)) * rterm + 5 * debt_pre + float(rng.normal(0, phys_sd))
            true_temp = base_subject.temp_baseline + .28 * rterm + float(rng.normal(0, .08))
            true_spo2 = base_subject.spo2_baseline - .25 * rterm + float(rng.normal(0, .20))
            artifact = bool(rng.random() < p["measurement_process"]["artifact_probability"])
            hr, hq, ha = state._measure(rng, true_hr, p["measurement_process"]["hr_sd_bpm"], 20, 250, artifact, "hr")
            temp, tq, ta = state._measure(rng, true_temp, p["measurement_process"]["temperature_sd_c"], 20, 45, artifact, "temp")
            spo2, sq, sa = state._measure(rng, true_spo2, p["measurement_process"]["spo2_sd_pct"], 50, 100, artifact, "spo2")
            for name in ("hr", "temp", "spo2"):
                if rng.random() < p["measurement_process"]["missing_probability"]:
                    if name == "hr": hr = None
                    elif name == "temp": temp = None
                    else: spo2 = None

            z = {}
            for level in ("WEAK", "BASE", "STRONG"):
                weights = p["targets"]["burden_coupling"][level]
                z[f"burden_{level}"] = sum(w*x for w, x in zip(weights, (rterm, depletion, strain, debt_pre, u_burden)))
            z["fatigue"] = sum(w*x for w, x in zip(p["targets"]["fatigue_weights"], (rterm, depletion, strain, debt_pre, u_wellness)))
            positive = float(np.clip((u_wellness + .5), 0, 1))
            z["condition"] = sum(w*x for w, x in zip(p["targets"]["condition_weights"], (1-rterm, reserve_after, 1-strain, 1-debt_pre, positive)))
            targets, noiseless, clipped = {}, {}, {}
            for target in target_names:
                if activity == "NONE" and target.startswith("burden_"):
                    targets[target] = noiseless[target] = None; clipped[target] = False; continue
                bias = stable_bias[target] + drift[target] + shift[target]
                no, obs, was_clipped = _score(z[target], bias, float(rng.normal(0, rp["session_noise_sd"])))
                targets[target], noiseless[target], clipped[target] = obs, no, was_clipped

            session_id = f"{sid}-{seq:03d}"
            observed.append({
                "subject_id": sid, "session_id": session_id, "fold": fold, "sequence": seq,
                "timestamp": timestamp.isoformat(), "activity_type": activity, "workload": workload,
                "planned_duration_min": duration, "actual_duration_min": float(actual), "completed": completed,
                "recovery_interval_days": gap, "v5_kmh": v5,
                "hr_bpm": hr, "hr_quality": hq, "temperature_c": temp, "temperature_quality": tq,
                "spo2_pct": spo2, "spo2_quality": sq, "measurement_issue": int(bool(ha or ta or sa)),
                "targets": targets, "target_clipped": clipped,
            })
            audit.append({
                "subject_id": sid, "session_id": session_id, "fold": fold, "sequence": seq,
                "timestamp": timestamp.isoformat(), "activity_type": activity, "capacity": capacity,
                "capacity_log_change": capacity_log_change, "relative_demand": relative, "reserve_pre": reserve_pre,
                "reserve_depletion": depletion, "reserve_after": reserve_after, "debt_pre": debt_pre,
                "debt_after": debt, "strain": strain, "true_hr_bpm": float(true_hr),
                "true_temperature_c": float(true_temp), "true_spo2_pct": float(true_spo2),
                "reporting_bias": {t: stable_bias[t] + drift[t] + shift[t] for t in target_names},
                "noiseless_targets": noiseless, "u_phys": u_phys, "u_burden": u_burden, "u_wellness": u_wellness,
            })
            previous_end = timestamp + timedelta(minutes=actual)
        
    return {"seed": seed, "sensitivity": sensitivity, "observed": observed, "audit": audit, "profiles_audit_only": profiles}


def history_features(data: dict, k: int, evaluation_only: bool = True) -> list[dict]:
    audit_by_id = {r["session_id"]: r for r in data["audit"]}
    by_subject: dict[str, list[dict]] = {}
    for row in data["observed"]:
        by_subject.setdefault(row["subject_id"], []).append(row)
    out = []
    latent_names = {"capacity", "reserve", "debt", "strain", "true", "reporting_bias", "noiseless", "u_"}
    for rows in by_subject.values():
        rows.sort(key=lambda r: r["timestamp"])
        eval_start = len(rows) - 30
        for i, current in enumerate(rows):
            if evaluation_only and i < eval_start:
                continue
            past = rows[max(0, i-k):i] if k else []
            if any(r["timestamp"] >= current["timestamp"] for r in past):
                raise AssertionError("current/future history leakage")
            rec = {
                "subject_id": current["subject_id"], "session_id": current["session_id"], "fold": current["fold"],
                "sequence": current["sequence"], "activity_type": current["activity_type"],
                "current_demand": float(current["workload"].get("u_v5", current["workload"].get("speed_kmh", current["workload"].get("work_sec", 0)))),
                "planned_duration_min": current["planned_duration_min"], "recovery_interval_days": current["recovery_interval_days"],
                "v5_kmh": current["v5_kmh"], "hr_bpm": current["hr_bpm"], "temperature_c": current["temperature_c"],
                "spo2_pct": current["spo2_pct"], "hr_quality": current["hr_quality"], "temperature_quality": current["temperature_quality"],
                "spo2_quality": current["spo2_quality"], "history_n": len(past),
                "targets": current["targets"],
            }
            for field in ("hr_bpm", "temperature_c", "spo2_pct", "actual_duration_min"):
                values = [float(r[field]) for r in past if r[field] is not None]
                rec[f"history_{field}_mean"] = float(np.mean(values)) if values else None
                rec[f"history_{field}_sd"] = float(np.std(values)) if len(values) > 1 else None
            for target in ("burden_BASE", "fatigue", "condition"):
                values = [r["targets"][target] for r in past if r["targets"][target] is not None]
                rec[f"history_{target}_mean"] = float(np.mean(values)) if values else None
                rec[f"history_{target}_last"] = float(values[-1]) if values else None
            for activity in ("AEROBIC", "LOADED_MOVEMENT", "BODYWEIGHT_CIRCUIT", "NONE"):
                subset = [r for r in past if r["activity_type"] == activity]
                rec[f"history_{activity}_n"] = len(subset)
                hrs = [r["hr_bpm"] for r in subset if r["hr_bpm"] is not None]
                rec[f"history_{activity}_hr_mean"] = float(np.mean(hrs)) if hrs else None
            if any(any(name in key for name in latent_names) for key in rec if key != "targets"):
                raise AssertionError("latent key in predictor feature")
            rec["audit_true"] = audit_by_id[current["session_id"]]
            out.append(rec)
    return out


if __name__ == "__main__":
    d = generate()
    print(json.dumps({"rows": len(d["observed"]), "subjects": len(d["profiles_audit_only"])}, indent=2))
