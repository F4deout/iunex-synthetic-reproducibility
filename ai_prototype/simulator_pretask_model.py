"""Preregistered pre-task synthetic generator.

Only T0 observations and past sessions may become predictor inputs.  Latent
variables are retained in a separate audit table and never returned by the
feature builder.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
PARAM = ROOT / "PRETASK_MODEL_PARAMETERS.json"
LOCK = ROOT / "PRETASK_MODEL_LOCK.json"
TASKS = ("AEROBIC", "LOADED_MOVEMENT", "BODYWEIGHT_CIRCUIT")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_lock() -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    changed = [x["path"] for x in lock["files"] if sha(ROOT / x["path"]) != x["sha256"]]
    if changed:
        raise RuntimeError(f"locked preregistration changed: {changed}")


def _measure(rng, true, sd, missing_p, artifact_p, artifact_scale, bounds):
    artifact = bool(rng.random() < artifact_p)
    missing = bool(rng.random() < missing_p)
    error = rng.normal(0, sd * (artifact_scale if artifact else 1.0))
    observed = float(np.clip(true + error, bounds[0], bounds[1]))
    quality = float(np.clip(0.94 - 0.55 * artifact + rng.normal(0, 0.035), 0, 1))
    return (None if missing else observed), quality, missing, artifact


def _report(rng, z, slope, bias, drift, noise_sd, positive=True):
    construct = z if positive else 1.0 - z
    noiseless = float(np.clip(2.0 + 6.0 * slope * construct + bias + drift, 0, 10))
    return float(np.clip(noiseless + rng.normal(0, noise_sd), 0, 10)), noiseless


def generate(seed: int = 110) -> dict:
    verify_lock()
    p = json.loads(PARAM.read_text(encoding="utf-8"))
    rng = np.random.default_rng(seed)
    observed, audit, profiles = [], [], []
    n_cal, n_eval = p["sessions"]["calibration"], p["sessions"]["evaluation"]
    demand_levels = p["planned_demand_levels"]
    durations = p["planned_duration_minutes"]
    gaps, gap_probs = p["observation_gap_days"]["values"], p["observation_gap_days"]["probabilities"]
    s = p["subject"]; phys = p["physiology"]; outcome = p["task_outcome"]
    report = p["reporting"]; state = p["pretask_state"]; gate = p["safety_gate_research_only"]

    for ix in range(p["subjects"]["total"]):
        sid = f"PT-{ix+1:03d}"
        fold = "train" if ix < 72 else "validation" if ix < 96 else "test"
        prng = np.random.default_rng(int(hashlib.sha256(f"{seed}|{sid}".encode()).hexdigest()[:16], 16))
        common = prng.normal()
        capacities = {}
        rho = s["cross_task_capacity_correlation"]
        for task in TASKS:
            z = rho * common + math.sqrt(1-rho*rho) * prng.normal()
            capacities[task] = float(np.exp(s["capacity_log_sd"] * z))
        tolerance = float(prng.lognormal(s["tolerance_minutes_log_mean"], s["tolerance_minutes_log_sd"]))
        recovery_h = float(prng.lognormal(s["recovery_hours_log_mean"], s["recovery_hours_log_sd"]))
        hr_base = float(prng.normal(phys["resting_hr_mean"], phys["resting_hr_sd"]))
        temp_base = float(prng.normal(phys["temperature_mean_c"], phys["temperature_between_subject_sd_c"]))
        spo2_base = float(np.clip(prng.normal(phys["spo2_mean_pct"], phys["spo2_between_subject_sd_pct"]), 94, 99.5))
        slopes = {name: float(prng.lognormal(0, s["perception_slope_log_sd"])) for name in ("fatigue", "condition", "burden")}
        biases = {name: float(prng.normal(0, s["reporting_bias_sd_points"])) for name in slopes}
        anchor = float(np.clip(1.0 + 0.55 * common + prng.normal(0, .20), .35, 2.2))
        profiles.append({"subject_id": sid, "fold": fold, "observed_anchor": anchor,
                         "capacity": capacities, "tolerance_minutes": tolerance,
                         "recovery_hours": recovery_h, "hr_baseline": hr_base,
                         "perception_slopes": slopes, "reporting_bias": biases})
        debt, log_capacity_change, drift, day = 0.0, 0.0, 0.0, 0

        for j in range(n_cal+n_eval):
            gap_days = int(prng.choice(gaps, p=gap_probs)); day += gap_days
            debt_pre = float(debt * math.exp(-24*gap_days/recovery_h))
            log_capacity_change += float(prng.normal(0, p["capacity_dynamics"]["continuous_log_sd_per_30_days"] * math.sqrt(gap_days/30)))
            if prng.random() < p["capacity_dynamics"]["event_probability_per_30_days"] * gap_days/30:
                log_capacity_change += float(prng.normal(0, p["capacity_dynamics"]["event_log_sd"]))
            drift += float(prng.normal(0, report["drift_sd_per_30_days"] * math.sqrt(gap_days/30)))
            sleep = float(np.clip(prng.beta(2, 5), 0, 1)); stress = float(np.clip(prng.beta(2, 4), 0, 1))
            unobserved = float(np.clip(.5 + prng.normal(0, state["session_unobserved_sd"]), 0, 1))
            pre_fatigue_latent = float(np.clip(state["debt_weight"]*debt_pre + state["sleep_weight"]*sleep + state["stress_weight"]*stress + state["unobserved_weight"]*unobserved, 0, 1))

            true_hr = hr_base + phys["fatigue_hr_gain_bpm"]*pre_fatigue_latent + phys["stress_hr_gain_bpm"]*stress + prng.normal(0, 1.3)
            true_temp = temp_base + .25*pre_fatigue_latent + .10*stress + prng.normal(0, .04)
            true_spo2 = float(np.clip(spo2_base - .5*pre_fatigue_latent + prng.normal(0,.15), 90, 99.8))
            hr, q_hr, m_hr, a_hr = _measure(prng,true_hr,phys["measurement_hr_sd_bpm"],phys["missing_probability"],phys["artifact_probability"],3,(25,240))
            temp,q_temp,m_temp,a_temp = _measure(prng,true_temp,phys["measurement_temperature_sd_c"],phys["missing_probability"],phys["artifact_probability"],4,(30,43))
            spo2,q_spo2,m_spo2,a_spo2 = _measure(prng,true_spo2,phys["measurement_spo2_sd_pct"],phys["missing_probability"],phys["artifact_probability"],4,(70,100))
            fatigue_score, fatigue_noiseless = _report(prng,pre_fatigue_latent,slopes["fatigue"],biases["fatigue"],drift,report["session_noise_sd_points"],True)
            condition_score, condition_noiseless = _report(prng,pre_fatigue_latent,slopes["condition"],biases["condition"],drift,report["session_noise_sd_points"],False)

            task = TASKS[(j + ix) % len(TASKS)]
            planned_level = float(demand_levels[(j*3 + ix) % len(demand_levels)])
            planned_duration = float(durations[(j*5 + ix) % len(durations)])
            external_demand = planned_level * anchor
            effective_capacity = capacities[task] * math.exp(log_capacity_change) * (1-outcome["fatigue_capacity_penalty"]*pre_fatigue_latent)
            relative = float(external_demand/max(effective_capacity,.05))
            if relative <= outcome["relative_demand_threshold"]:
                latent_limit = float("inf")
            else:
                latent_limit = tolerance/max(relative-outcome["relative_demand_threshold"],.02)
            behavior = float(prng.lognormal(0,outcome["behavioral_stop_log_sd"]))
            actual = planned_duration if math.isinf(latent_limit) else min(planned_duration, latent_limit*behavior)
            completed = bool(actual >= planned_duration-1e-9)
            depletion = float(np.clip(max(relative-1,0)*actual/max(tolerance,1),0,1))
            duration_term = actual/max(durations)
            out_unobserved = float(prng.uniform(0,1))
            w = outcome["post_burden_weights"]
            burden_latent = float(np.clip(w["relative_demand"]*np.clip(relative/1.8,0,1)+w["duration"]*duration_term+w["pre_fatigue"]*pre_fatigue_latent+w["depletion"]*depletion+w["unobserved"]*out_unobserved,0,1))
            burden_score, burden_noiseless = _report(prng,burden_latent,slopes["burden"],biases["burden"],drift,report["session_noise_sd_points"],True)
            recovery_delay = float(max(0,outcome["recovery_delay_base_hours"]+outcome["recovery_delay_burden_gain_hours"]*burden_latent*(recovery_h/24)+prng.normal(0,1.2)))
            debt = float(np.clip(debt_pre + .45*burden_latent + .25*depletion,0,1))
            safety = bool((hr is not None and (hr < gate["resting_hr_low_bpm"] or hr > gate["resting_hr_high_bpm"]))
                          or (temp is not None and temp >= gate["temperature_high_c"])
                          or (spo2 is not None and spo2 < gate["spo2_low_pct"]))
            session_id = f"{seed}-{sid}-{j:03d}"
            observed.append({
                "session_id":session_id,"subject_id":sid,"fold":fold,"session_index":j,"day":day,
                "phase":"calibration" if j<n_cal else "evaluation","task_type":task,
                "planned_demand":planned_level,"external_demand":external_demand,"planned_duration":planned_duration,
                "observed_anchor":anchor,"gap_days":gap_days,
                "t0_hr":hr,"t0_temperature":temp,"t0_spo2":spo2,"quality_hr":q_hr,"quality_temperature":q_temp,"quality_spo2":q_spo2,
                "safety_gate":safety,
                "targets":{"pre_fatigue":fatigue_score,"pre_condition":condition_score,"completed":int(completed),
                           "stop_time":None if completed else float(actual),"post_burden":burden_score,"recovery_delay":recovery_delay},
                "history_observable":{"actual_duration":float(actual),"completed":int(completed),
                    "observed_stop_time":None if completed else float(actual),"post_burden":burden_score,
                    "recovery_delay":recovery_delay,"pre_fatigue":fatigue_score,"pre_condition":condition_score,
                    "t2_hr":float(true_hr+45*burden_latent+prng.normal(0,3)),"t3_hr":float(hr_base+12*debt+prng.normal(0,2))}
            })
            audit.append({"session_id":session_id,"subject_id":sid,"pre_fatigue_latent":pre_fatigue_latent,
                "debt_pre":debt_pre,"capacity":effective_capacity,"relative_demand":relative,"tolerance_minutes":tolerance,
                "depletion":depletion,"latent_limit":None if math.isinf(latent_limit) else latent_limit,
                "burden_latent":burden_latent,"fatigue_noiseless":fatigue_noiseless,
                "condition_noiseless":condition_noiseless,"burden_noiseless":burden_noiseless,
                "missing_count":int(m_hr)+int(m_temp)+int(m_spo2),"artifact_count":int(a_hr)+int(a_temp)+int(a_spo2)})
    return {"seed":seed,"observed":observed,"audit":audit,"profiles":profiles,"parameter_sha256":sha(PARAM),"lock_sha256":sha(LOCK)}


def history_rows(data: dict, mode: str, k: int = 20) -> list[dict]:
    if mode not in {"current","sensor_history","self_report_history","performance_history","full"}:
        raise ValueError(mode)
    by_subject = {}
    for r in data["observed"]: by_subject.setdefault(r["subject_id"],[]).append(r)
    rows=[]
    for seq in by_subject.values():
        seq.sort(key=lambda x:x["session_index"])
        for i,r in enumerate(seq):
            if r["phase"] != "evaluation": continue
            out={x:r[x] for x in ("session_id","subject_id","fold","session_index","task_type","planned_demand","external_demand","planned_duration","observed_anchor","gap_days","t0_hr","t0_temperature","t0_spo2","quality_hr","quality_temperature","quality_spo2","safety_gate")}
            out["targets"]=r["targets"]
            past=seq[max(0,i-k):i]
            def stats(name, values):
                v=[float(x) for x in values if x is not None]
                out[f"hist_{name}_mean"]=float(np.mean(v)) if v else None
                out[f"hist_{name}_sd"]=float(np.std(v)) if v else None
                out[f"hist_{name}_last"]=v[-1] if v else None
                out[f"hist_{name}_n"]=len(v)
            if mode in {"sensor_history","full"}:
                for name in ("t0_hr","t0_temperature","t0_spo2"):
                    stats(name,[x[name] for x in past])
                stats("t2_hr",[x["history_observable"]["t2_hr"] for x in past])
                stats("t3_hr",[x["history_observable"]["t3_hr"] for x in past])
            if mode in {"self_report_history","full"}:
                for name in ("pre_fatigue","pre_condition","post_burden"):
                    stats(name,[x["history_observable"][name] for x in past])
            if mode in {"performance_history","full"}:
                for name in ("actual_duration","completed","observed_stop_time","recovery_delay"):
                    stats(name,[x["history_observable"][name] for x in past])
                for task in TASKS:
                    subset=[x for x in past if x["task_type"]==task]
                    stats(f"{task.lower()}_completion",[x["history_observable"]["completed"] for x in subset])
                    stats(f"{task.lower()}_duration",[x["history_observable"]["actual_duration"] for x in subset])
            rows.append(out)
    return rows
