from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np


ROOT = Path(__file__).resolve().parent
PARAM_PATH = ROOT / "RQ1_STATE_MIXTURE_PARAMETERS.json"


def clip(x: float, lo: float, hi: float) -> float:
    return float(min(max(x, lo), hi))


def tnorm(rng: np.random.Generator, mean: float, sd: float, lo: float, hi: float) -> float:
    for _ in range(200):
        x = float(rng.normal(mean, sd))
        if lo <= x <= hi:
            return x
    return clip(mean, lo, hi)


def weighted_choice(rng: np.random.Generator, weights: Dict[str, float]) -> str:
    keys = list(weights)
    p = np.array([weights[k] for k in keys], dtype=float)
    p /= p.sum()
    return str(rng.choice(keys, p=p))


@dataclass(frozen=True)
class Subject:
    subject_id: str
    split: str
    hr_baseline: float
    temp_baseline: float
    spo2_baseline: float
    fitness: float
    heat_sensitivity: float
    oxygen_sensitivity: float


def _subject(rng: np.random.Generator, idx: int, split: str) -> Subject:
    return Subject(
        subject_id=f"S{idx:03d}",
        split=split,
        hr_baseline=tnorm(rng, 70, 9, 48, 96),
        temp_baseline=tnorm(rng, 36.65, 0.24, 36.0, 37.3),
        spo2_baseline=tnorm(rng, 97.7, 0.85, 95.0, 100.0),
        fitness=tnorm(rng, 0.55, 0.18, 0.10, 0.95),
        heat_sensitivity=tnorm(rng, 1.0, 0.16, 0.65, 1.40),
        oxygen_sensitivity=tnorm(rng, 1.0, 0.12, 0.70, 1.35),
    )


