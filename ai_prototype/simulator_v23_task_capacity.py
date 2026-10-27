"""Preregistered v2.3 task-capacity generator; v2.2 remains untouched."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import simulator_v22_multi_activity as v22
from multi_activity_schema import validate

ROOT = Path(__file__).resolve().parent
PARAM = ROOT / "SIMULATOR_V23_TASK_CAPACITY_PARAMETERS.json"
FREEZE = ROOT / "SIMULATOR_V23_TASK_CAPACITY_FREEZE.json"
CAL = ROOT / "artifacts/simulator_v2_calibration_v1/calibration.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_lock() -> None:
    lock = json.loads(FREEZE.read_text(encoding="utf-8-sig"))
    changed = [name for name, expected in lock["files"].items()
               if _sha(ROOT / name) != expected]
    if changed:
        raise RuntimeError(f"locked v2.3 input changed: {changed}")
    if _sha(ROOT / "simulator_v22_multi_activity.py") != lock["frozen_v22_generator_sha256"]:
        raise RuntimeError("frozen v2.2 generator changed")


def _aerobic_reference() -> np.ndarray:
    frames = [pd.read_sas(path, format="xport") for path in
              sorted((ROOT / "data/external/nhanes_cv_fitness").glob("*.xpt"))]
    data = pd.concat(frames, ignore_index=True)
    values = data.loc[(data.CVDEXSTS == 1) & data.CVDESVO2.notna(), "CVDESVO2"].astype(float).to_numpy()
    lo, med, hi = np.quantile(values, [.05, .5, .95])
    return values[(values >= lo) & (values <= hi)] / med


def _profile(seed: int, index: int, baselines: list[float], p: dict, aerobic: np.ndarray,
             sensitivity: str) -> dict:
    sid = f"V23-{index + 1:03d}"
    r = v22._rng(seed, sid, "v23-profile")
    tc, tol, rec, phys, targets = (p[k] for k in
                                    ("task_capacity", "tolerance", "recovery", "physiology", "targets"))
    a = float(r.choice(aerobic))
    shared = tc["shared_aerobic_loading"][sensitivity]
    task_sd = tc["task_specific_log_sd"][sensitivity]
    rho = tc["cross_task_residual_correlation"][sensitivity]
    zm = float(r.normal()); zc = float(rho * zm + math.sqrt(1 - rho ** 2) * r.normal())
    capacities = {
        "LOADED_MARCH": float(math.exp(shared * math.log(a) + task_sd * zm)),
        "BODYWEIGHT_CIRCUIT": float(math.exp(shared * math.log(a) + task_sd * zc)),
    }
    tol_sd = tol["task_specific_log_sd"][sensitivity]
    tol_corr = tol["capacity_tolerance_correlation"][sensitivity]
    tolerances = {
        "LOADED_MARCH": float(math.exp(tol_sd * (tol_corr * zm + math.sqrt(1 - tol_corr ** 2) * r.normal()))),
        "BODYWEIGHT_CIRCUIT": float(math.exp(tol_sd * (tol_corr * zc + math.sqrt(1 - tol_corr ** 2) * r.normal()))),
    }
    rec_sd = rec["individual_log_sd"][sensitivity]
    return {
        "subject_id": sid,
        "fold": "train" if index < 72 else "validation" if index < 96 else "test",
        "aerobic_reference": a,
        "baseline_hr": float(r.choice(baselines)),
        "capacity": capacities,
        "tolerance": tolerances,
        "fast_recovery_multiplier": float(math.exp(rec_sd * r.normal())),
        "slow_recovery_multiplier": float(math.exp(rec_sd * r.normal())),
        "hr_response_delta": {activity: float(r.normal(0, phys["subject_response_sd_bpm"][sensitivity]))
                              for activity in p["activities"]},
        "bias": {name: float(r.normal(0, targets["personal_bias_sd_points"][sensitivity]))
                 for name in ("burden_WEAK", "burden_BASE", "burden_STRONG", "fatigue", "condition")},
        "task_z": {"LOADED_MARCH": zm, "BODYWEIGHT_CIRCUIT": zc},
    }


def generate(seed: int = 110, n_subjects: int = 120, sensitivity: str = "base",
             forced: dict | None = None) -> dict:
    _verify_lock()
    p = json.loads(PARAM.read_text(encoding="utf-8"))
    old = json.loads(v22.PARAM_PATH.read_text(encoding="utf-8"))
    cal = json.loads(CAL.read_text(encoding="utf-8"))
    baselines = [x["median_bpm"] for x in cal["parameters"]["P01"]["subjects"].values()]
    aerobic = _aerobic_reference()
    observed, audit, profiles = [], [], []
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    threshold = p["tolerance"]["threshold"]

    for i in range(n_subjects):
        prof = _profile(seed, i, baselines, p, aerobic, sensitivity)
        if forced:
            for name in ("capacity", "tolerance"):
                if name in forced:
                    prof[name] = {a: float(forced[name]) for a in p["activities"]}
            for name in ("fast_recovery_multiplier", "slow_recovery_multiplier"):
                if name in forced:
                    prof[name] = float(forced[name])
        profiles.append(prof)
        debt, reserve = 0.0, {a: 1.0 for a in p["activities"]}
        clock, previous = start + timedelta(minutes=i), None
        for seq, event in enumerate(v22._events(old, prof["subject_id"]), 1):
            row, activity = event["row"], event["activity"]
            gap = v22._gap_minutes(event, previous, old)
            clock += timedelta(minutes=gap)
            fast_tau = p["recovery"]["fast_time_constant_minutes"][sensitivity] * prof["fast_recovery_multiplier"]
            slow_tau = p["recovery"]["slow_time_constant_hours"][sensitivity] * prof["slow_recovery_multiplier"]
            reserve_pre = 1 - (1 - reserve[activity]) * math.exp(-gap / fast_tau) if gap else reserve[activity]
            debt_pre = debt * math.exp(-(gap / 60) / slow_tau) if gap else debt
            if activity == "LOADED_MARCH":
                demand = v22._march_demand(row, old["loaded_march"], sensitivity)
                planned, ref, half = float(row[4]), old["loaded_march"]["reference_duration_min"], old["loaded_march"]["half_duration_min"]
            else:
                demand = v22._circuit_demand(row, old["bodyweight_circuit"], sensitivity)
                planned, ref, half = float(row[3]), old["bodyweight_circuit"]["duration_reference_min"], old["bodyweight_circuit"]["half_duration_min"]
            relative = demand / prof["capacity"][activity]
            rate = max(relative - threshold, 0.0) / (ref * prof["tolerance"][activity])
            planned_depletion = rate * planned
            completed = planned_depletion <= reserve_pre
            actual = planned if completed or rate == 0 else max(1 / 60, reserve_pre / rate)
            depletion = min(reserve_pre, rate * actual)
            reserve_after = max(0.0, reserve_pre - depletion)
            reserve[activity] = reserve_after
            rterm, dterm = relative / (1 + relative), actual / (actual + half)
            rs = v22._rng(seed, prof["subject_id"], row[0], "v23-state")
            u_phys, u_burden, u_wellness = (float(x) for x in rs.normal(0, .12, 3))
            sw = p["latent_state"]["strain_weights_relative_duration_depletion_debt_unobserved"]
            strain = v22._q(sum(w * x for w, x in zip(sw, (rterm, dterm, depletion, debt_pre, u_phys))))
            exposure = relative * actual / ref
            gain = p["latent_state"]["slow_debt_gain"][sensitivity]
            debt = v22._q(1 - (1 - debt_pre) * math.exp(-gain * exposure))
            rh = v22._rng(seed, prof["subject_id"], row[0], "v23-hr")
            phys_sd = p["physiology"]["physiology_sd_bpm"][sensitivity]
            meas_sd = p["physiology"]["measurement_sd_bpm"][sensitivity]
            pre_true = prof["baseline_hr"] + rh.normal(0, phys_sd / 2)
            post_true = prof["baseline_hr"] + (p["physiology"]["hr_gain_bpm"][sensitivity] + prof["hr_response_delta"][activity]) * rterm + rh.normal(0, phys_sd)
            pre_obs, post_obs = pre_true + rh.normal(0, meas_sd), post_true + rh.normal(0, meas_sd)
            rt = v22._rng(seed, prof["subject_id"], row[0], "v23-targets")
            error_sd = p["targets"]["occasion_error_sd_points"][sensitivity]
            errors = {name: float(rt.normal(0, error_sd)) for name in prof["bias"]}
            labels, clipped = {}, {}
            for level in ("WEAK", "BASE", "STRONG"):
                weights = p["targets"]["burden_coupling"][level]
                z = sum(w * x for w, x in zip(weights, (rterm, depletion, strain, debt_pre, u_burden)))
                key = f"burden_{level}"
                labels[key], clipped[key] = v22._score(z, prof["bias"][key], errors[key], p["targets"]["score_map"])
            fw = p["targets"]["fatigue_weights"]["values"]
            fz = sum(w * x for w, x in zip(fw, (rterm, depletion, strain, debt_pre, u_wellness)))
            labels["fatigue"], clipped["fatigue"] = v22._score(fz, prof["bias"]["fatigue"], errors["fatigue"], p["targets"]["score_map"])
            cw = p["targets"]["condition_weights"]["values"]
            positive = v22._q((u_wellness + .5) / 1.0)
            cz = sum(w * x for w, x in zip(cw, (1-rterm, reserve_after, 1-strain, 1-debt_pre, positive)))
            labels["condition"], clipped["condition"] = v22._score(cz, prof["bias"]["condition"], errors["condition"], p["targets"]["score_map"])
            session_id = f"{prof['subject_id']}-{row[0]}"
            rec = {
                "schema_version": "v22-observed-1", "subject_id": prof["subject_id"], "session_id": session_id,
                "timestamp": clock.isoformat(), "fold": prof["fold"], "phase": event["phase"], "event_code": row[0],
                "sequence": seq, "activity_type": activity, "planned_duration_min": planned,
                "actual_duration_min": float(actual), "completed": bool(completed),
                "stop_reason": "completed" if completed else "unknown",
                "recovery_interval_min": gap, "workload": v22._workload(event, actual, old),
                "vitals": {"pre": {"hr_bpm": float(pre_obs), "quality": 1.0},
                           "post": {"hr_bpm": float(post_obs), "quality": 1.0}},
                "targets": labels, "target_clipped": clipped,
            }
            validate(rec); observed.append(rec)
            audit.append({
                "subject_id": prof["subject_id"], "session_id": session_id, "fold": prof["fold"], "phase": event["phase"],
                "activity_type": activity, "event_code": row[0], "aerobic_reference": prof["aerobic_reference"],
                "capacity": prof["capacity"][activity], "tolerance": prof["tolerance"][activity],
                "demand": demand, "relative_demand": relative, "reserve_pre": reserve_pre,
                "reserve_depletion": depletion, "reserve_after": reserve_after, "duration_term": dterm,
                "strain": strain, "debt_pre": debt_pre, "debt_after": debt,
                "true_pre_hr": float(pre_true), "true_post_hr": float(post_true),
                "u_phys": u_phys, "u_burden": u_burden, "u_wellness": u_wellness,
            })
            clock += timedelta(minutes=actual); previous = event
    return {"seed": seed, "sensitivity": sensitivity, "observed": observed,
            "audit": audit, "profiles_audit_only": profiles}


if __name__ == "__main__":
    d = generate()
    print(json.dumps({"observed": len(d["observed"]), "audit": len(d["audit"])}, indent=2))
