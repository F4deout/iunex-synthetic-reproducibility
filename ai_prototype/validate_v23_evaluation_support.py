"""Build and validate the separately preregistered v2.3 evaluation-support grid."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

import simulator_v22_multi_activity as v22
import simulator_v23_task_capacity as v23

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "artifacts" / "synthetic_v23_evaluation_support"
SEEDS = [110, 220, 330, 440, 550]
MARCH = [["MS1", 4.5, .2, 0., 20.], ["MS2", 5.5, .4, 5., 20.],
         ["MS3", 5.5, .4, 5., 45.], ["MS4", 5.5, .4, 5., 90.]]
CIRCUIT = [["BS1", 20., 20., 14.], ["BS2", 30., 5., 14.],
           ["BS3", 30., 5., 45.], ["BS4", 30., 5., 90.]]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(seed: int) -> dict:
    old_events, old_gap = v22._events, v22._gap_minutes

    def events(_params, subject_id):
        m = [{"activity": "LOADED_MARCH", "phase": "EVALUATION", "row": row} for row in MARCH]
        c = [{"activity": "BODYWEIGHT_CIRCUIT", "phase": "EVALUATION", "row": row} for row in CIRCUIT]
        rows = [x for pair in zip(m, c) for x in pair]
        return rows if v22._parity(subject_id) == 0 else list(reversed(rows))

    def gap(_event, previous, _params):
        return 72.0 * 60.0 if previous else 0.0

    v22._events, v22._gap_minutes = events, gap
    try:
        return v23.generate(seed)
    finally:
        v22._events, v22._gap_minutes = old_events, old_gap


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = {seed: build(seed) for seed in SEEDS}
    reproducible = json.dumps(data[110], sort_keys=True) == json.dumps(build(110), sort_keys=True)
    rows = []
    for seed, d in data.items():
        amap = {r["session_id"]: r for r in d["audit"]}
        for o in d["observed"]:
            a = amap[o["session_id"]]
            rows.append({"seed": seed, "subject_id": o["subject_id"], "fold": o["fold"],
                         "session_id": o["session_id"], "activity": o["activity_type"], "event": o["event_code"],
                         "completed": o["completed"], "planned": o["planned_duration_min"],
                         "actual": o["actual_duration_min"], "capacity": a["capacity"],
                         "tolerance": a["tolerance"], "relative": a["relative_demand"]})

    event_support = {}
    for event in [r[0] for r in MARCH + CIRCUIT]:
        x = [r for r in rows if r["event"] == event]
        by_seed = {seed: float(np.mean([r["completed"] for r in x if r["seed"] == seed])) for seed in SEEDS}
        rate = float(np.mean([r["completed"] for r in x]))
        event_support[event] = {"activity": x[0]["activity"], "n": len(x), "completion_rate": rate,
                                "completed": int(sum(r["completed"] for r in x)),
                                "stopped": int(sum(not r["completed"] for r in x)),
                                "seed_completion_rate": by_seed,
                                "actual_stop_min": ({"mean": float(np.mean([r["actual"] for r in x if not r["completed"]])),
                                                     "p05": float(np.quantile([r["actual"] for r in x if not r["completed"]], .05)),
                                                     "p95": float(np.quantile([r["actual"] for r in x if not r["completed"]], .95))}
                                                    if any(not r["completed"] for r in x) else None)}

    activity_support = {}
    for activity in ("LOADED_MARCH", "BODYWEIGHT_CIRCUIT"):
        events = [v for v in event_support.values() if v["activity"] == activity]
        mixed = [v for v in events if 0 < v["completion_rate"] < 1]
        activity_support[activity] = {"mixed_events": len(mixed), "status": "SUPPORTED" if mixed else "NOT_SUPPORTED"}

    split_ok = True
    for seed in SEEDS:
        groups = {f: {r["subject_id"] for r in rows if r["seed"] == seed and r["fold"] == f}
                  for f in ("train", "validation", "test")}
        split_ok &= not (groups["train"] & groups["validation"] or groups["train"] & groups["test"] or groups["validation"] & groups["test"])
    duration_ok = all((r["completed"] and abs(r["actual"] - r["planned"]) < 1e-9) or
                      ((not r["completed"]) and r["actual"] < r["planned"]) for r in rows)
    unique_ok = len({(r["seed"], r["session_id"]) for r in rows}) == len(rows)
    observed_keys = set().union(*(r.keys() for d in data.values() for r in d["observed"]))
    leakage_ok = not ({"capacity", "tolerance", "reserve", "strain", "debt", "hypothetical_limit"} & observed_keys)
    support_ok = all(v["status"] == "SUPPORTED" for v in activity_support.values())
    checks = {"reproducibility": reproducible, "subject_split": split_ok, "unique_session": unique_ok,
              "completion_duration_consistency": duration_ok, "latent_observed_leakage": leakage_ok,
              "both_activities_have_mixed_completion": support_ok}
    status = "EXPERIMENT_READY" if all(checks.values()) else "FIX_REQUIRED"
    result = {"status": status, "checks": checks, "grid": {"march": MARCH, "circuit": CIRCUIT},
              "event_support": event_support, "activity_support": activity_support,
              "interpretation": "synthetic evaluation support only; not a safe human protocol or military performance estimate"}
    (OUT / "validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# v2.3 evaluation-support validation", "", f"Final: **{status}**", "",
             *[f"- {k}: {'PASS' if v else 'FAIL'}" for k, v in checks.items()], "",
             "| Event | Activity | Completion | Completed | Stopped | Stop time mean [p05, p95] min |",
             "|---|---|---:|---:|---:|---:|"]
    for event, x in event_support.items():
        stop = "—" if x["actual_stop_min"] is None else f"{x['actual_stop_min']['mean']:.2f} [{x['actual_stop_min']['p05']:.2f}, {x['actual_stop_min']['p95']:.2f}]"
        lines.append(f"| {event} | {x['activity']} | {x['completion_rate']:.3f} | {x['completed']} | {x['stopped']} | {stop} |")
    lines += ["", "This grid is an identifiability audit for a synthetic endpoint. It is not a recommended test for people."]
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {"amendment_freeze": sha(ROOT / "SIMULATOR_V23_EVALUATION_SUPPORT_FREEZE.json"),
                "builder_validator": sha(Path(__file__)), "v23_generator": sha(ROOT / "simulator_v23_task_capacity.py"),
                "validation": sha(OUT / "validation.json"), "report": sha(OUT / "REPORT.md"),
                "v22_phase1": sha(ROOT / "artifacts/v22_multi_activity_phase1/results.json")}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"status": status, "checks": checks, "activity_support": activity_support,
                      "event_support": event_support}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
