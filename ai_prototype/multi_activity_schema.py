"""Observed-only input contract for v2.2 multi-activity work.

This file validates records. It does not generate physiology, targets, or scores.
"""
from __future__ import annotations

from math import isfinite

ACTIVITIES = {"RUN", "LOADED_MARCH", "BODYWEIGHT_CIRCUIT"}
STOP_REASONS = {"completed", "voluntary", "safety", "medical", "administrative", "unknown"}
FORBIDDEN = {
    "true_cs", "cs_like", "true_dprime", "dprime_like", "q", "reserve",
    "tau_fast", "tau_slow", "strain", "debt", "latent", "noiseless_target",
    "hypothetical_limit", "future_target",
}


def _number(value, name, *, low=0.0, allow_zero=True):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if value < low or (not allow_zero and value == 0):
        raise ValueError(f"{name} is outside its valid range")


def _forbidden_keys(value, path="record"):
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in FORBIDDEN:
                raise ValueError(f"latent/forbidden field at {path}.{key}")
            _forbidden_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _forbidden_keys(child, f"{path}[{index}]")


def validate(record: dict) -> dict:
    """Validate one observed activity log and return it unchanged."""
    if not isinstance(record, dict):
        raise ValueError("record must be an object")
    _forbidden_keys(record)
    for name in ("schema_version", "subject_id", "session_id", "timestamp", "activity_type"):
        if not isinstance(record.get(name), str) or not record[name].strip():
            raise ValueError(f"{name} is required")
    activity = record["activity_type"]
    if activity not in ACTIVITIES:
        raise ValueError(f"unsupported activity_type: {activity}")
    _number(record.get("planned_duration_min"), "planned_duration_min", allow_zero=False)
    _number(record.get("actual_duration_min"), "actual_duration_min", allow_zero=False)
    if record["actual_duration_min"] > record["planned_duration_min"] * 2:
        raise ValueError("actual_duration_min requires review: over twice planned duration")
    if not isinstance(record.get("completed"), bool):
        raise ValueError("completed must be boolean")
    reason = record.get("stop_reason")
    if reason not in STOP_REASONS:
        raise ValueError("stop_reason is required and must use the controlled vocabulary")
    if record["completed"] != (reason == "completed"):
        raise ValueError("completed and stop_reason disagree")
    _number(record.get("recovery_interval_min"), "recovery_interval_min")
    workload = record.get("workload")
    if not isinstance(workload, dict):
        raise ValueError("workload is required")
    {"RUN": _run, "LOADED_MARCH": _march, "BODYWEIGHT_CIRCUIT": _circuit}[activity](workload)
    _vitals(record.get("vitals", {}))
    return record


def _run(w):
    for key in ("distance_km", "actual_speed_kmh"):
        _number(w.get(key), key, allow_zero=False)
    if "grade_pct" in w:
        _number(abs(w["grade_pct"]), "grade_pct")
    anchor = w.get("prior_performance_anchor")
    if anchor is not None:
        if not isinstance(anchor, dict):
            raise ValueError("prior_performance_anchor must be an object")
        _number(anchor.get("distance_km"), "anchor.distance_km", allow_zero=False)
        _number(anchor.get("time_min"), "anchor.time_min", allow_zero=False)
        if not isinstance(anchor.get("observed_at"), str) or not anchor["observed_at"].strip():
            raise ValueError("anchor.observed_at is required")


def _march(w):
    for key in ("distance_km", "actual_speed_kmh", "carried_load_kg", "body_mass_kg"):
        _number(w.get(key), key, allow_zero=(key == "carried_load_kg"))
    if not isinstance(w.get("terrain"), str) or not w["terrain"].strip():
        raise ValueError("terrain is required")
    _number(abs(w.get("grade_pct", 0.0)), "grade_pct")


def _circuit(w):
    exercises = w.get("exercises")
    if not isinstance(exercises, list) or not exercises:
        raise ValueError("exercises must be a non-empty list")
    for index, item in enumerate(exercises):
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
            raise ValueError(f"exercises[{index}].name is required")
        for key in ("planned_reps", "actual_reps", "sets", "work_sec", "rest_sec"):
            _number(item.get(key), f"exercises[{index}].{key}")
        if "external_load_kg" in item:
            _number(item["external_load_kg"], f"exercises[{index}].external_load_kg")


def _vitals(vitals):
    if not isinstance(vitals, dict):
        raise ValueError("vitals must be an object")
    for phase, values in vitals.items():
        if phase not in {"pre", "post", "recovery"} or not isinstance(values, dict):
            raise ValueError("vitals phases are pre/post/recovery objects")
        for key, value in values.items():
            if key not in {"hr_bpm", "spo2_pct", "temperature_c", "systolic_mmhg", "diastolic_mmhg", "quality"}:
                raise ValueError(f"unsupported vital: {key}")
            _number(value, f"vitals.{phase}.{key}")


def assignment_view(record: dict) -> dict:
    """Return only information allowed before assigning the current workload."""
    validate(record)
    return {
        "schema_version": record["schema_version"],
        "subject_id": record["subject_id"],
        "activity_type": record["activity_type"],
        "prior_performance_anchor": record["workload"].get("prior_performance_anchor"),
        "recovery_interval_min": record["recovery_interval_min"],
        "pre_vitals": record.get("vitals", {}).get("pre", {}),
    }

