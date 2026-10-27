"""Preregistered method correction: imbalance audit and bounded discrete-time survival."""
from __future__ import annotations

import csv, hashlib, json, math
from collections import defaultdict
from pathlib import Path

import numpy as np

from run_v22_multi_activity_phase1 import Prep, ci
from run_v23_phase1 import ROOT, SEEDS, KS, SCOPES, GRID, build, make_rows, fit_logistic, logistic_predict, cindex

OUT=ROOT/"artifacts/v23_phase1_methodfix"


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def average_precision(y,p):
    y=np.asarray(y,bool);p=np.asarray(p);order=np.argsort(-p);ys=y[order]
    return float(np.sum((np.cumsum(ys)/np.arange(1,len(ys)+1))*ys)/ys.sum()) if ys.sum() else None


def metrics(y,p,threshold=.5):
    y=np.asarray(y,bool);p=np.clip(np.asarray(p,float),1e-9,1-1e-9);pred=p>=threshold
    pos=p[y];neg=p[~y];auc=float(np.mean(pos[:,None]>neg[None,:])+.5*np.mean(pos[:,None]==neg[None,:])) if len(pos) and len(neg) else None
    tpr=float(np.mean(pred[y])) if y.any() else None;tnr=float(np.mean(~pred[~y])) if (~y).any() else None
    bins=np.minimum((p*10).astype(int),9);ece=sum(np.mean(bins==b)*abs(np.mean(p[bins==b])-np.mean(y[bins==b])) for b in range(10) if np.any(bins==b))
    return {"brier":float(np.mean((p-y)**2)),"logloss":float(-np.mean(y*np.log(p)+(1-y)*np.log(1-p))),
            "auc":auc,"pr_auc":average_precision(y,p),"balanced_accuracy":float((tpr+tnr)/2),
            "ece10":float(ece),"predicted_rate":float(p.mean()),"observed_rate":float(y.mean())}


def choose_threshold(y,p):
    return max(np.arange(.05,1,.05),key=lambda t:metrics(y,p,t)["balanced_accuracy"])


def intervals(limit):
    x=list(np.arange(5.,limit,5.));x.append(float(limit));return np.array(x)


def expand(x,t,event):
    xx=[];yy=[]
    for features,limit,e in zip(x,t,event):
        ends=intervals(limit)
        for j,end in enumerate(ends):
            xx.append(np.r_[features,end/90.,math.log1p(end)/math.log(91.)]);yy.append(bool(e and j==len(ends)-1))
    return np.asarray(xx),np.asarray(yy,bool)


def hazard_curve(model,features,endpoints):
    x=np.array([np.r_[features,e/90.,math.log1p(e)/math.log(91.)] for e in endpoints])
    return logistic_predict(model,x)


def survival_predictions(model,x,planned):
    stop_prob=[];rmst=[]
    grid=np.arange(5.,91.,5.)
    for feat,limit in zip(x,planned):
        h=hazard_curve(model,feat,intervals(limit));stop_prob.append(1-float(np.prod(1-h)))
        hg=hazard_curve(model,feat,grid);surv=np.r_[1.,np.cumprod(1-hg)[:-1]];rmst.append(float(np.sum(surv*5.)))
    return np.asarray(stop_prob),np.asarray(rmst)


