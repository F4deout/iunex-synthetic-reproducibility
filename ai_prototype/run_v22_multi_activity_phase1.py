"""Preregistered v2.2 Phase 1 history experiment."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

from simulator_v22_multi_activity import generate

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "artifacts/v22_multi_activity_phase1"
SEEDS = [110, 220, 330, 440, 550]
KS = [0, 1, 3, 5, 10, 20]
TARGETS = ["burden_WEAK", "burden_BASE", "burden_STRONG", "fatigue", "condition"]
ALPHAS = [.1, 1.0, 10.0]
AMENDMENT_HASH = "8134a3094be0bc67bda06ca5aa0f6412f362444e32c58a655f51bf6251d2a881"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workload_values(r):
    if r["activity_type"] == "LOADED_MARCH":
        w = r["workload"]
        return [w["actual_speed_kmh"], w["carried_load_kg"]/w["body_mass_kg"], w["grade_pct"], 0., 0., 0.]
    ex = r["workload"]["exercises"][0]
    density = ex["work_sec"]/(ex["work_sec"]+ex["rest_sec"])
    return [0., 0., 0., ex["work_sec"], ex["rest_sec"], density]


def history_summary(rows, activity):
    if not rows:
        return [np.nan] * 14
    pre = np.array([r["vitals"]["pre"]["hr_bpm"] for r in rows])
    post = np.array([r["vitals"]["post"]["hr_bpm"] for r in rows])
    delta = post-pre
    actual = np.array([r["actual_duration_min"] for r in rows])
    gap = np.array([r["recovery_interval_min"] for r in rows])
    base = [len(rows), np.mean([r["completed"] for r in rows]), pre.mean(), post.mean(), delta.mean(),
            delta.std(ddof=1) if len(rows)>1 else 0., actual.mean(), actual.std(ddof=1) if len(rows)>1 else 0.,
            gap.mean(), delta[-1], float(rows[-1]["completed"])]
    w = np.array([workload_values(r) for r in rows])
    extra = w[:, :3].mean(0) if activity == "LOADED_MARCH" else w[:, 3:].mean(0)
    return base + extra.tolist()


def make_rows(data, k, scope):
    by_subject = defaultdict(list)
    for r in data["observed"]: by_subject[r["subject_id"]].append(r)
    result = []
    for sid, rows in by_subject.items():
        rows.sort(key=lambda r:r["sequence"])
        calibration = [r for r in rows if r["phase"] == "CALIBRATION"]
        for current in (r for r in rows if r["phase"] == "EVALUATION" and r["completed"]):
            if scope != "pooled" and current["activity_type"] != scope: continue
            w = workload_values(current)
            x = [float(current["activity_type"] == "LOADED_MARCH"), current["planned_duration_min"],
                 current["actual_duration_min"], current["recovery_interval_min"],
                 current["vitals"]["pre"]["hr_bpm"], current["vitals"]["post"]["hr_bpm"]] + w
            if k:
                prior = [r for r in calibration if r["sequence"] < current["sequence"]]
                common = prior[-k:]
                same = [r for r in prior if r["activity_type"] == current["activity_type"]][-k:]
                common_stats = history_summary(common, current["activity_type"])
                same_stats = history_summary(same, current["activity_type"])
                x += common_stats[:11] + same_stats
            result.append({"subject_id":sid,"session_id":current["session_id"],"fold":current["fold"],
                           "activity":current["activity_type"],"x":x,"targets":current["targets"]})
    return result


class Prep:
    def fit(self, x):
        x=np.asarray(x,float)
        self.keep_nonempty=~np.all(np.isnan(x),axis=0)
        x=x[:,self.keep_nonempty]
        self.median=np.nanmedian(x,axis=0)
        x=np.where(np.isnan(x),self.median,x)
        self.keep_variable=x.std(0)>1e-12
        x=x[:,self.keep_variable]
        self.mean=x.mean(0); self.sd=x.std(0); self.sd[self.sd==0]=1
        return self
    def transform(self,x):
        x=np.asarray(x,float)[:,self.keep_nonempty]
        x=np.where(np.isnan(x),self.median,x)[:,self.keep_variable]
        return (x-self.mean)/self.sd


def fit_ridge(x,y,alpha):
    y=np.asarray(y,float); ym=float(y.mean())
    coef=np.linalg.solve(x.T@x+alpha*np.eye(x.shape[1]),x.T@(y-ym))
    return ym,coef


def predict(model,x): return model[0]+x@model[1]


def metric(y,p):
    y=np.asarray(y);p=np.asarray(p);den=np.sum((y-y.mean())**2)
    return {"mae":float(np.mean(np.abs(y-p))),"rmse":float(np.sqrt(np.mean((y-p)**2))),
            "r2":float(1-np.sum((y-p)**2)/den) if den else None}


def run_one(rows,target):
    folds=np.array([r["fold"] for r in rows]); x=np.array([r["x"] for r in rows]); y=np.array([r["targets"][target] for r in rows])
    tr,va,te=folds=="train",folds=="validation",folds=="test"
    prep=Prep().fit(x[tr]); ztr,zva,zte=map(prep.transform,(x[tr],x[va],x[te]))
    scored=[]
    for a in ALPHAS:
        m=fit_ridge(ztr,y[tr],a); scored.append((metric(y[va],predict(m,zva))["mae"],a))
    alpha=min(scored)[1]
    model=fit_ridge(np.vstack((ztr,zva)),np.concatenate((y[tr],y[va])),alpha)
    pred=predict(model,zte); ids=[rows[i]["session_id"] for i in np.where(te)[0]]
    return metric(y[te],pred)|{"alpha":alpha,"n_test":int(te.sum())}, list(zip(ids,y[te],pred))


def ci(values):
    a=np.array(values,float); mean=float(a.mean()); sd=float(a.std(ddof=1)); half=2.776*sd/math.sqrt(len(a))
    return {"mean":mean,"sd":sd,"ci95_low":mean-half,"ci95_high":mean+half}


def main():
    if sha(ROOT/"SIMULATOR_V22_MULTI_ACTIVITY_AMENDMENT_05.md") != AMENDMENT_HASH:
        raise RuntimeError("Phase 1 amendment hash mismatch")
    OUT.mkdir(parents=True,exist_ok=True)
    runs=[]; predictions=[]; data_hashes={}
    for seed in SEEDS:
        data=generate(seed=seed)
        data_hashes[str(seed)]=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
        for scope in ("pooled","LOADED_MARCH","BODYWEIGHT_CIRCUIT"):
            for k in KS:
                rows=make_rows(data,k,scope)
                test_ids=sorted(r["session_id"] for r in rows if r["fold"]=="test")
                for target in TARGETS:
                    m,preds=run_one(rows,target)
                    runs.append({"seed":seed,"scope":scope,"k":k,"target":target,**m,"test_ids_hash":hashlib.sha256("\n".join(test_ids).encode()).hexdigest()})
                    predictions += [{"seed":seed,"scope":scope,"k":k,"target":target,"session_id":sid,"actual":float(y),"prediction":float(pr)} for sid,y,pr in preds]
    grouped=defaultdict(list)
    for r in runs: grouped[(r["scope"],r["target"],r["k"])].append(r)
    summaries=[]
    for (scope,target,k),items in grouped.items():
        s={metric_name:ci([r[metric_name] for r in items]) for metric_name in ("mae","rmse","r2")}
        base=grouped[(scope,target,0)]
        diff=[b["mae"]-r["mae"] for b,r in zip(sorted(base,key=lambda x:x["seed"]),sorted(items,key=lambda x:x["seed"]))]
        summaries.append({"scope":scope,"target":target,"k":k,**s,"k0_minus_k_mae":ci(diff),
                          "improved_seeds":sum(d>0 for d in diff),"seed_directions":["improved" if d>0 else "worse" if d<0 else "equal" for d in diff]})
    # Same evaluation sessions across k, checked per seed/scope.
    session_check=True
    for seed in SEEDS:
        for scope in ("pooled","LOADED_MARCH","BODYWEIGHT_CIRCUIT"):
            hashes={r["test_ids_hash"] for r in runs if r["seed"]==seed and r["scope"]==scope}
            session_check &= len(hashes)==1
    result={"status":"COMPLETE" if session_check else "FAIL","seeds":SEEDS,"k":KS,
            "same_test_sessions_across_k":bool(session_check),"summaries":summaries,"runs":runs,
            "data_hashes":data_hashes,"limitations":["synthetic activities; not actual soldier performance","current data do not empirically calibrate loaded-march or circuit parameters"]}
    (OUT/"results.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    with (OUT/"raw_predictions.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=predictions[0].keys());w.writeheader();w.writerows(predictions)
    manifest={"amendment_sha256":AMENDMENT_HASH,"generator_sha256":sha(ROOT/"simulator_v22_multi_activity.py"),
              "analysis_sha256":sha(Path(__file__)),"parameter_sha256":sha(ROOT/"SIMULATOR_V22_MULTI_ACTIVITY_PARAMETERS.json"),
              "results_sha256":sha(OUT/"results.json"),"predictions_sha256":sha(OUT/"raw_predictions.csv")}
    (OUT/"artifact_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(json.dumps({"status":result["status"],"same_test_sessions_across_k":session_check,"n_runs":len(runs),"n_predictions":len(predictions)},indent=2))


if __name__=="__main__": main()