def _latent_and_true(rng: np.random.Generator, s: Subject, scenario: str) -> Dict[str, float | str | int]:
    context = "rest"
    exertion = 0.0
    recovery = 0.0
    thermal = 0.03
    oxygen = 0.03
    cardio = 0.04
    attention = 0

    if scenario == "healthy_rest":
        pass
    elif scenario == "normal_post_activity":
        context = "post_activity"
        exertion = float(rng.uniform(0.30, 0.85))
        recovery = float(rng.uniform(0.05, 0.35))
    elif scenario == "artifact_only":
        pass
    elif scenario == "incomplete_recovery":
        context = "recovery"
        exertion = float(rng.uniform(0.25, 0.65))
        recovery = float(rng.uniform(0.55, 0.90))
        attention = 1
    elif scenario == "febrile":
        thermal = float(rng.uniform(0.38, 0.68))
        cardio = float(rng.uniform(0.10, 0.30))
        attention = 1
    elif scenario == "severe_heat":
        context = "post_activity" if rng.random() < 0.70 else "rest"
        exertion = float(rng.uniform(0.35, 0.85)) if context == "post_activity" else 0.0
        recovery = float(rng.uniform(0.10, 0.55)) if context == "post_activity" else 0.0
        thermal = float(rng.uniform(0.78, 1.00))
        cardio = float(rng.uniform(0.15, 0.42))
        attention = 2
    elif scenario == "hypothermic":
        thermal = -float(rng.uniform(0.55, 1.00))
        cardio = float(rng.uniform(-0.35, 0.25))
        attention = 2
    elif scenario == "hypoxemia_moderate":
        oxygen = float(rng.uniform(0.35, 0.58))
        cardio = float(rng.uniform(0.05, 0.30))
        attention = 1
    elif scenario == "hypoxemia_severe":
        context = "recovery" if rng.random() < 0.25 else "rest"
        exertion = float(rng.uniform(0.15, 0.45)) if context == "recovery" else 0.0
        recovery = float(rng.uniform(0.20, 0.65)) if context == "recovery" else 0.0
        oxygen = float(rng.uniform(0.62, 1.00))
        cardio = float(rng.uniform(0.10, 0.50))
        attention = 2
    elif scenario == "resting_tachycardia":
        cardio = float(rng.uniform(0.60, 1.00))
        attention = 1
    elif scenario == "resting_bradycardia":
        cardio = -float(rng.uniform(0.45, 0.88))
        attention = 1
    elif scenario == "combined_abnormality":
        context = "post_activity" if rng.random() < 0.55 else "rest"
        exertion = float(rng.uniform(0.35, 0.90)) if context == "post_activity" else 0.0
        thermal = float(rng.uniform(0.45, 0.90))
        oxygen = float(rng.uniform(0.45, 0.90))
        cardio = float(rng.uniform(0.30, 0.80))
        recovery = float(rng.uniform(0.25, 0.75))
        attention = 2
    else:
        raise ValueError(scenario)

    # Common-cause generation: scenario latents cause both true physiology and targets.
    true_temp = s.temp_baseline + 4.0 * thermal * s.heat_sensitivity + 0.28 * exertion + rng.normal(0, 0.08)
    # A nonlinear saturation response permits both mild and severe hypoxemic states
    # without changing the physiological upper bound.
    oxygen_drop = (5.0 * oxygen + 18.0 * oxygen ** 3) * s.oxygen_sensitivity
    true_spo2 = s.spo2_baseline - oxygen_drop - 0.25 * exertion + rng.normal(0, 0.20)
    true_hr = (
        s.hr_baseline
        + (78.0 - 28.0 * s.fitness) * exertion
        + 55.0 * cardio
        + 13.0 * max(thermal, 0)
        + 13.0 * recovery
        + rng.normal(0, 3.0)
    )

    # Enforce frozen scenario support without changing target weights.
    if scenario == "febrile":
        true_temp = tnorm(rng, 38.5, 0.30, 38.0, 39.0)
    elif scenario == "severe_heat":
        true_temp = tnorm(rng, 40.1, 0.62, 39.1, 41.5)
    elif scenario == "hypothermic":
        true_temp = tnorm(rng, 33.8, 0.85, 30.0, 35.0)
    else:
        true_temp = clip(true_temp, 35.5, 38.0 if scenario == "normal_post_activity" else 37.9)

    if scenario == "hypoxemia_moderate":
        true_spo2 = tnorm(rng, 93.5, 0.72, 92.0, 94.9)
    elif scenario in {"hypoxemia_severe", "combined_abnormality"}:
        true_spo2 = tnorm(rng, true_spo2, 1.3, 70.0, 91.9)
    else:
        true_spo2 = clip(true_spo2, 95.0, 100.0)

    if scenario == "resting_tachycardia":
        true_hr = tnorm(rng, 138.0, 16.0, 111.0, 175.0)
    elif scenario == "resting_bradycardia":
        true_hr = tnorm(rng, 42.0, 5.0, 30.0, 50.0)
    else:
        true_hr = clip(true_hr, 35.0, 210.0)

    if scenario == "artifact_only":
        true_hr = clip(true_hr, 51.0, 100.0)
        true_temp = clip(true_temp, 36.1, 37.5)
        true_spo2 = clip(true_spo2, 96.0, 100.0)

    # Synchronize the synthetic attention label with the already frozen safety
    # routing policy. This label uses true physiology; predictors receive only
    # noisy observed measurements.
    if true_temp >= 40.0 or true_temp <= 35.0 or true_spo2 <= 92.0:
        attention = 2
    elif true_temp >= 38.0 or true_spo2 < 95.0:
        attention = max(attention, 1)
    if context == "rest":
        if true_hr >= 131.0 or true_hr <= 40.0:
            attention = 2
        elif true_hr > 100.0 or true_hr <= 50.0:
            attention = max(attention, 1)
    elif true_hr >= 131.0:
        attention = max(attention, 1)

    return {
        "context": context,
        "attention_level": attention,
        "thermal": thermal,
        "oxygen": oxygen,
        "cardio": cardio,
        "exertion": exertion,
        "recovery": recovery,
        "true_hr_bpm": true_hr,
        "true_temperature_c": true_temp,
        "true_spo2_pct": true_spo2,
    }


def _target_score(rng: np.random.Generator, latent: Dict[str, float | str | int], spec: dict) -> float:
    unobserved = float(rng.beta(2.0, 5.0))
    components = {
        "thermal": abs(float(latent["thermal"])),
        "oxygen": float(latent["oxygen"]),
        "cardio": abs(float(latent["cardio"])),
        "exertion": float(latent["exertion"]),
        "recovery": float(latent["recovery"]),
        "unobserved": unobserved,
    }
    weights = spec["components"]
    weighted = sum(weights[k] * components[k] for k in weights) / sum(weights.values())
    dominant = max(components[k] for k in spec["dominant_components"])
    fraction = float(spec["dominant_fraction"])
    severity = (1.0 - fraction) * weighted + fraction * dominant
    return clip(0.5 + float(spec["score_scale"]) * severity + rng.normal(0, 0.45), 0.0, 10.0)


