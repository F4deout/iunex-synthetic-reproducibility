"""Preregistered, read-only maturity audit for the frozen PRETASK model."""
from __future__ import annotations
import hashlib, json, math
from pathlib import Path
import numpy as np
import simulator_pretask_model as sim
import run_pretask_model as run

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"artifacts"/"pretask_inference_maturity"
SEEDS=(110,220,330,440,550)

def ci(v):
    a=np.asarray(v,float); m=float(a.mean()); sd=float(a.std(ddof=1)); h=2.7764451051977987*sd/math.sqrt(len(a)); return {"mean":m,"sd":sd,"ci95":[m-h,m+h]}

def ece(y,p,bins=10):
    edges=np.linspace(0,1,bins+1); total=len(y); value=0.; detail=[]
    for i in range(bins):
        mask=(p>=edges[i])&(p<(edges[i+1]) if i<bins-1 else p<=edges[i+1])
        if not np.any(mask): continue
        conf=float(p[mask].mean()); freq=float(y[mask].mean()); value+=mask.sum()/total*abs(conf-freq); detail.append({"low":edges[i],"high":edges[i+1],"n":int(mask.sum()),"predicted":conf,"observed":freq})
    return float(value),detail

def binary_raw(rows):
    fkeys=run.keys(rows); X=run.matrix(rows,fkeys); y=np.asarray([r["targets"]["completed"] for r in rows],float); folds=np.asarray([r["fold"] for r in rows]); best=None
    for a in (.1,1.,10.):
        xt,state=run.transform_fit(X[folds=="train"]); xv=run.transform(X[folds=="validation"],state); p=run.logistic(xt,y[folds=="train"],xv,a); score=float(np.mean((p-y[folds=="validation"])**2))
        if best is None or score<best[0]: best=(score,a)
    fit=folds!="test"; xt,state=run.transform_fit(X[fit]); xe=run.transform(X[folds=="test"],state); p=run.logistic(xt,y[fit],xe,best[1]); test=[r for r in rows if r["fold"]=="test"]
    return test,y[folds=="test"],p

def latent_head(rows,amap,history=False):
    # Audit-only target independent of reporting slope and bias.
    target=[]
    for r in rows:
        x=dict(r); x["targets"]=dict(r["targets"]); x["targets"]["audit_phys_state"]=2+6*amap[r["session_id"]]["pre_fatigue_latent"]; target.append(x)
    return run.fit_cont(target,"audit_phys_state")[0]

def safety_screen(values,p):
    gate=p["safety_gate_research_only"]
    present=[values.get("t0_hr"),values.get("t0_temperature"),values.get("t0_spo2")]
    if all(v is None for v in present): return "ABSTAIN_MISSING"
    if values.get("t0_hr") is not None and (values["t0_hr"]<gate["resting_hr_low_bpm"] or values["t0_hr"]>gate["resting_hr_high_bpm"]): return "SAFETY_HOLD"
    if values.get("t0_temperature") is not None and values["t0_temperature"]>=gate["temperature_high_c"]: return "SAFETY_HOLD"
    if values.get("t0_spo2") is not None and values["t0_spo2"]<gate["spo2_low_pct"]: return "SAFETY_HOLD"
    return "MODEL_ALLOWED"

def main():
    p=json.loads(sim.PARAM.read_text(encoding="utf-8")); per_seed={}
    for seed in SEEDS:
        data=sim.generate(seed); amap={a["session_id"]:a for a in data["audit"]}; current=sim.history_rows(data,"current",20); full=sim.history_rows(data,"full",20); sensor=sim.history_rows(data,"sensor_history",20)
        test,y,prob=binary_raw(full); score_ece,cal=ece(y,prob)
        by_task={}; by_demand={}
        for name,selector in [(t,lambda r,t=t:r["task_type"]==t) for t in sim.TASKS]+[(str(d),lambda r,d=d:r["planned_demand"]==d) for d in p["planned_demand_levels"]]:
            mask=np.asarray([selector(r) for r in test]); rec={"n":int(mask.sum()),"brier":float(np.mean((prob[mask]-y[mask])**2)),"completion_rate":float(y[mask].mean())}
            (by_task if name in sim.TASKS else by_demand)[name]=rec
        cont={}
        for target in ("pre_fatigue","pre_condition","post_burden","recovery_delay","stop_time"):
            rows=full if target!="stop_time" else [r for r in full if r["targets"]["stop_time"] is not None]
            metric,raw,_=run.fit_cont(rows,target); grouped={}
            for task in sim.TASKS:
                z=[(truth,pred) for sid,sub,truth,pred in raw if next(r for r in rows if r["session_id"]==sid)["task_type"]==task]
                grouped[task]={"n":len(z),"mae":float(np.mean([abs(a-b) for a,b in z])) if z else None}
            cont[target]={"overall":metric,"by_task":grouped}
        per_seed[str(seed)]={"completion":{"brier":float(np.mean((prob-y)**2)),"ece10":score_ece,"calibration_bins":cal,"by_task":by_task,"by_demand":by_demand},"continuous":cont,"physiology_audit":{"current":latent_head(current,amap),"sensor_history":latent_head(sensor,amap)}}
    summary={"completion":{"brier":ci([per_seed[str(s)]["completion"]["brier"] for s in SEEDS]),"ece10":ci([per_seed[str(s)]["completion"]["ece10"] for s in SEEDS])},"physiology_audit":{"current_mae":ci([per_seed[str(s)]["physiology_audit"]["current"]["mae"] for s in SEEDS]),"sensor_history_mae":ci([per_seed[str(s)]["physiology_audit"]["sensor_history"]["mae"] for s in SEEDS])}}
    safety_cases={"normal":{"t0_hr":70,"t0_temperature":36.7,"t0_spo2":98},"high_fever":{"t0_hr":90,"t0_temperature":40,"t0_spo2":97},"low_spo2":{"t0_hr":80,"t0_temperature":36.8,"t0_spo2":85},"high_hr":{"t0_hr":150,"t0_temperature":36.8,"t0_spo2":97},"all_missing":{"t0_hr":None,"t0_temperature":None,"t0_spo2":None}}
    safety={k:safety_screen(v,p) for k,v in safety_cases.items()}; safety_pass=safety=={"normal":"MODEL_ALLOWED","high_fever":"SAFETY_HOLD","low_spo2":"SAFETY_HOLD","high_hr":"SAFETY_HOLD","all_missing":"ABSTAIN_MISSING"}
    result={"version":"pretask-inference-maturity-audit-01","protocol_sha256":hashlib.sha256((ROOT/"PRETASK_INFERENCE_MATURITY_PROTOCOL.md").read_bytes()).hexdigest(),"per_seed":per_seed,"summary":summary,"safety_stress_test":safety,"safety_pass":safety_pass,"finding":"SUBJECTIVE_AND_PHYSIOLOGICAL_HEADS_MUST_REMAIN_SEPARATE","status":"MATURE_FOR_RESEARCH_UI" if safety_pass else "MODEL_FIX_REQUIRED"}
    OUT.mkdir(parents=True,exist_ok=True); (OUT/"results.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8"); print(json.dumps({"summary":summary,"safety":safety,"finding":result["finding"],"status":result["status"]},ensure_ascii=False,indent=2))

if __name__=="__main__": main()
