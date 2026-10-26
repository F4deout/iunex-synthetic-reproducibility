"""Locked v2.1 dataset schedules and split audit; no predictor is fitted here."""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

import capacity
import simulator_v21_running as sim

ROOT = Path(__file__).resolve().parent
PROTOCOL = "SIMULATOR_V21_RUNNING_DATASET_PROTOCOL.md"
PROTOCOL_HASH = "21c95ca62f4bb98f0ef93671fa68d506d7aa6dd7983c856dfc70039a05574100"
GENERATOR_HASH = "d03b854edb53fa95955d440c58c71bf3e7a158c3104753841f073a20046cf586"
OUT = ROOT / "artifacts" / "synthetic_v21_running_dataset_dryrun"
SEED = 20260921
K_VALUES = (0, 1, 3, 5, 10, 20)
FOLDS = ("train", "validation", "id_test")


def check_locks() -> None:
    sim.check_locks()
    if sim.file_hash(ROOT / PROTOCOL) != PROTOCOL_HASH:
        raise ValueError("Dataset protocol changed")
    if (ROOT / "SIMULATOR_V21_RUNNING_DATASET_PROTOCOL.sha256").read_text(encoding="ascii").split() != [PROTOCOL_HASH, PROTOCOL]:
        raise ValueError("Dataset protocol sidecar changed")
    if sim.file_hash(ROOT / "simulator_v21_running.py") != GENERATOR_HASH:
        raise ValueError("Frozen v2.1 generator changed")


def source_templates() -> list[dict]:
    """Fail closed: an audit ID must match exactly one dated workout."""
    try:
        rows, audit = capacity.dataset()
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("STOP: source workout/Fitbit logId audit cannot be constructed") from exc
    matched = audit["matched_sessions"]
    if len(rows) != 64 or len(matched) != len(rows):
        raise ValueError("STOP: expected 64 matched source workouts and audit IDs")
    by_key: dict[tuple[str, str], dict] = {}
    for a in matched:
        log_id = a.get("log_id")
        if log_id is None or isinstance(log_id, bool) or str(log_id).strip() == "":
            raise ValueError("STOP: missing Fitbit logId")
        key = (a["subject"], a["exercise_start"][:10])
        if key in by_key:
            raise ValueError("STOP: ambiguous source subject/day audit join")
        by_key[key] = a
    ids: set[str] = set()
    result = []
    for row in rows:
        key = (row["subject"], row["date"])
        if key not in by_key:
            raise ValueError("STOP: workout cannot be joined to Fitbit logId")
        a = by_key.pop(key)
        sid = f"{row['subject']}:{a['log_id']}"
        if sid in ids:
            raise ValueError("STOP: duplicate source_template_id")
        ids.add(sid)
        result.append({"source_template_id": sid, "source_subject": row["subject"],
                       "date": row["date"], "speed_kmh": row["features"]["speed_kmh"],
                       "duration_minutes": row["features"]["duration_minutes"],
                       "v5_kmh": row["features"]["reference_speed_kmh"]})
    if by_key:
        raise ValueError("STOP: unmatched Fitbit audit entry")
    return result


def template_folds(templates: list[dict]) -> tuple[dict[str, str], dict]:
    if len(templates) != 64 or len({t["source_template_id"] for t in templates}) != 64:
        raise ValueError("STOP: invalid source template set")
    ordered = sorted(templates, key=lambda t: hashlib.sha256(
        ("v21-naturalistic-group-v1|" + t["source_template_id"]).encode("utf-8")).hexdigest())
    fold = {t["source_template_id"]: FOLDS[0 if i < 38 else 1 if i < 51 else 2]
            for i, t in enumerate(ordered)}
    manifest = {name: [t["source_template_id"] for t in ordered if fold[t["source_template_id"]] == name]
                for name in FOLDS}
    if [len(manifest[n]) for n in FOLDS] != [38, 13, 13]:
        raise AssertionError("Template split sizes changed")
    return fold, manifest


def subject_folds() -> dict[str, str]:
    ids = sorted((f"v21-s{i:03d}" for i in range(120)),
                 key=lambda s: hashlib.sha256(s.encode("utf-8")).hexdigest())
    return {sid: FOLDS[0 if i < 72 else 1 if i < 96 else 2] for i, sid in enumerate(ids)}


