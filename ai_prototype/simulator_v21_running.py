"""Locked v2.1-running core generator; synthetic constructs, not physiological estimates."""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np

import capacity

ROOT = Path(__file__).resolve().parent
LOCKS = {
    "SIMULATOR_V21_RUNNING_PROTOCOL.md": "4594babf1e5cef0fc69a2879d7bb5b0a374bfde4abefd1661f4de9fb87aba129",
    "SIMULATOR_V21_RUNNING_PARAMETERS.md": "be7eed3eae78a3a2e56fa3e07ee7101afa5780ba753b13bde0ba28f07bb99823",
    "SIMULATOR_V21_RUNNING_PARAMETERS_AMENDMENT_01.md": "1e135e799dd3b776838b78b26b160fdc43d380878287899b99d8fd345cf21540",
}
LEVELS = {
    "rho": {"low": .90, "base": .97, "high": 1.05},
    "dprime": {"low": 80., "base": 130., "high": 200.},
    "tau_fast": {"low": 2., "base": 4., "high": 6.},  # minutes
    "tau_slow": {"low": 12., "base": 24., "high": 48.},  # hours
    "response_sd": {"low": 5., "base": 10., "high": 15.},
    "physiology_sd": {"low": 3., "base": 5., "high": 8.},
    "rpe_error_sd": {"low": 1.2, "base": .8, "high": .4},  # reliability LOW -> largest error
    "rpe_bias_sd": {"low": .3, "base": .5, "high": .8},
    "measurement_sd": {"low": 2., "base": 4., "high": 6.},
}
COUPLINGS = {
    "WEAK": (.10, .05, .20, .15, .50),
    "BASE": (.20, .15, .25, .15, .25),
    "STRONG": (.30, .25, .25, .10, .10),
}


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_locks() -> None:
    for name, expected in LOCKS.items():
        if file_hash(ROOT / name) != expected:
            raise ValueError(f"Locked input changed: {name}")
    sidecar = (ROOT / "SIMULATOR_V21_RUNNING_PARAMETERS_AMENDMENT_01.sha256").read_text(encoding="ascii").split()
    if sidecar != [LOCKS["SIMULATOR_V21_RUNNING_PARAMETERS_AMENDMENT_01.md"],
                   "SIMULATOR_V21_RUNNING_PARAMETERS_AMENDMENT_01.md"]:
        raise ValueError("Amendment sidecar mismatch")


def scenario(family: str | None = None, level: str = "base") -> dict[str, float]:
    if level not in ("low", "base", "high") or family not in (None, *LEVELS):
        raise ValueError("Unknown sensitivity choice")
    return {key: values[level if key == family else "base"] for key, values in LEVELS.items()}


def source_data() -> tuple[dict[str, list[dict]], dict[str, list[float]], list[float]]:
    """Keep source runner, 5-km anchor, speed and duration paired."""
    rows, _ = capacity.dataset()
    runs: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        runs[row["subject"]].append(row)
    gaps: dict[str, list[float]] = {}
    for source, items in runs.items():
        days = sorted(date.fromisoformat(item["date"]) for item in items)
        gaps[source] = [float((b - a).days * 24) for a, b in zip(days, days[1:]) if b > a]
    all_gaps = [gap for values in gaps.values() for gap in values]
    calibration = json.loads((ROOT / "artifacts/simulator_v2_calibration_v1/calibration.json").read_text(encoding="utf-8"))
    baselines = [float(v["median_bpm"]) for v in calibration["parameters"]["P01"]["subjects"].values()]
    return dict(runs), {key: value or all_gaps for key, value in gaps.items()}, baselines


def draw_subject(rng: np.random.Generator, source: str, v5_kmh: float,
                 baselines: list[float], p: dict[str, float], sid: str) -> dict:
    rho = float(rng.triangular(p["rho"] - .03, p["rho"], p["rho"] + .03))
    dprime = float(rng.triangular(.8 * p["dprime"], p["dprime"], 1.2 * p["dprime"]))
    while True:
        delta = float(rng.normal(0, p["response_sd"]))
        if 120 + delta / .70 > 0:
            break
    return {
        "subject": sid, "source_subject": source, "v5_kmh": v5_kmh,
        "baseline_hr": float(rng.choice(baselines)),
        "cs": rho * v5_kmh / 3.6, "rho": rho, "dprime": dprime,
        "tau_fast": p["tau_fast"] * float(rng.triangular(.75, 1, 1.25)),
        "tau_slow": p["tau_slow"] * float(rng.triangular(.75, 1, 1.25)),
        "delta_hr": delta,
        "bias": {"burden": float(rng.normal(0, p["rpe_bias_sd"])),
                 "fatigue": float(rng.normal(0, .5)),
                 "condition": float(rng.normal(0, .5))},
    }