def run(rows):
    folds=np.array([r["fold"] for r in rows]);x=np.array([r["x"] for r in rows]);event=np.array([r["event"] for r in rows]);t=np.array([r["time"] for r in rows]);planned=np.array([r["planned"] for r in rows])
    tr,va,te=folds=="train",folds=="validation",folds=="test";prep=Prep().fit(x[tr]);zt,zv,ze=map(prep.transform,(x[tr],x[va],x[te]))
    # Session-level completion/stop classifier plus prevalence-only baseline.
    candidates=[]
    for c in GRID:
        m=fit_logistic(zt,event[tr],c);pv=logistic_predict(m,zv);candidates.append((metrics(event[va],pv)["logloss"],c,m,pv))
    _,c,_,pv=min(candidates,key=lambda q:q[0]);threshold=choose_threshold(event[va],pv)
    classifier=fit_logistic(np.vstack((zt,zv)),np.r_[event[tr],event[va]],c);prob=logistic_predict(classifier,ze)
    class_metric=metrics(event[te],prob,threshold)
    prevalence=float(event[tr].mean());base_metric=metrics(event[te],np.repeat(prevalence,te.sum()),.5)
    # Discrete-time hazard model.
    et,yt=expand(zt,t[tr],event[tr]);ev,yv=expand(zv,t[va],event[va])
    hc=min(((metrics(yv,logistic_predict(fit_logistic(et,yt,c),ev))["logloss"],c) for c in GRID),key=lambda q:q[0])[1]
    ea,ya=expand(np.vstack((zt,zv)),np.r_[t[tr],t[va]],np.r_[event[tr],event[va]])
    hazard=fit_logistic(ea,ya,hc);hprob,rmst=survival_predictions(hazard,ze,planned[te]);hazard_metric=metrics(event[te],hprob,.5)
    hazard_metric.update({"cindex":cindex(t[te],event[te],rmst),"stopped_rmst_mae":float(np.mean(np.abs(t[te][event[te]]-rmst[event[te]]))) if event[te].any() else None,
                          "rmst_min":float(rmst.min()),"rmst_max":float(rmst.max()),"hazard_c":hc})
    ids=[rows[i]["session_id"] for i in np.where(te)[0]]
    preds=[(sid,bool(e),float(tt),float(pp),float(hp),float(rt)) for sid,e,tt,pp,hp,rt in zip(ids,event[te],t[te],prob,hprob,rmst)]
    return {"classifier":class_metric,"prevalence_baseline":base_metric,"hazard":hazard_metric,
            "classifier_c":c,"threshold":float(threshold),"n_test":int(te.sum()),"n_stopped":int(event[te].sum())},preds


def summarize(runs,path,metric,higher=False):
    out=[]
    for scope in SCOPES:
        for k in KS:
            items=sorted([r for r in runs if r["scope"]==scope and r["k"]==k],key=lambda r:r["seed"])
            vals=[r[path][metric] for r in items];base=sorted([r for r in runs if r["scope"]==scope and r["k"]==0],key=lambda r:r["seed"])
            diffs=[(x[path][metric]-b[path][metric] if higher else b[path][metric]-x[path][metric]) for b,x in zip(base,items)]
            out.append({"scope":scope,"k":k,"metric":metric,"value":ci(vals),"k0_improvement":ci(diffs),"improved_seeds":sum(d>0 for d in diffs)})
    return out


def main():
    freeze=json.loads((ROOT/"SIMULATOR_V23_PHASE1_METHOD_FREEZE.json").read_text(encoding="utf-8-sig"))
    if sha(ROOT/"SIMULATOR_V23_PHASE1_METHOD_AMENDMENT_01.md")!=freeze["amendment_sha256"]:raise RuntimeError("amendment changed")
    OUT.mkdir(parents=True,exist_ok=True);runs=[];preds=[];hashes={}
    for seed in SEEDS:
        data=build(seed);hashes[str(seed)]=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
        for scope in SCOPES:
            for k in KS:
                rows=make_rows(data,k,scope,"performance");result,p=run(rows);runs.append({"seed":seed,"scope":scope,"k":k,**result})
                preds += [{"seed":seed,"scope":scope,"k":k,"session_id":sid,"stopped":event,"observed_time":time,
                           "classifier_stop_probability":prob,"hazard_stop_probability":hp,"rmst_0_90":rmst} for sid,event,time,prob,hp,rmst in p]
    result={"status":"METHOD_VALIDATED","runs":runs,"data_hashes":hashes,
            "classifier_brier":summarize(runs,"classifier","brier"),"classifier_pr_auc":summarize(runs,"classifier","pr_auc",True),
            "hazard_brier":summarize(runs,"hazard","brier"),"hazard_cindex":summarize(runs,"hazard","cindex",True),
            "limitations":["synthetic endpoints","RMST is restricted to 0-90 minutes","stopped-only RMST MAE is descriptive"]}
    (OUT/"results.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    with (OUT/"predictions.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=preds[0].keys());w.writeheader();w.writerows(preds)
    manifest={"method_freeze":sha(ROOT/"SIMULATOR_V23_PHASE1_METHOD_FREEZE.json"),"analysis":sha(Path(__file__)),
              "results":sha(OUT/"results.json"),"predictions":sha(OUT/"predictions.csv"),
              "old_phase1_results":sha(ROOT/"artifacts/v23_phase1/results.json")}
    (OUT/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(json.dumps({"status":"METHOD_VALIDATED","runs":len(runs)},indent=2))


if __name__=="__main__":main()
