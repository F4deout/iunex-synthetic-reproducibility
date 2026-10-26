"""Dry-run validation and frozen five-seed pre-task model experiment."""
from __future__ import annotations

import csv, gzip, hashlib, json, math
from pathlib import Path
import numpy as np
import simulator_pretask_model as sim

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"artifacts"/"pretask_model_phase1"
SEEDS=(110,220,330,440,550)
MODES=("current","sensor_history","self_report_history","performance_history","full")
TARGETS=("pre_fatigue","pre_condition","post_burden","recovery_delay")
ALPHAS=(1.,10.,100.)

def mae(y,p): return float(np.mean(np.abs(y-p)))
def rmse(y,p): return float(np.sqrt(np.mean((y-p)**2)))
def r2(y,p):
    d=float(np.sum((y-y.mean())**2)); return float(1-np.sum((y-p)**2)/d) if d else float("nan")
def ci(v):
    a=np.asarray(v,float); m=float(a.mean()); sd=float(a.std(ddof=1)); h=2.7764451051977987*sd/math.sqrt(len(a))
    return {"mean":m,"sd":sd,"ci95":[m-h,m+h]}

def keys(rows):
    forbidden=("target","latent","capacity","tolerance","debt","relative_demand","depletion","actual_duration","completed","stop_time","recovery_delay","post_burden")
    result=[]
    for k,v in rows[0].items():
        if k in {"session_id","subject_id","fold","session_index","task_type","targets","safety_gate"}: continue
        if not k.startswith("hist_") and any(x==k for x in forbidden): continue
        if isinstance(v,(int,float)) or v is None: result.append(k)
    for task in sim.TASKS: result.append("task_"+task)
    return result

def matrix(rows, feature_keys):
    X=[]
    for r in rows:
        line=[]
        for k in feature_keys:
            if k.startswith("task_"): line.append(float(r["task_type"]==k[5:]))
            else: line.append(np.nan if r.get(k) is None else float(r[k]))
        X.append(line)
    return np.asarray(X,float)

def transform_fit(X):
    med=np.nanmedian(X,axis=0); med=np.where(np.isfinite(med),med,0); Xi=np.where(np.isnan(X),med,X)
    mean=Xi.mean(axis=0); sd=Xi.std(axis=0); sd=np.where(sd<1e-9,1,sd)
    return (Xi-mean)/sd,(med,mean,sd)
def transform(X,state):
    med,mean,sd=state; return (np.where(np.isnan(X),med,X)-mean)/sd
def ridge(X,y,Xp,a):
    Xa=np.c_[np.ones(len(X)),X]; Xpa=np.c_[np.ones(len(Xp)),Xp]
    reg=np.eye(Xa.shape[1])*a; reg[0,0]=0
    return Xpa@np.linalg.solve(Xa.T@Xa+reg,Xa.T@y)
def logistic(X,y,Xp,a):
    Xa=np.c_[np.ones(len(X)),X]; Xpa=np.c_[np.ones(len(Xp)),Xp]; b=np.zeros(Xa.shape[1])
    for _ in range(80):
        z=np.clip(Xa@b,-30,30); p=1/(1+np.exp(-z)); w=np.clip(p*(1-p),1e-5,None)
        g=Xa.T@(p-y); g[1:]+=a*b[1:]
        H=Xa.T@(Xa*w[:,None]); H[1:,1:]+=a*np.eye(len(b)-1)
        step=np.linalg.solve(H+1e-7*np.eye(len(b)),g); b-=step
        if np.max(np.abs(step))<1e-7: break
    return 1/(1+np.exp(-np.clip(Xpa@b,-30,30)))
def auc(y,p):
    y=np.asarray(y); pos=np.sum(y==1); neg=np.sum(y==0)
    if not pos or not neg: return float("nan")
    order=np.argsort(p); ranks=np.empty(len(p)); ranks[order]=np.arange(1,len(p)+1)
    return float((ranks[y==1].sum()-pos*(pos+1)/2)/(pos*neg))