def core(profile: dict, previous_q: float, previous_debt: float,
         gap_h: float, speed_kmh: float, planned_minutes: float,
         u_b: float = .5, u_w: float = .5) -> dict:
    """Pure structural equations; reporting and measurement noise are separate."""
    dprime, cs = profile["dprime"], profile["cs"]
    q_start = dprime - (dprime - previous_q) * math.exp(-60 * gap_h / profile["tau_fast"])
    debt_pre = previous_debt * math.exp(-gap_h / profile["tau_slow"])
    speed = speed_kmh / 3.6
    x = speed / cs
    if speed > cs:
        limit_minutes = q_start / (60 * (speed - cs))
        completed = planned_minutes <= limit_minutes
        actual_minutes = min(planned_minutes, limit_minutes)
        q_end = max(0., q_start - 60 * actual_minutes * (speed - cs))
    elif speed < cs:
        limit_minutes = None
        completed, actual_minutes = True, planned_minutes
        q_end = dprime - (dprime - q_start) * math.exp(-actual_minutes / profile["tau_fast"])
    else:
        limit_minutes = None
        completed, actual_minutes, q_end = True, planned_minutes, q_start
    depletion = max(0., (q_start - q_end) / dprime)
    relative = x / (1 + x)
    duration_term = actual_minutes / (actual_minutes + 60)
    strain = (relative + duration_term + depletion + debt_pre) / 4
    exposure = x * actual_minutes / 60
    debt_after = 1 - (1 - debt_pre) * math.exp(-.5 * (exposure + depletion))
    true_hr_mean = profile["baseline_hr"] + 120 * x + profile["delta_hr"] * x / .70 + 5 * strain + 5 * debt_pre
    terms = (relative, depletion, strain, debt_pre, u_b)
    latent = {name: 2 + 6 * sum(w * v for w, v in zip(weights, terms))
              for name, weights in COUPLINGS.items()}
    latent["fatigue"] = 2 + 6 * (.50 * debt_after + .25 * strain + .25 * (1 - u_w))
    latent["condition"] = 2 + 6 * (.30 * (1 - debt_pre) + .25 * q_end / dprime
                                    + .25 * (1 - strain) + .20 * u_w)
    return {"q_start": q_start, "q_end": q_end, "depletion": depletion,
            "debt_pre": debt_pre, "debt_after": debt_after, "strain": strain,
            "relative": relative, "duration_term": duration_term, "x": x,
            "u_b": u_b, "u_w": u_w, "true_hr_mean": true_hr_mean,
            "completed": completed, "actual_minutes": actual_minutes,
            "limit_minutes": limit_minutes, "latent": latent}


def generate(seed: int = 20260921, subjects: int = 120, sessions: int = 24,
             family: str | None = None, level: str = "base") -> tuple[list[dict], dict]:
    check_locks()
    p = scenario(family, level)
    runs, gaps, baselines = source_data()
    rng = np.random.default_rng(seed)
    sources = sorted(runs)
    counts = np.array([len(runs[name]) for name in sources], dtype=float)
    probabilities = counts / counts.sum()
    output, profiles = [], {}
    for j in range(subjects):
        source = str(rng.choice(sources, p=probabilities))
        v5 = float(runs[source][0]["features"]["reference_speed_kmh"])
        sid = f"v21-s{j:03d}"
        profile = draw_subject(rng, source, v5, baselines, p, sid)
        profiles[sid] = profile
        previous_q, previous_debt = profile["dprime"], 0.
        for index in range(sessions):
            template = runs[source][int(rng.integers(len(runs[source])))]
            gap_h = 0. if index == 0 else float(rng.choice(gaps[source]))
            speed_kmh = float(template["features"]["speed_kmh"])
            duration = float(template["features"]["duration_minutes"])
            u_b, u_w = float(rng.uniform()), float(rng.uniform())
            state = core(profile, previous_q, previous_debt, gap_h, speed_kmh, duration, u_b, u_w)
            true_hr = state["true_hr_mean"] + float(rng.normal(0, p["physiology_sd"]))
            observed_hr = true_hr + float(rng.normal(0, p["measurement_sd"]))
            errors = {"burden": float(rng.normal(0, p["rpe_error_sd"])),
                      "fatigue": float(rng.normal(0, .8)), "condition": float(rng.normal(0, .8))}
            labels, clipping = {}, {}
            for target in ("burden", "fatigue", "condition"):
                names = COUPLINGS if target == "burden" else (target,)
                for name in names:
                    key = name if target == "burden" else target
                    raw = state["latent"][key] + profile["bias"][target] + errors[target]
                    labels[key] = float(np.clip(raw, 0, 10)) if state["completed"] else None
                    clipping[key] = bool(raw < 0 or raw > 10) if state["completed"] else None
            output.append({"subject": sid, "session": f"{sid}-r{index:02d}", "index": index,
                           "source_subject": source, "speed_kmh": speed_kmh,
                           "planned_minutes": duration, "gap_h": gap_h,
                           "true_hr": true_hr, "observed_hr": observed_hr,
                           "labels": labels, "clipping": clipping, **state})
            previous_q, previous_debt = state["q_end"], state["debt_after"]
    return output, profiles


def canonical_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
