"""Frozen v2.2 multi-activity synthetic generator.

Implements only LOADED_MARCH and BODYWEIGHT_CIRCUIT.  The v2.1 running
generator is deliberately untouched.  Observed and audit-only outputs are
separate so latent state cannot enter a predictor by accident.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from multi_activity_schema import validate

ROOT = Path(__file__).resolve().parent
PARAM_PATH = ROOT / "SIMULATOR_V22_MULTI_ACTIVITY_PARAMETERS.json"
CAL_PATH = ROOT / "artifacts/simulator_v2_calibration_v1/calibration.json"
LOCKED_INPUTS = {
    "SIMULATOR_V22_MULTI_ACTIVITY_DESIGN.md": "2d22367a51225912370644dd3976d2baa11f72226ff24df91f9174f10affbdb9",
    "SIMULATOR_V22_MULTI_ACTIVITY_PROTOCOL.md": "1f649ad9ab3891d799420ef2ca96794194bd73e99557762db53b9a2012299c11",
    "SIMULATOR_V22_MULTI_ACTIVITY_PARAMETER_REGISTER.md": "e5a368b1e42f755b9aeb9a3e50db1af67c34342c1863fcb42f9315f28026efa2",
    "SIMULATOR_V22_MULTI_ACTIVITY_AMENDMENT_01.md": "1a00063cecd259d0210f013a57a6ed6b763761a7b2b283e4f0b9af240f02d2e5",
    "SIMULATOR_V22_MULTI_ACTIVITY_AMENDMENT_02.md": "0b16a50c6742c2c01ca10af511876ee7efad7da4577db8a3abbbbba4d6c851e2",
    "SIMULATOR_V22_MULTI_ACTIVITY_AMENDMENT_03.md": "ae16de7c5a046efb66c4df1df9de003cd7c85e7aa8e5000c60baa6fb19bd66af",
    "SIMULATOR_V22_MULTI_ACTIVITY_AMENDMENT_04.md": "b31428726eeab2224dcda7787f8640ae16690efa8d9837f9b33ec2a3abe1104c",
    "SIMULATOR_V22_MULTI_ACTIVITY_PARAMETERS.json": "3c5ca26d0787d744155e3ff3507325437da2140f819e41faa1f2575628ecce42",
}


def _verify_lock() -> None:
    changed = [name for name, expected in LOCKED_INPUTS.items()
               if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != expected]
    if changed:
        raise RuntimeError(f"locked v2.2 input changed: {changed}")


def _rng(seed: int, *parts: object) -> np.random.Generator:
    token = "|".join(map(str, (seed,) + parts)).encode()
    raw = hashlib.sha256(token).digest()[:8]
    return np.random.default_rng(int.from_bytes(raw, "big"))


def _parity(text: str) -> int:
    return hashlib.sha256(text.encode()).digest()[0] & 1


def _q(x: float, low=0.0, high=1.0) -> float:
    return float(np.clip(x, low, high))


def _score(z: float, bias: float, error: float, cfg: dict) -> tuple[float, bool]:
    raw = cfg["offset"] + cfg["scale"] * z + bias + error
    value = float(np.clip(raw, *cfg["clip"]))
    return value, value != raw


def _march_demand(row: list, cfg: dict, scenario: str) -> float:
    _, speed, load_ratio, grade, _ = row
    s = _q((speed - 3.5) / 2.0)
    l = _q(load_ratio / cfg["load_ratio_upper"])
    g = _q(grade / cfg["uphill_grade_upper_pct"])
    alpha = cfg["speed_load_interaction"][scenario]
    ws, wl, wg = cfg["base_weights_speed_load_grade"]
    return (ws * s + wl * l + wg * g + alpha * s * l) / (1.0 + alpha)


def _circuit_demand(row: list, cfg: dict, scenario: str) -> float:
    _, work, rest, duration, *_ = row
    density = work / (work + rest)
    w = _q(work / cfg["work_reference_sec"])
    t = _q(duration / cfg["duration_reference_min"])
    a, b, c = cfg["work_density_weights"][scenario.upper()]
    return a * density + b * w + c * t


def _events(params: dict, subject_id: str) -> list[dict]:
    march = [
        {"activity": "LOADED_MARCH", "phase": phase, "row": row}
        for phase, rows in (("CALIBRATION", params["loaded_march"]["calibration"]),
                            ("EVALUATION", params["loaded_march"]["evaluation"]))
        for row in rows
    ]
    circuit = [
        {"activity": "BODYWEIGHT_CIRCUIT", "phase": phase, "row": row}
        for phase, rows in (("CALIBRATION", params["bodyweight_circuit"]["calibration"]),
                            ("EVALUATION", params["bodyweight_circuit"]["evaluation"]))
        for row in rows
    ]
    mcal, meval = march[:12], march[12:]
    ccal, ceval = circuit[:12], circuit[12:]
    if _parity(subject_id) == 0:
        cal = mcal + ccal
    else:
        cal = ccal + mcal
    ev = []
    for m, c in zip(meval, ceval):
        ev.extend((m, c) if _parity(subject_id) == 0 else (c, m))
    return cal + ev


def _gap_minutes(event: dict, previous: dict | None, params: dict) -> float:
    row = event["row"]
    if event["activity"] == "BODYWEIGHT_CIRCUIT" and event["phase"] == "CALIBRATION" and len(row) > 4 and row[4] is not None:
        return float(row[4])
    return float(params["provenance"]["default_gap_hours"] * 60.0) if previous else 0.0


def _profile(seed: int, index: int, baselines: list[float], p: dict) -> dict:
    sid = f"V22-{index + 1:03d}"
    r = _rng(seed, sid, "profile")
    common = p["common"]
    center = common["capacity_center"]["base"]
    half = common["capacity_half_spread"]["base"]
    tri = common["recovery_multiplier_triangular"]
    return {
        "subject_id": sid,
        "fold": "train" if index < 72 else "validation" if index < 96 else "test",
        "baseline_hr": float(r.choice(baselines)),
        "capacity": {
            "LOADED_MARCH": float(r.triangular(center - half, center, center + half)),
            "BODYWEIGHT_CIRCUIT": float(r.triangular(center - half, center, center + half)),
        },
        "hr_response_delta": {
            a: float(r.normal(0, common["response_sd_bpm"]["base"]))
            for a in p["activities"]
        },
        "recovery_multiplier": float(r.triangular(*tri)),
        "bias": {
            t: float(r.normal(0, common["personal_bias_sd_points"]["base"]))
            for t in ("burden_WEAK", "burden_BASE", "burden_STRONG", "fatigue", "condition")
        },
    }


def _workload(event: dict, actual: float, p: dict) -> dict:
    row = event["row"]
    if event["activity"] == "LOADED_MARCH":
        _, speed, load_ratio, grade, _ = row
        mass = p["loaded_march"]["synthetic_display_body_mass_kg"]
        return {
            "distance_km": speed * actual / 60.0,
            "actual_speed_kmh": speed,
            "carried_load_kg": load_ratio * mass,
            "body_mass_kg": mass,
            "terrain": "synthetic_treadmill",
            "grade_pct": grade,
        }
    _, work, rest, _, *_ = row
    return {"exercises": [
        {"name": name, "planned_reps": 0, "actual_reps": 0, "sets": 1,
         "work_sec": work, "rest_sec": rest}
        for name in p["bodyweight_circuit"]["stations"]
    ]}


def generate(seed: int = 20260928, n_subjects: int = 120, scenario: str = "base") -> dict:
    _verify_lock()
    p = json.loads(PARAM_PATH.read_text(encoding="utf-8"))
    cal = json.loads(CAL_PATH.read_text(encoding="utf-8"))
    baselines = [x["median_bpm"] for x in cal["parameters"]["P01"]["subjects"].values()]
    observed, audit, profiles = [], [], []
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    common = p["common"]

    for i in range(n_subjects):
        prof = _profile(seed, i, baselines, p)
        profiles.append(prof)
        debt, clock, previous = 0.0, start + timedelta(minutes=i), None
        for seq, event in enumerate(_events(p, prof["subject_id"]), 1):
            row, activity = event["row"], event["activity"]
            gap = _gap_minutes(event, previous, p)
            clock += timedelta(minutes=gap)
            tau = common["tau_slow_hours"][scenario] * prof["recovery_multiplier"]
            debt_pre = debt * math.exp(-(gap / 60.0) / tau) if gap else debt
            if activity == "LOADED_MARCH":
                demand = _march_demand(row, p["loaded_march"], scenario)
                planned = float(row[4]); ref = p["loaded_march"]["reference_duration_min"]
                half = p["loaded_march"]["half_duration_min"]
            else:
                demand = _circuit_demand(row, p["bodyweight_circuit"], scenario)
                planned = float(row[3]); ref = p["bodyweight_circuit"]["duration_reference_min"]
                half = p["bodyweight_circuit"]["half_duration_min"]
            relative = demand / prof["capacity"][activity]
            planned_exposure = relative * planned / ref
            rstop = _rng(seed, prof["subject_id"], row[0], "stop")
            session_multiplier = float(math.exp(rstop.normal(-0.5 * common["session_tolerance_log_sd"][scenario] ** 2,
                                                               common["session_tolerance_log_sd"][scenario])))
            threshold = common["tolerance_multiplier"][scenario] * session_multiplier
            completed = planned_exposure <= threshold
            actual = planned if completed else max(1 / 60, threshold * ref / max(relative, 1e-9))
            dterm = actual / (actual + half)
            rterm = relative / (1.0 + relative)
            rs = _rng(seed, prof["subject_id"], row[0], "state")
            u_phys, u_b, u_w = (float(x) for x in rs.normal(0, 0.12, 3))
            strain = _q(sum(w * x for w, x in zip(common["strain_weights"], (rterm, dterm, debt_pre, u_phys))))
            exposure = relative * actual / ref
            debt = _q(1.0 - (1.0 - debt_pre) * math.exp(-common["lambda_debt"][scenario] * exposure))
            rh = _rng(seed, prof["subject_id"], row[0], "hr")
            phys_sd = common["physiology_sd_bpm"][scenario]
            meas_sd = common["measurement_sd_bpm"][scenario]
            pre_true = prof["baseline_hr"] + common["pre_hr_debt_coefficient_bpm"] * debt_pre + rh.normal(0, phys_sd / 2)
            post_true = (prof["baseline_hr"] + (common["hr_gain_bpm"][scenario] + prof["hr_response_delta"][activity]) * rterm
                         + common["post_hr_strain_coefficient_bpm"] * strain
                         + common["post_hr_debt_coefficient_bpm"] * debt_pre + rh.normal(0, phys_sd))
            pre_obs, post_obs = pre_true + rh.normal(0, meas_sd), post_true + rh.normal(0, meas_sd)
            rt = _rng(seed, prof["subject_id"], row[0], "targets")
            errors = {k: float(rt.normal(0, common["occasion_error_sd_points"][scenario]))
                      for k in prof["bias"]}
            labels, clipped = {}, {}
            for level, weights in p["burden_coupling"].items():
                z = sum(w * x for w, x in zip(weights, (relative, dterm, strain, debt_pre, u_b)))
                labels[f"burden_{level}"], clipped[f"burden_{level}"] = _score(z, prof["bias"][f"burden_{level}"], errors[f"burden_{level}"], common["score_map"])
            fw = common["fatigue_weights"]
            fatigue_z = fw[0] * strain + fw[1] * debt_pre + fw[2] * u_w
            labels["fatigue"], clipped["fatigue"] = _score(fatigue_z, prof["bias"]["fatigue"], errors["fatigue"], common["score_map"])
            cw = common["condition_weights"]
            condition_z = cw[0] * (1 - strain) + cw[1] * (1 - debt_pre) + cw[2] * (1 - _q((u_w + 0.5) / 1.0))
            labels["condition"], clipped["condition"] = _score(condition_z, prof["bias"]["condition"], errors["condition"], common["score_map"])
            session_id = f"{prof['subject_id']}-{row[0]}"
            rec = {
                "schema_version": "v22-observed-1", "subject_id": prof["subject_id"], "session_id": session_id,
                "timestamp": clock.isoformat(), "fold": prof["fold"], "phase": event["phase"], "event_code": row[0],
                "sequence": seq, "activity_type": activity, "planned_duration_min": planned,
                "actual_duration_min": float(actual), "completed": bool(completed),
                "stop_reason": "completed" if completed else "unknown", "recovery_interval_min": gap,
                "workload": _workload(event, actual, p),
                "vitals": {"pre": {"hr_bpm": float(pre_obs), "quality": 1.0},
                           "post": {"hr_bpm": float(post_obs), "quality": 1.0}},
                "targets": labels, "target_clipped": clipped,
            }
            validate(rec)
            observed.append(rec)
            audit.append({
                "subject_id": prof["subject_id"], "session_id": session_id, "fold": prof["fold"], "phase": event["phase"],
                "activity_type": activity, "event_code": row[0], "capacity": prof["capacity"][activity],
                "demand": demand, "relative_demand": relative, "duration_term": dterm, "strain": strain,
                "debt_pre": debt_pre, "debt_after": debt, "u_phys": u_phys, "u_burden": u_b, "u_wellness": u_w,
                "true_pre_hr": float(pre_true), "true_post_hr": float(post_true), "planned_exposure": planned_exposure,
                "stop_threshold": threshold, "session_tolerance_multiplier": session_multiplier,
            })
            clock += timedelta(minutes=actual)
            previous = event
    return {"seed": seed, "scenario": scenario, "observed": observed, "audit": audit, "profiles_audit_only": profiles}


if __name__ == "__main__":
    data = generate()
    print(json.dumps({"seed": data["seed"], "observed_rows": len(data["observed"]), "audit_rows": len(data["audit"])}, indent=2))