def fit_cont(rows,target,shuffle=False,feature_shuffle=False):
    fkeys=keys(rows); X=matrix(rows,fkeys); y=np.asarray([r["targets"][target] for r in rows],float); folds=np.asarray([r["fold"] for r in rows])
    if feature_shuffle: X=np.random.default_rng(991).permutation(X)
    yt=y.copy()
    if shuffle: yt[folds=="train"]=np.random.default_rng(992).permutation(yt[folds=="train"])
    best=None
    for a in ALPHAS:
        xt,state=transform_fit(X[folds=="train"]); xv=transform(X[folds=="validation"],state)
        score=mae(y[folds=="validation"],ridge(xt,yt[folds=="train"],xv,a))
        if best is None or score<best[0]: best=(score,a)
    fit=folds!="test"; xt,state=transform_fit(X[fit]); xe=transform(X[folds=="test"],state); pred=ridge(xt,yt[fit],xe,best[1]); truth=y[folds=="test"]
    raw=[(r["session_id"],r["subject_id"],float(t),float(p)) for r,t,p in zip([r for r in rows if r["fold"]=="test"],truth,pred)]
    return {"mae":mae(truth,pred),"rmse":rmse(truth,pred),"r2":r2(truth,pred),"alpha":best[1],"n":len(truth)},raw,fkeys

def fit_binary(rows):
    fkeys=keys(rows); X=matrix(rows,fkeys); y=np.asarray([r["targets"]["completed"] for r in rows],float); folds=np.asarray([r["fold"] for r in rows]); best=None
    for a in (.1,1.,10.):
        xt,state=transform_fit(X[folds=="train"]); xv=transform(X[folds=="validation"],state); p=logistic(xt,y[folds=="train"],xv,a); score=float(np.mean((p-y[folds=="validation"])**2))
        if best is None or score<best[0]: best=(score,a)
    fit=folds!="test"; xt,state=transform_fit(X[fit]); xe=transform(X[folds=="test"],state); p=logistic(xt,y[fit],xe,best[1]); truth=y[folds=="test"]; pred=p>=.5
    tp=np.sum((truth==1)&pred); tn=np.sum((truth==0)&~pred); fp=np.sum((truth==0)&pred); fn=np.sum((truth==1)&~pred)
    return {"brier":float(np.mean((p-truth)**2)),"accuracy":float(np.mean(pred==truth)),"sensitivity":float(tp/max(tp+fn,1)),"specificity":float(tn/max(tn+fp,1)),"auroc":auc(truth,p),"alpha":best[1],"n":len(truth),"positive_rate":float(truth.mean())}