def profiles_for_folds(templates: list[dict], tfold: dict[str, str], sfold: dict[str, str],
                       rng: np.random.Generator, p: dict) -> dict[str, dict]:
    baselines = sim.source_data()[2]
    profiles = {}
    for sid in sorted(sfold):
        pool = [t for t in templates if tfold[t["source_template_id"]] == sfold[sid]]
        sources = sorted({t["source_subject"] for t in pool})
        counts = np.asarray([sum(t["source_subject"] == source for t in pool)
                             for source in sources], dtype=float)
        source = str(rng.choice(sources, p=counts / counts.sum()))
        v5_values = {t["v5_kmh"] for t in pool if t["source_subject"] == source}
        if len(v5_values) != 1:
            raise ValueError("STOP: inconsistent source 5 km reference")
        profiles[sid] = sim.draw_subject(rng, source, v5_values.pop(), baselines, p, sid)
    return profiles


def observed_event(profile: dict, previous_q: float, previous_debt: float, gap_h: float,
                   speed_kmh: float, minutes: float, rng: np.random.Generator, p: dict,
                   *, rest: bool = False) -> dict:
    """Use the frozen core and the same measurement/report draws as its generator."""
    u_b, u_w = float(rng.uniform()), float(rng.uniform())
    state = sim.core(profile, previous_q, previous_debt, gap_h, speed_kmh, minutes, u_b, u_w)
    true_hr = state["true_hr_mean"] + float(rng.normal(0, p["physiology_sd"]))
    observed_hr = true_hr + float(rng.normal(0, p["measurement_sd"]))
    errors = {"burden": float(rng.normal(0, p["rpe_error_sd"])),
              "fatigue": float(rng.normal(0, .8)), "condition": float(rng.normal(0, .8))}
    labels, clipping = {}, {}
    for target in ("burden", "fatigue", "condition"):
        names = sim.COUPLINGS if target == "burden" else (target,)
        for name in names:
            raw = state["latent"][name] + profile["bias"][target] + errors[target]
            labels[name] = float(np.clip(raw, 0, 10)) if state["completed"] and not rest else None
            clipping[name] = bool(raw < 0 or raw > 10) if state["completed"] and not rest else None
    return {**state, "true_hr": true_hr, "observed_hr": observed_hr,
            "labels": labels, "clipping": clipping, "gap_h": gap_h,
            "speed_kmh": speed_kmh, "planned_minutes": minutes}


def rotate(subject: str, letter: str, items: list) -> list:
    offset = int(hashlib.sha256((subject + "|" + letter).encode("utf-8")).hexdigest(), 16) % len(items)
    return items[offset:] + items[:offset]


def controlled_schedule(subject: str) -> list[tuple[str, float, float, float, str]]:
    grid = [("G1", .70, 6), ("G2", .90, 12), ("G3", 1., 6),
            ("G4", 1.05, 3), ("G5", 1.05, 20), ("G6", 1.10, 12)]
    events = [("R1", 0., 0., 0., "calibration")]
    events += [(name, x, t, 72., "calibration") for name, x, t in rotate(subject, "G", grid)]
    for number, gap_minutes in rotate(subject, "F", [(1, 1), (2, 4), (3, 16)]):
        events += [(f"F{number}a", 1.10, 3., 72., "calibration"),
                   (f"F{number}b", 1.10, 12., gap_minutes / 60., "calibration")]
    events.append(("R2", 0., 0., 72., "calibration"))
    for number, gap_hours in rotate(subject, "S", [(1, 6), (2, 24), (3, 72)]):
        events += [(f"S{number}a", .90, 12., 72., "calibration"),
                   (f"S{number}b", .70, 6., float(gap_hours), "calibration")]
    evaluation = [("E1", .70, 6), ("E2", .90, 12), ("E3", 1.05, 3), ("E4", 1.10, 12)]
    events += [(name, x, t, 72., "evaluation") for name, x, t in rotate(subject, "E", evaluation)]
    if len(events) != 24:
        raise AssertionError("Controlled schedule must have 20+4 events")
    return events


