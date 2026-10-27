"""Audit-only separation of reporting-style and noiseless-state information in Phase 1."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

import simulator_rq1_longitudinal_v2 as sim
import audit_rq1_longitudinal_v2_recoverability as audit
from run_rq1_longitudinal_v2_phase1 import SEEDS, KS, TARGETS, complete_target_history, feature_keys

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "artifacts" / "rq1_longitudinal_v2_phase1_corrected"
MODES = ("current", "sensor_context", "self_report", "full")


def mean_ci(values):
    a = np.asarray(values, float); mean = float(a.mean()); sd = float(a.std(ddof=1))
    half = 2.7764451051977987 * sd / math.sqrt(len(a))
    return {"mean": mean, "sd": sd, "ci95": [mean-half, mean+half]}


def main():
    per_seed = {}
    for seed in SEEDS:
        data = sim.generate(seed, "BASE")
        per_seed[str(seed)] = {}
        for k in KS:
            rows = complete_target_history(data, sim.history_features(data, k), k)
            per_seed[str(seed)][str(k)] = {}
            for target in TARGETS:
                usable = [r for r in rows if r["targets"].get(target) is not None]
                y = np.asarray([r["audit_true"]["noiseless_targets"][target] for r in usable], float)
                per_seed[str(seed)][str(k)][target] = {
                    mode: audit._fit(usable, feature_keys(usable[0], mode, target), y) for mode in MODES
                }
    summary = {}
    for target in TARGETS:
        summary[target] = {}
        base = [per_seed[str(s)]["0"][target]["current"]["mae"] for s in SEEDS]
        for k in KS:
            summary[target][str(k)] = {}
            for mode in MODES:
                vals = [per_seed[str(s)][str(k)][target][mode]["mae"] for s in SEEDS]
                diffs = [b-v for b, v in zip(base, vals)]
                summary[target][str(k)][mode] = {"mae": mean_ci(vals), "k0_current_minus_model": mean_ci(diffs),
                                                  "improved_seeds": sum(d > 0 for d in diffs)}
    result = {"version": "rq1-longitudinal-v2-phase1-information-path-audit-01", "seeds": list(SEEDS),
              "history_lengths": list(KS), "target_source": "audit-only noiseless subjective state",
              "per_seed": per_seed, "summary": summary}
    (OUT / "information_path_audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({t: {k: summary[t][k]["full"] for k in ("0", "5", "20", "100")} for t in TARGETS}, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