def validations(data, mode_rows):
    checks={}
    splits={f:{x["subject_id"] for x in data["observed"] if x["fold"]==f} for f in ("train","validation","test")}
    checks["subject_disjoint"]=not((splits["train"]&splits["validation"])|(splits["train"]&splits["test"])|(splits["validation"]&splits["test"]))
    ids=[{r["session_id"] for r in rows} for rows in mode_rows.values()]; checks["same_evaluation_sessions"]=all(x==ids[0] for x in ids[1:])
    bad_tokens=("latent","capacity","tolerance","debt","relative","depletion")
    checks["no_latent_feature"]=all(not any(t in k for t in bad_tokens) for rows in mode_rows.values() for k in keys(rows))
    checks["past_only_history"]=all(r["session_index"]>=100 for rows in mode_rows.values() for r in rows)
    audit={x["session_id"]:x for x in data["audit"]}
    checks["missing_artifact_support"]=sum(x["missing_count"] for x in audit.values())>0 and sum(x["artifact_count"] for x in audit.values())>0
    checks["completion_class_support"]=all(len({r["targets"]["completed"] for r in rows if r["fold"]==f})==2 for f in ("train","validation","test") for rows in [mode_rows["current"]])
    return checks

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    seed_results={}; predictions=[]; split_manifest={}; validation={}
    for seed in SEEDS:
        data=sim.generate(seed); repeat=sim.generate(seed)
        reproducible=hashlib.sha256(json.dumps(data["observed"],sort_keys=True).encode()).hexdigest()==hashlib.sha256(json.dumps(repeat["observed"],sort_keys=True).encode()).hexdigest()
        mode_rows={m:sim.history_rows(data,m,20) for m in MODES}; checks=validations(data,mode_rows); checks["exact_reproducibility"]=reproducible
        validation[str(seed)]=checks
        split_manifest[str(seed)]={f:sorted({r["subject_id"] for r in data["observed"] if r["fold"]==f}) for f in ("train","validation","test")}
        seed_results[str(seed)]={}
        for mode,rows in mode_rows.items():
            entry={"continuous":{},"completion":fit_binary(rows)}
            for target in TARGETS:
                met,raw,fkeys=fit_cont(rows,target); entry["continuous"][target]=met
                for sid,sub,t,p in raw: predictions.append({"seed":seed,"mode":mode,"target":target,"session_id":sid,"subject_id":sub,"truth":t,"prediction":p})
            stop_rows=[r for r in rows if r["targets"]["stop_time"] is not None]
            entry["continuous"]["stop_time"],raw,_=fit_cont(stop_rows,"stop_time")
            seed_results[str(seed)][mode]=entry
        # Falsification tests are audit-only and use seed-specific full rows.
        normal,_,_=fit_cont(mode_rows["full"],"pre_fatigue")
        tshuf,_,_=fit_cont(mode_rows["full"],"pre_fatigue",shuffle=True)
        fshuf,_,_=fit_cont(mode_rows["full"],"pre_fatigue",feature_shuffle=True)
        validation[str(seed)]["shuffle"]={"normal_mae":normal["mae"],"target_shuffle_mae":tshuf["mae"],"feature_shuffle_mae":fshuf["mae"],"pass":tshuf["mae"]>normal["mae"] and fshuf["mae"]>normal["mae"]}

    summary={}
    for target in (*TARGETS,"stop_time","completed"):
        summary[target]={}
        base=[]
        for s in SEEDS:
            x=seed_results[str(s)]["current"]
            base.append(x["completion"]["brier"] if target=="completed" else x["continuous"][target]["mae"])
        for mode in MODES:
            vals=[]
            for s in SEEDS:
                x=seed_results[str(s)][mode]; vals.append(x["completion"]["brier"] if target=="completed" else x["continuous"][target]["mae"])
            diff=[b-v for b,v in zip(base,vals)]
            summary[target][mode]={"primary":ci(vals),"current_minus_mode":ci(diff),"improved_seeds":sum(d>0 for d in diff)}
    result={"version":"pretask-model-phase1-01","seeds":list(SEEDS),"modes":list(MODES),"targets":list(TARGETS)+["stop_time","completed"],"seed_results":seed_results,"summary":summary,"validation":validation,"parameter_sha256":sim.sha(sim.PARAM),"lock_sha256":sim.sha(sim.LOCK),"generator_sha256":sim.sha(ROOT/"simulator_pretask_model.py")}
    (OUT/"results.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"split_manifest.json").write_text(json.dumps(split_manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    with gzip.open(OUT/"raw_predictions.jsonl.gz","wt",encoding="utf-8") as f:
        for row in predictions:f.write(json.dumps(row,ensure_ascii=False)+"\n")
    with (OUT/"summary.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.writer(f); w.writerow(["target","mode","primary_mean","primary_sd","ci_low","ci_high","current_minus_mode","diff_ci_low","diff_ci_high","improved_seeds"])
        for target,by_mode in summary.items():
            for mode,x in by_mode.items(): w.writerow([target,mode,x["primary"]["mean"],x["primary"]["sd"],*x["primary"]["ci95"],x["current_minus_mode"]["mean"],*x["current_minus_mode"]["ci95"],x["improved_seeds"]])
    print(json.dumps({"summary":summary,"validation":validation},ensure_ascii=False,indent=2))

if __name__=="__main__": main()
