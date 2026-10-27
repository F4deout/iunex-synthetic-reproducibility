"""Preregistered v2.3 Phase 1: state scores and censored performance endpoints."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

import simulator_v22_multi_activity as v22
import simulator_v23_task_capacity as v23
from run_v22_multi_activity_phase1 import Prep, fit_ridge, predict, metric, ci, workload_values
from validate_v23_evaluation_support import MARCH, CIRCUIT

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "artifacts" / "v23_phase1"
SEEDS = [110, 220, 330, 440, 550]
KS = [0, 1, 3, 5, 10, 20]
SCOPES = ["pooled", "LOADED_MARCH", "BODYWEIGHT_CIRCUIT"]
TARGETS = ["burden_WEAK", "burden_BASE", "burden_STRONG", "fatigue", "condition"]
GRID = [.1, 1., 10.]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(seed: int) -> dict:
    old_events, old_gap = v22._events, v22._gap_minutes

    def events(params, subject_id):
        cal = [e for e in old_events(params, subject_id) if e["phase"] == "CALIBRATION"]
        m = [{"activity": "LOADED_MARCH", "phase": "EVALUATION", "row": row} for row in MARCH]
        c = [{"activity": "BODYWEIGHT_CIRCUIT", "phase": "EVALUATION", "row": row} for row in CIRCUIT]
        ev = [x for pair in zip(m, c) for x in pair]
        if v22._parity(subject_id):
            ev = list(reversed(ev))
        return cal + ev

    def gap(event, previous, params):
        return 72. * 60 if event["phase"] == "EVALUATION" else old_gap(event, previous, params)

    v22._events, v22._gap_minutes = events, gap
    try:
        return v23.generate(seed)
    finally:
        v22._events, v22._gap_minutes = old_events, old_gap


def history(rows, activity):
    if not rows:
        return [np.nan] * 17
    pre = np.array([r["vitals"]["pre"]["hr_bpm"] for r in rows])
    post = np.array([r["vitals"]["post"]["hr_bpm"] for r in rows])
    ratio = np.array([r["actual_duration_min"] / r["planned_duration_min"] for r in rows])
    stopped = [r["actual_duration_min"] for r in rows if not r["completed"]]
    w = np.array([workload_values(r) for r in rows])
    wx = w[:, :3] if activity == "LOADED_MARCH" else w[:, 3:]
    return [len(rows), np.mean([r["completed"] for r in rows]), ratio.mean(),
            ratio.std(ddof=1) if len(rows) > 1 else 0., np.mean(stopped) if stopped else np.nan,
            pre.mean(), post.mean(), (post-pre).mean(), (post-pre).std(ddof=1) if len(rows) > 1 else 0.,
            np.mean([r["recovery_interval_min"] for r in rows]), float(rows[-1]["completed"]), ratio[-1],
            *wx.mean(0).tolist(), float(np.std(post-pre)), float(np.std(pre))]


def make_rows(data, k, scope, endpoint):
    by = defaultdict(list)
    for r in data["observed"]:
        by[r["subject_id"]].append(r)
    out = []
    for sid, records in by.items():
        records.sort(key=lambda r: r["sequence"])
        cal = [r for r in records if r["phase"] == "CALIBRATION"]
        for cur in [r for r in records if r["phase"] == "EVALUATION"]:
            if scope != "pooled" and cur["activity_type"] != scope:
                continue
            if endpoint == "state" and not cur["completed"]:
                continue
            w = workload_values(cur)
            x = [float(cur["activity_type"] == "LOADED_MARCH"), cur["planned_duration_min"],
                 cur["recovery_interval_min"], cur["vitals"]["pre"]["hr_bpm"], *w]
            if endpoint == "state":
                x += [cur["actual_duration_min"], float(cur["completed"]), cur["vitals"]["post"]["hr_bpm"]]
            if k:
                common = cal[-k:]
                same = [r for r in cal if r["activity_type"] == cur["activity_type"]][-k:]
                x += history(common, cur["activity_type"]) + history(same, cur["activity_type"])
            out.append({"subject_id": sid, "session_id": cur["session_id"], "fold": cur["fold"],
                        "activity": cur["activity_type"], "x": x, "targets": cur["targets"],
                        "completed": cur["completed"], "event": not cur["completed"],
                        "time": cur["actual_duration_min"], "planned": cur["planned_duration_min"]})
    return out


def fit_logistic(x, y, c):
    X = np.column_stack((np.ones(len(x)), x)); y = np.asarray(y, float)
    b = np.zeros(X.shape[1]); penalty = np.r_[0., np.repeat(1/c, X.shape[1]-1)]
    for _ in range(60):
        p = 1 / (1 + np.exp(-np.clip(X@b, -30, 30)))
        w = np.maximum(p*(1-p), 1e-6)
        h = X.T@(X*w[:,None]) + np.diag(penalty)
        step = np.linalg.solve(h, X.T@(p-y) + penalty*b)
        b -= step
        if np.max(np.abs(step)) < 1e-8: break
    return b


def logistic_predict(b, x):
    X = np.column_stack((np.ones(len(x)), x))
    return 1 / (1 + np.exp(-np.clip(X@b, -30, 30)))


def classification_metric(y, p):
    y=np.asarray(y,bool); p=np.clip(np.asarray(p,float),1e-9,1-1e-9)
    pos=p[y];neg=p[~y]
    auc=float(np.mean(pos[:,None]>neg[None,:])+.5*np.mean(pos[:,None]==neg[None,:])) if len(pos) and len(neg) else None
    return {"brier":float(np.mean((p-y)**2)),"logloss":float(-np.mean(y*np.log(p)+(1-y)*np.log(1-p))),"auc":auc}


def _sf(z):
    return np.maximum(np.array([.5*math.erfc(float(v)/math.sqrt(2)) for v in np.ravel(z)]).reshape(np.shape(z)),1e-12)


def aft_nll(theta,x,t,event,alpha):
    X=np.column_stack((np.ones(len(x)),x)); beta=theta[:-1]; ls=float(np.clip(theta[-1],-3,3)); sigma=math.exp(ls)
    z=(np.log(t)-X@beta)/sigma; e=np.asarray(event,bool)
    terms=np.empty(len(t)); terms[e]=ls+.5*z[e]**2+.5*math.log(2*math.pi); terms[~e]=-np.log(_sf(z[~e]))
    return float(terms.mean()+alpha*np.sum(beta[1:]**2)/(2*len(t)))


def fit_aft(x,t,event,alpha):
    X=np.column_stack((np.ones(len(x)),x)); y=np.log(t); e=np.asarray(event,bool)
    beta=np.zeros(X.shape[1]); beta[0]=float(np.mean(y)); ls=float(np.log(max(np.std(y),.2)))
    mb=np.zeros_like(beta);vb=np.zeros_like(beta);ml=vl=0.; lr=.03
    for it in range(1,1201):
        sigma=math.exp(np.clip(ls,-3,3)); z=(y-X@beta)/sigma
        dmu=np.empty(len(y)); dls=np.empty(len(y))
        dmu[e]=-z[e]/sigma; dls[e]=1-z[e]**2
        sf=_sf(z[~e]); phi=np.exp(-.5*z[~e]**2)/math.sqrt(2*math.pi); mills=np.minimum(phi/sf,50)
        dmu[~e]=-mills/sigma; dls[~e]=-mills*z[~e]
        gb=X.T@dmu/len(y); gb[1:]+=alpha*beta[1:]/len(y); gl=float(np.mean(dls))
        mb=.9*mb+.1*gb;vb=.999*vb+.001*gb**2;ml=.9*ml+.1*gl;vl=.999*vl+.001*gl**2
        beta-=lr*(mb/(1-.9**it))/(np.sqrt(vb/(1-.999**it))+1e-8)
        ls-=lr*(ml/(1-.9**it))/(math.sqrt(vl/(1-.999**it))+1e-8);ls=float(np.clip(ls,-3,3))
    return np.r_[beta,ls]


def aft_predict(theta,x):
    X=np.column_stack((np.ones(len(x)),x)); return np.exp(X@theta[:-1])


def cindex(t,event,pred):
    c=n=0.;t=np.asarray(t);e=np.asarray(event,bool);pred=np.asarray(pred)
    for i in np.where(e)[0]:
        valid=np.where(t>t[i])[0];n+=len(valid);c+=np.sum(pred[i]<pred[valid])+.5*np.sum(pred[i]==pred[valid])
    return float(c/n) if n else None


def run_state(rows,target):
    folds=np.array([r["fold"] for r in rows]);x=np.array([r["x"] for r in rows]);y=np.array([r["targets"][target] for r in rows])
    tr,va,te=folds=="train",folds=="validation",folds=="test";prep=Prep().fit(x[tr]);zt,zv,ze=map(prep.transform,(x[tr],x[va],x[te]))
    alpha=min((metric(y[va],predict(fit_ridge(zt,y[tr],a),zv))["mae"],a) for a in GRID)[1]
    model=fit_ridge(np.vstack((zt,zv)),np.r_[y[tr],y[va]],alpha);pred=predict(model,ze)
    return metric(y[te],pred)|{"alpha":alpha,"n_test":int(te.sum())}, [(rows[i]["session_id"],y[i],pred[j]) for j,i in enumerate(np.where(te)[0])]


def run_performance(rows):
    folds=np.array([r["fold"] for r in rows]);x=np.array([r["x"] for r in rows]);event=np.array([r["event"] for r in rows]);t=np.array([r["time"] for r in rows])
    tr,va,te=folds=="train",folds=="validation",folds=="test";prep=Prep().fit(x[tr]);zt,zv,ze=map(prep.transform,(x[tr],x[va],x[te]))
    c=min((classification_metric(event[va],logistic_predict(fit_logistic(zt,event[tr],c),zv))["logloss"],c) for c in GRID)[1]
    logit=fit_logistic(np.vstack((zt,zv)),np.r_[event[tr],event[va]],c);prob=logistic_predict(logit,ze);cm=classification_metric(event[te],prob)
    alpha=min((aft_nll(fit_aft(zt,t[tr],event[tr],a),zv,t[va],event[va],a),a) for a in GRID)[1]
    aft=fit_aft(np.vstack((zt,zv)),np.r_[t[tr],t[va]],np.r_[event[tr],event[va]],alpha);ptime=aft_predict(aft,ze)
    am={"nll":aft_nll(aft,ze,t[te],event[te],alpha),"cindex":cindex(t[te],event[te],ptime),
        "stopped_mae":float(np.mean(np.abs(t[te][event[te]]-ptime[event[te]]))) if np.any(event[te]) else None,
        "n_test":int(te.sum()),"n_stopped":int(event[te].sum()),"alpha":alpha,"logistic_c":c}
    pred=[(rows[i]["session_id"],bool(event[i]),t[i],prob[j],ptime[j]) for j,i in enumerate(np.where(te)[0])]
    return cm|am,pred


def summarize(runs,key,metric_name,higher_better=False):
    grouped=defaultdict(list)
    for r in runs: grouped[(r["scope"],r[key],r["k"])].append(r)
    out=[]
    for (scope,name,k),items in grouped.items():
        vals=[r[metric_name] for r in sorted(items,key=lambda z:z["seed"]) if r[metric_name] is not None]
        base=sorted(grouped[(scope,name,0)],key=lambda z:z["seed"])
        cur=sorted(items,key=lambda z:z["seed"])
        diffs=[(x[metric_name]-b[metric_name] if higher_better else b[metric_name]-x[metric_name])
               for b,x in zip(base,cur) if b[metric_name] is not None and x[metric_name] is not None]
        out.append({"scope":scope,key:name,"k":k,metric_name:ci(vals),"k0_minus_k":ci(diffs),"improved_seeds":sum(d>0 for d in diffs)})
    return out


def main():
    freeze=json.loads((ROOT/"SIMULATOR_V23_PHASE1_FREEZE.json").read_text(encoding="utf-8-sig"))
    if sha(ROOT/"SIMULATOR_V23_PHASE1_PROTOCOL.md")!=freeze["phase1_protocol_sha256"]: raise RuntimeError("protocol changed")
    OUT.mkdir(parents=True,exist_ok=True);state_runs=[];perf_runs=[];state_pred=[];perf_pred=[];hashes={}
    for seed in SEEDS:
        data=build(seed);hashes[str(seed)]=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
        for scope in SCOPES:
            for k in KS:
                sr=make_rows(data,k,scope,"state");pr=make_rows(data,k,scope,"performance")
                for target in TARGETS:
                    m,p=run_state(sr,target);state_runs.append({"seed":seed,"scope":scope,"k":k,"target":target,**m})
                    state_pred += [{"seed":seed,"scope":scope,"k":k,"target":target,"session_id":sid,"actual":float(y),"prediction":float(q)} for sid,y,q in p]
                m,p=run_performance(pr);perf_runs.append({"seed":seed,"scope":scope,"k":k,"endpoint":"performance",**m})
                perf_pred += [{"seed":seed,"scope":scope,"k":k,"session_id":sid,"stopped":event,"observed_time":float(t),"stop_probability":float(prob),"aft_median_time":float(pt)} for sid,event,t,prob,pt in p]
    result={"status":"COMPLETE","seeds":SEEDS,"k":KS,
            "state_summary":summarize(state_runs,"target","mae"),
            "performance_brier_summary":summarize(perf_runs,"endpoint","brier"),
            "performance_nll_summary":summarize(perf_runs,"endpoint","nll"),
            "performance_cindex_summary":summarize(perf_runs,"endpoint","cindex",True),
            "state_runs":state_runs,"performance_runs":perf_runs,"data_hashes":hashes,
            "limitations":["synthetic endpoints","stopped-only MAE is descriptive","45/90-minute grid is not a human test recommendation"]}
    (OUT/"results.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    for name,rows in (("state_predictions.csv",state_pred),("performance_predictions.csv",perf_pred)):
        with (OUT/name).open("w",newline="",encoding="utf-8-sig") as f:
            w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    manifest={"protocol_freeze":sha(ROOT/"SIMULATOR_V23_PHASE1_FREEZE.json"),"analysis":sha(Path(__file__)),
              "generator":sha(ROOT/"simulator_v23_task_capacity.py"),"results":sha(OUT/"results.json"),
              "state_predictions":sha(OUT/"state_predictions.csv"),"performance_predictions":sha(OUT/"performance_predictions.csv"),
              "v22_phase1":sha(ROOT/"artifacts/v22_multi_activity_phase1/results.json")}
    (OUT/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(json.dumps({"status":"COMPLETE","state_runs":len(state_runs),"performance_runs":len(perf_runs)},indent=2))


if __name__=="__main__": main()