def build_naturalistic(profiles: dict, templates: list[dict], tfold: dict[str, str],
                       sfold: dict[str, str], rng: np.random.Generator, p: dict) -> list[dict]:
    pool = defaultdict(list)
    for t in templates:
        pool[(tfold[t["source_template_id"]], t["source_subject"])].append(t)
    rows = []
    _, gaps, _ = sim.source_data()
    for sid in sorted(profiles):
        profile = profiles[sid]
        choices = pool[(sfold[sid], profile["source_subject"])]
        q, debt = profile["dprime"], 0.
        for index in range(24):
            t = choices[int(rng.integers(len(choices)))]
            gap = 0. if index == 0 else float(rng.choice(gaps[profile["source_subject"]]))
            state = observed_event(profile, q, debt, gap, t["speed_kmh"], t["duration_minutes"], rng, p)
            rows.append({**state, "dataset": "NATURALISTIC_GROUPED_V1", "fold": sfold[sid],
                         "subject": sid, "session": f"{sid}-n{index:02d}", "index": index,
                         "event_type": "calibration" if index < 20 else "evaluation",
                         "source_subject": profile["source_subject"],
                         "source_template_id": t["source_template_id"],
                         "protocol_cell_id": None, "v5_kmh": t["v5_kmh"],
                         "empirical_completed_but_simulator_censored": not state["completed"]})
            q, debt = state["q_end"], state["debt_after"]
    return rows


def build_controlled(profiles: dict, sfold: dict[str, str], rng: np.random.Generator,
                     p: dict) -> list[dict]:
    rows = []
    for sid in sorted(profiles):
        profile = profiles[sid]
        q, debt = profile["dprime"], 0.
        for index, (cell, x, minutes, gap, event_type) in enumerate(controlled_schedule(sid)):
            state = observed_event(profile, q, debt, gap, 3.6 * x * profile["cs"],
                                   minutes, rng, p, rest=cell.startswith("R"))
            rows.append({**state, "dataset": "CONTROLLED_PERSONALIZATION", "fold": sfold[sid],
                         "subject": sid, "session": f"{sid}-c{index:02d}", "index": index,
                         "event_type": event_type, "source_subject": profile["source_subject"],
                         "source_template_id": None, "protocol_cell_id": cell,
                         "assigned_relative_intensity_audit_only": x,
                         "v5_kmh": profile["v5_kmh"]})
            q, debt = state["q_end"], state["debt_after"]
    return rows


def history_manifest(rows: list[dict]) -> list[dict]:
    by_subject = defaultdict(list)
    for row in rows:
        by_subject[row["subject"]].append(row)
    output = []
    for sid, items in sorted(by_subject.items()):
        items.sort(key=lambda r: r["index"])
        calibration = [r["session"] for r in items if r["event_type"] == "calibration"]
        evaluations = [r for r in items if r["event_type"] == "evaluation"]
        if len(calibration) != 20 or len(evaluations) != 4:
            raise AssertionError("Incorrect history/evaluation event counts")
        for k in K_VALUES:
            sources = calibration[-k:] if k else []
            for r in evaluations:
                assert all(int(s.rsplit("-", 1)[1][1:]) < r["index"] for s in sources)
                output.append({"subject": sid, "fold": r["fold"], "dataset": r["dataset"],
                               "k": k, "evaluation_session": r["session"],
                               "history_sessions": sources, "completed": r["completed"]})
    return output


def observed_inputs(rows: list[dict]) -> list[dict]:
    """Explicit predictor-facing boundary; keep latent audit rows separate."""
    names = ("dataset", "fold", "subject", "session", "index", "event_type",
             "speed_kmh", "planned_minutes", "actual_minutes", "observed_hr", "gap_h", "completed")
    result = [{name: r[name] for name in names} for r in rows]
    assert all(not ({"x", "cs", "dprime", "q_start", "q_end", "labels", "true_hr",
                     "assigned_relative_intensity_audit_only"} & item.keys()) for item in result)
    return result


def describe(values: list[float]) -> dict:
    a = np.asarray(values, dtype=float)
    if not len(a):
        return {"n": 0}
    q = np.quantile(a, [.01, .05, .5, .95, .99])
    return {"n": len(a), "mean": float(a.mean()), "sd": float(a.std(ddof=1)) if len(a) > 1 else 0.,
            "q01": float(q[0]), "q05": float(q[1]), "median": float(q[2]),
            "q95": float(q[3]), "q99": float(q[4]), "min": float(a.min()), "max": float(a.max())}