def _measure(rng: np.random.Generator, true_value: float, sd: float, lo: float, hi: float, artifact: bool, kind: str) -> Tuple[float | None, float, int]:
    artifact_flag = int(artifact)
    if artifact:
        if kind == "hr":
            err = float(rng.choice([-1, 1]) * rng.uniform(15, 55))
        elif kind == "temp":
            err = float(rng.choice([-1, 1]) * rng.uniform(0.8, 3.0))
        else:
            err = float(rng.choice([-1, 1]) * rng.uniform(3.0, 12.0))
        q = float(rng.uniform(0.05, 0.45))
    else:
        err = float(rng.normal(0, sd))
        q = float(rng.uniform(0.72, 1.0))
    measured = true_value + err
    if kind == "spo2":
        # Reflecting bounds avoid impossible values and a hard-clipping point mass
        # at 100%, while preserving both positive and negative artifact directions.
        while measured > hi or measured < lo:
            if measured > hi:
                measured = hi - (measured - hi)
            if measured < lo:
                measured = lo + (lo - measured)
    else:
        measured = clip(measured, lo, hi)
    return float(measured), q, artifact_flag


def generate(config_path: Path = PARAM_PATH) -> Tuple[List[dict], List[dict], dict]:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    rng = np.random.default_rng(int(cfg["seed"]))
    n = int(cfg["n_subjects"])
    splits = ["train"] * 72 + ["validation"] * 24 + ["test"] * 24
    subjects = [_subject(rng, i + 1, splits[i]) for i in range(n)]
    observed: List[dict] = []
    audit: List[dict] = []

    for s in subjects:
        for j in range(int(cfg["sessions_per_subject"])):
            scenario = weighted_choice(rng, cfg["scenario_weights"])
            lat = _latent_and_true(rng, s, scenario)
            forced_artifact = scenario == "artifact_only"
            any_artifact = forced_artifact or bool(rng.random() < cfg["measurement"]["artifact_probability"])
            hr, hr_q, hr_art = _measure(rng, float(lat["true_hr_bpm"]), cfg["measurement"]["hr_sd_bpm"], 20, 250, any_artifact, "hr")
            temp, temp_q, temp_art = _measure(rng, float(lat["true_temperature_c"]), cfg["measurement"]["temperature_sd_c"], 20, 45, any_artifact, "temp")
            spo2, spo2_q, spo2_art = _measure(rng, float(lat["true_spo2_pct"]), cfg["measurement"]["spo2_sd_pct"], 50, 100, any_artifact, "spo2")

            # Independent missingness; quality remains recorded to distinguish missing from low-quality values.
            for name in ("hr", "temp", "spo2"):
                if rng.random() < cfg["measurement"]["missing_probability"]:
                    if name == "hr": hr = None
                    if name == "temp": temp = None
                    if name == "spo2": spo2 = None

            condition_loss = _target_score(rng, lat, cfg["target_weights"]["condition_loss"])
            fatigue = _target_score(rng, lat, cfg["target_weights"]["fatigue"])
            burden = _target_score(rng, lat, cfg["target_weights"]["exercise_burden"]) if lat["context"] != "rest" else None
            condition = clip(10.0 - condition_loss, 0.0, 10.0)

            sid = f"{s.subject_id}_{j + 1:03d}"
            row = {
                "subject_id": s.subject_id,
                "session_id": sid,
                "split": s.split,
                "scenario": scenario,
                "context": lat["context"],
                "hr_bpm": hr,
                "hr_quality": hr_q,
                "temperature_c": temp,
                "temperature_quality": temp_q,
                "spo2_pct": spo2,
                "spo2_quality": spo2_q,
                "measurement_issue": int(bool(hr_art or temp_art or spo2_art)),
                "attention_level": int(lat["attention_level"]),
                "needs_attention": int(int(lat["attention_level"]) > 0),
                "condition_score": condition,
                "fatigue_score": fatigue,
                "exercise_burden_score": burden,
            }
            observed.append(row)
            audit.append({
                "subject_id": s.subject_id,
                "session_id": sid,
                "split": s.split,
                "scenario": scenario,
                "hr_baseline": s.hr_baseline,
                "temp_baseline": s.temp_baseline,
                "spo2_baseline": s.spo2_baseline,
                "fitness": s.fitness,
                **lat,
            })
    return observed, audit, cfg


def _write_csv(path: Path, rows: Iterable[dict]) -> None:
    rows = list(rows)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def save(out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    observed, audit, cfg = generate()
    observed_path = out_dir / "state_mixture_observed.csv"
    audit_path = out_dir / "state_mixture_audit.jsonl"
    _write_csv(observed_path, observed)
    with audit_path.open("w", encoding="utf-8", newline="\n") as f:
        for row in audit:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    config_copy = out_dir / "frozen_parameters.json"
    config_copy.write_text(json.dumps(cfg, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    files = {}
    for p in (observed_path, audit_path, config_copy):
        files[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    manifest = {"version": cfg["version"], "rows": len(observed), "files": files}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    print(json.dumps(save(args.out), indent=2))