def identification_audit(cells: dict[str, dict], profiles: dict) -> dict:
    """Structural inversion only; no target model or history-performance test."""
    cs_errors, dprime_errors, fast_errors, hr_estimates, hr_truth = [], [], [], [], []
    slow_signal, slow_noise, slow_observed, slow_truth = [], [], [], []
    for sid, d in cells.items():
        g5, g6 = d["G5"], d["G6"]
        if not g5["completed"] and not g6["completed"]:
            t1, t2 = g5["limit_minutes"] * 60, g6["limit_minutes"] * 60
            v1, v2 = g5["speed_kmh"] / 3.6, g6["speed_kmh"] / 3.6
            cs = (v2 * t2 - v1 * t1) / (t2 - t1)
            dprime = (v1 - cs) * t1
            cs_errors.append(cs - profiles[sid]["cs"])
            dprime_errors.append(dprime - profiles[sid]["dprime"])
            for n, gap_minutes in ((1, 1), (2, 4), (3, 16)):
                lead, probe = d[f"F{n}a"], d[f"F{n}b"]
                if lead["completed"] and not probe["completed"]:
                    lead_q = dprime - (lead["speed_kmh"] / 3.6 - cs) * 60 * lead["actual_minutes"]
                    probe_q = (probe["speed_kmh"] / 3.6 - cs) * 60 * probe["limit_minutes"]
                    ratio = (dprime - probe_q) / (dprime - lead_q)
                    if 0 < ratio < 1:
                        recovered_tau = -gap_minutes / np.log(ratio)
                        fast_errors.append(float(recovered_tau - profiles[sid]["tau_fast"]))
        x = np.asarray([d[k]["x"] for k in ("G1", "G2", "G3", "G4")])
        y = np.asarray([d[k]["observed_hr"] for k in ("G1", "G2", "G3", "G4")])
        hr_estimates.append(float(.7 * (np.polyfit(x, y, 1)[0] - 120)))
        hr_truth.append(profiles[sid]["delta_hr"])
        s1, s3 = d["S1b"], d["S3b"]
        signal = s1["true_hr_mean"] - s3["true_hr_mean"]
        observed = s1["observed_hr"] - s3["observed_hr"]
        slow_signal.append(signal)
        slow_noise.append(observed - signal)
        slow_observed.append(observed)
        slow_truth.append(profiles[sid]["tau_slow"])
    corr = lambda a, b: float(np.corrcoef(a, b)[0, 1])
    return {
        "cs_like": {"classification": "IDENTIFIABLE" if len(cs_errors) == len(cells) and max(map(abs, cs_errors)) < 1e-6 else "PARTIAL",
                    "paired_limit_count": len(cs_errors), "max_abs_reconstruction_error_mps": max(map(abs, cs_errors), default=None)},
        "dprime_like": {"classification": "IDENTIFIABLE" if len(dprime_errors) == len(cells) and max(map(abs, dprime_errors)) < 1e-6 else "PARTIAL",
                        "paired_limit_count": len(dprime_errors), "max_abs_reconstruction_error_m": max(map(abs, dprime_errors), default=None)},
        "hr_response": {"classification": "PARTIAL", "four_grid_point_slope_truth_correlation": corr(hr_estimates, hr_truth),
                        "four_grid_point_slope_mae_bpm": float(np.mean(np.abs(np.asarray(hr_estimates) - hr_truth)))},
        "fast_recovery": {"classification": "IDENTIFIABLE" if len(fast_errors) == 3 * len(cells) and max(map(abs, fast_errors)) < 1e-6 else "PARTIAL",
                          "inverted_probe_count": len(fast_errors), "max_abs_tau_error_minutes": max(map(abs, fast_errors), default=None)},
        "slow_recovery": {"classification": "NOT_IDENTIFIABLE", "mean_absolute_paired_true_hr_signal_bpm": float(np.mean(np.abs(slow_signal))),
                          "paired_hr_noise_sd_bpm": float(np.std(slow_noise, ddof=1)),
                          "observed_difference_tau_correlation": corr(slow_observed, slow_truth)}
    }


def audit(natural: list[dict], controlled: list[dict], profiles: dict, templates: list[dict],
          tfold: dict[str, str], sfold: dict[str, str], history: list[dict]) -> dict:
    allrows = natural + controlled
    assert len(natural) == len(controlled) == 120 * 24
    assert Counter(tfold.values()) == {"train": 38, "validation": 13, "id_test": 13}
    assert Counter(sfold.values()) == {"train": 72, "validation": 24, "id_test": 24}
    overlaps = {}
    for kind, values in (("template", {f: {t["source_template_id"] for t in templates if tfold[t["source_template_id"]] == f} for f in FOLDS}),
                         ("subject", {f: {sid for sid in sfold if sfold[sid] == f} for f in FOLDS}),
                         ("session", {f: {r["session"] for r in allrows if r["fold"] == f} for f in FOLDS})):
        overlaps[kind] = {f"{a}/{b}": len(values[a] & values[b]) for a, b in
                          (("train", "validation"), ("train", "id_test"), ("validation", "id_test"))}
        assert not any(overlaps[kind].values())
    source_sets = {f: {p["source_subject"] for sid, p in profiles.items() if sfold[sid] == f} for f in FOLDS}
    source_overlap = {f"{a}/{b}": sorted(source_sets[a] & source_sets[b]) for a, b in
                      (("train", "validation"), ("train", "id_test"), ("validation", "id_test"))}
    assert all(r["source_template_id"] is None for r in controlled)
    for sid in profiles:
        rows = [r for r in controlled if r["subject"] == sid]
        schedule = controlled_schedule(sid)
        assert [(r["protocol_cell_id"], r["assigned_relative_intensity_audit_only"],
                 r["planned_minutes"], r["gap_h"], r["event_type"]) for r in rows] == schedule
        assert all(r["source_template_id"] is None for r in rows)
    assert all(tfold[r["source_template_id"]] == r["fold"] for r in natural)
    eval_sets = defaultdict(dict)
    for h in history:
        if h["evaluation_session"] in h["history_sessions"]:
            raise AssertionError("Current evaluation leaked to history")
        if any("-c2" in s or "-n2" in s for s in h["history_sessions"]):
            raise AssertionError("Future evaluation leaked to history")
        eval_sets[(h["dataset"], h["subject"])].setdefault(h["k"], set()).add(h["evaluation_session"])
    assert all(len(set(map(frozenset, group.values()))) == 1 for group in eval_sets.values())
    folds = {}
    for f in FOLDS:
        t = [r for r in natural if r["fold"] == f]
        folds[f] = {"subjects": len({r["subject"] for r in t}),
                    "source_subjects": sorted({r["source_subject"] for r in t}),
                    "templates_used": len({r["source_template_id"] for r in t}),
                    "speed_kmh": describe([r["speed_kmh"] for r in t]),
                    "duration_minutes": describe([r["planned_minutes"] for r in t]),
                    "speed_v5": describe([r["speed_kmh"] / r["v5_kmh"] for r in t]),
                    "below_threshold": sum(r["x"] < 1 for r in t),
                    "at_threshold": sum(r["x"] == 1 for r in t),
                    "above_threshold": sum(r["x"] > 1 for r in t),
                    "simulator_censored": sum(not r["completed"] for r in t)}
    cells = defaultdict(dict)
    for r in controlled:
        cells[r["subject"]][r["protocol_cell_id"]] = r
    limit = {cell: describe([d[cell]["limit_minutes"] for d in cells.values()
                             if d[cell]["limit_minutes"] is not None]) for cell in ("G5", "G6")}
    complete = {cell: sum(d[cell]["completed"] for d in cells.values()) for cell in ("G5", "G6")}
    both_limit = sum(not d["G5"]["completed"] and not d["G6"]["completed"] for d in cells.values())
    fast = {str(gap): {"q_start_fraction": describe([d[f"F{n}b"]["q_start"] / profiles[sid]["dprime"]
                                                   for sid, d in cells.items()]),
                        "depletion": describe([d[f"F{n}b"]["depletion"] for d in cells.values()]),
                        "probe_censored": sum(not d[f"F{n}b"]["completed"] for d in cells.values())}
            for n, gap in ((1, 1), (2, 4), (3, 16))}
    slow = {str(gap): {"debt_pre": describe([d[f"S{n}b"]["debt_pre"] for d in cells.values()]),
                        "true_hr_mean": describe([d[f"S{n}b"]["true_hr_mean"] for d in cells.values()])}
            for n, gap in ((1, 6), (2, 24), (3, 72))}
    evaluations = {cell: {"complete": sum(d[cell]["completed"] for d in cells.values()),
                          "censored": sum(not d[cell]["completed"] for d in cells.values())}
                   for cell in ("E1", "E2", "E3", "E4")}
    return {"status": {"naturalistic_builder": "PASS", "controlled_builder": "PASS"},
            "template_intersections": overlaps["template"], "subject_intersections": overlaps["subject"],
            "session_intersections": overlaps["session"], "source_subject_intersections": source_overlap,
            "naturalistic_folds": folds, "naturalistic_overall": {
                "below_threshold": sum(r["x"] < 1 for r in natural),
                "at_threshold": sum(r["x"] == 1 for r in natural),
                "above_threshold": sum(r["x"] > 1 for r in natural),
                "simulator_censored": sum(not r["completed"] for r in natural)},
            "controlled": {"source_template_uses": sum(r["source_template_id"] is not None for r in controlled),
                           "calibration_events_per_subject": 20, "evaluation_events_per_subject": 4,
                           "G5_G6_time_to_limit_minutes": limit, "G5_G6_completed": complete,
                           "both_G5_G6_limits_observed": both_limit,
                           "fast_recovery_by_gap_minutes": fast,
                           "slow_recovery_by_gap_hours": slow,
                           "evaluation": evaluations,
                           "identification_audit": identification_audit(cells, profiles)},
            "history_k": list(K_VALUES), "history_leakage": "PASS",
            "event_order_hash_rotation": "PASS"}


def build(seed: int = SEED) -> dict:
    check_locks()
    templates = source_templates()  # STOP before generating anything if IDs fail
    tfold, template_manifest = template_folds(templates)
    sfold = subject_folds()
    p = sim.scenario()
    rng = np.random.default_rng(seed)
    profiles = profiles_for_folds(templates, tfold, sfold, rng, p)
    natural = build_naturalistic(profiles, templates, tfold, sfold, rng, p)
    controlled = build_controlled(profiles, sfold, rng, p)
    history = history_manifest(natural) + history_manifest(controlled)
    report = audit(natural, controlled, profiles, templates, tfold, sfold, history)
    observed = observed_inputs(natural + controlled)
    return {"seed": seed, "config": {"subjects": 120, "naturalistic_templates": 64,
                                      "naturalistic_sessions_per_subject": 24,
                                      "controlled_calibration_events": 20,
                                      "controlled_evaluation_events": 4,
                                      "parameter_level": "base", "coupling": ["WEAK", "BASE", "STRONG"]},
            "locks": {PROTOCOL: PROTOCOL_HASH,
                      **{name: sim.file_hash(ROOT / name) for name in sim.LOCKS},
                      "simulator_v21_running.py": sim.file_hash(ROOT / "simulator_v21_running.py")},
            "template_manifest": template_manifest, "subject_manifest": sfold,
            "profiles_audit_only": profiles, "naturalistic": natural, "controlled": controlled,
            "history_manifest": history, "observed_inputs": observed, "validation": report}


def main() -> None:
    first = build()
    second = build()
    first_hash = sim.canonical_hash(first)
    if first_hash != sim.canonical_hash(second):
        raise AssertionError("Same seed/config is not fully reproducible")
    first["validation"]["same_seed_reproducibility"] = "PASS"
    first["validation"]["reproducibility_hash"] = first_hash
    OUT.mkdir(parents=True, exist_ok=True)
    for key, filename in (("validation", "validation.json"), ("template_manifest", "template_manifest.json"),
                          ("subject_manifest", "subject_manifest.json"), ("profiles_audit_only", "profiles_audit_only.json"),
                          ("naturalistic", "naturalistic.json"), ("controlled", "controlled.json"),
                          ("history_manifest", "history_manifest.json"),
                          ("observed_inputs", "observed_inputs.json")):
        (OUT / filename).write_text(json.dumps(first[key], ensure_ascii=False, indent=2, sort_keys=True,
                                               allow_nan=False), encoding="utf-8")
    (OUT / "config_and_hashes.json").write_text(json.dumps({k: first[k] for k in
        ("seed", "config", "locks")}, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    report = first["validation"]
    print(json.dumps({"status": report["status"], "template_intersections": report["template_intersections"],
                      "subject_intersections": report["subject_intersections"],
                      "session_intersections": report["session_intersections"],
                      "source_subject_intersections": report["source_subject_intersections"],
                      "naturalistic_overall": report["naturalistic_overall"],
                      "controlled_evaluation": report["controlled"]["evaluation"],
                      "identification_audit": report["controlled"]["identification_audit"],
                      "reproducibility": report["same_seed_reproducibility"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
