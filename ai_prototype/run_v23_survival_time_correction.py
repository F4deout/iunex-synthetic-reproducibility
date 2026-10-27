"""Separate post-hoc time-at-risk correction; no frozen files are edited."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
import run_v23_phase1_methodfix as old

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'artifacts/v23_survival_time_correction_20260929'
PLAN = ROOT/'SIMULATOR_V23_SURVIVAL_TIME_AMENDMENT_20260929.md'
STEPS = (1., 2.5, 5., 10.)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def save(name, obj):
    (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

def grid(step):
    return np.arange(step,90.+1e-8,step)

def time_features(ends):
    return np.column_stack((ends/90.,np.log1p(ends)/np.log(91.)))

def expand(x,t,event,step):
    t=np.asarray(t,float); event=np.asarray(event,bool)
    assert np.all((t>0)&(t<=90))
    ends=grid(step)
    exposure=np.clip(t[:,None]-(ends-step),0,step)
    i,j=np.where(exposure>0)
    design=np.column_stack((np.ones(len(i)),x[i],time_features(ends[j])))
    d=event[i] & (j==np.searchsorted(ends,t[i],side='left'))
    assert np.allclose(np.bincount(i,weights=exposure[i,j],minlength=len(t)),t)
    assert np.array_equal(np.bincount(i,weights=d,minlength=len(t)),event.astype(int))
    return design,exposure[i,j],d.astype(float)

def objective(b,X,exposure,d,penalty):
    eta=X@b
    with np.errstate(over='ignore'):
        return float(np.sum(exposure*np.exp(eta)-d*eta)+.5*np.sum(penalty*b*b))

def fit(X,exposure,d,c):
    b=np.zeros(X.shape[1]); b[0]=np.log(d.sum()/exposure.sum())
    penalty=np.r_[0.,np.full(len(b)-1,1/c)]
    for iteration in range(100):
        mu=exposure*np.exp(X@b)
        g=X.T@(mu-d)+penalty*b
        H=X.T@(X*mu[:,None])+np.diag(penalty)
        delta=np.linalg.solve(H,g)
        decrement=float(g@delta)
        if decrement<1e-9:
            return b,{'iterations':iteration+1,'decrement':decrement,'scaled_gradient':float(np.max(np.abs(g))/(1+d.sum()))}
        loss=objective(b,X,exposure,d,penalty)
        scale=1.
        while scale>2**-30:
            trial=b-scale*delta
            if objective(trial,X,exposure,d,penalty)<=loss-1e-4*scale*decrement:
                b=trial
                break
            scale*=.5
        else:
            raise RuntimeError('Newton line search failed')
    raise RuntimeError('Newton convergence failed')

def predict(b,x,planned,step):
    ends=grid(step)
    base=b[0]+x@b[1:-2]
    rates=np.exp(base[:,None]+(time_features(ends)@b[-2:])[None,:])
    exposure=np.clip(np.asarray(planned)[:,None]-(ends-step),0,step)
    probability=-np.expm1(-np.sum(rates*exposure,axis=1))
    cum=np.cumsum(rates*step,axis=1)
    start=np.exp(-np.column_stack((np.zeros(len(x)),cum[:,:-1])))
    integral=np.divide(-np.expm1(-rates*step),rates,out=np.full_like(rates,step),where=rates>0)
    rmst=np.sum(start*integral,axis=1)
    assert np.all(np.isfinite(rmst)) and np.all((rmst>=0)&(rmst<=90+1e-8))
    return probability,rmst

def checks():
    for step in STEPS:
        t=np.array([.01,step,step+.01,90.])
        X,e,d=expand(np.empty((4,0)),t,[True,True,False,False],step)
        assert d.sum()==2 and abs(e.sum()-t.sum())<1e-9
        b=np.array([np.log(.1),0.,0.])
        p,r=predict(b,np.empty((3,0)),[1.,5.01,90.],step)
        assert np.allclose(p,1-np.exp(-.1*np.array([1.,5.01,90.])))
        assert np.allclose(r,(1-np.exp(-9))/.1)
    X=np.ones((4,1));e=np.array([1.,2.,3.,4.]);d=np.array([1.,0.,1.,0.])
    b,info=fit(X,e,d,1.)
    assert np.allclose(np.exp(b[0]),d.sum()/e.sum())
    a=expand(np.zeros((1,1)),[5.01],[True],5.)[0]
    b=expand(np.zeros((1,1)),[9.99],[True],5.)[0]
    assert np.array_equal(a,b)
    return {'exposure_conservation':'PASS','event_conservation':'PASS','boundary_and_partial_censoring':'PASS','constant_rate_analytic_probability_rmst':'PASS','intercept_only_mle':'PASS','event_time_not_used_as_time_feature':'PASS'}

def run(rows,step):
    folds=np.array([r['fold'] for r in rows]); x=np.array([r['x'] for r in rows])
    t=np.array([r['time'] for r in rows]);event=np.array([r['event'] for r in rows]);planned=np.array([r['planned'] for r in rows])
    tr,va,te=folds=='train',folds=='validation',folds=='test'
    prep=old.Prep().fit(x[tr]);zt,zv,ze=map(prep.transform,(x[tr],x[va],x[te]))
    Xt,et,dt=expand(zt,t[tr],event[tr],step)
    Xv,ev,dv=expand(zv,t[va],event[va],step)
    trials=[]
    for c in old.GRID:
        b,info=fit(Xt,et,dt,c)
        loss=objective(b,Xv,ev,dv,np.zeros(len(b)))/va.sum()
        trials.append({'c':c,'validation_session_nll':loss,**info})
    c=min(trials,key=lambda v:(v['validation_session_nll'],v['c']))['c']
    Xa,ea,da=expand(np.vstack((zt,zv)),np.r_[t[tr],t[va]],np.r_[event[tr],event[va]],step)
    b,info=fit(Xa,ea,da,c)
    p,r=predict(b,ze,planned[te],step)
    metrics=old.metrics(event[te],p,.5)
    metrics.update({'cindex':old.cindex(t[te],event[te],r),'stopped_rmst_mae':float(np.abs(t[te][event[te]]-r[event[te]]).mean()),'rmst_min':float(r.min()),'rmst_max':float(r.max())})
    predictions=[{'subject':row['subject_id'],'session':row['session_id'],'event':bool(ee),'observed_minutes':float(tt),'planned_minutes':float(pp),'stop_probability':float(pr),'rmst_minutes':float(rr)} for row,ee,tt,pp,pr,rr in zip([v for v in rows if v['fold']=='test'],event[te],t[te],planned[te],p,r)]
    return {'metrics':metrics,'selected_c':c,'trials':trials,'optimizer':info,'preprocessing':{k:np.asarray(v).tolist() for k,v in vars(prep).items()},'coefficients':b.tolist()},predictions

def main():
    OUT.mkdir(parents=True,exist_ok=False)
    protected=list(ROOT.glob('*.py'))+list(ROOT.glob('SIMULATOR*.md'))+list(ROOT.glob('SIMULATOR*.json'))
    protected += list((ROOT/'artifacts/v23_phase1').glob('*'))+list((ROOT/'artifacts/v23_phase1_methodfix').glob('*'))
    protected += list(ROOT.parent.glob('*.hwpx'))
    before={str(p.relative_to(ROOT.parent)):sha(p) for p in protected if p.is_file()}
    save('freeze_before.json',{'plan_sha256':sha(PLAN),'code_sha256':sha(Path(__file__)),'protected':before})
    validation=checks(); save('unit_validation.json',validation)
    previous=json.loads((ROOT/'artifacts/v23_phase1_methodfix/results.json').read_text(encoding='utf-8'))
    runs=[];raw=[];hashes={};split=[]
    for seed in old.SEEDS:
        data=old.build(seed)
        h=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        assert h==previous['data_hashes'][str(seed)]
        hashes[str(seed)]=h
        for scope in old.SCOPES:
            keys=None
            for k in old.KS:
                rows=old.make_rows(data,k,scope,'performance')
                ids={f:{r['subject_id'] for r in rows if r['fold']==f} for f in ('train','validation','test')}
                assert not(ids['train']&ids['validation'] or ids['train']&ids['test'] or ids['validation']&ids['test'])
                current=[r['session_id'] for r in rows if r['fold']=='test']
                if keys is None:
                    keys=current
                    split.extend({'seed':seed,'scope':scope,'subject':r['subject_id'],'session':r['session_id'],'fold':r['fold']} for r in rows)
                assert keys==current
                for step in STEPS:
                    result,pred=run(rows,step)
                    tag={'seed':seed,'scope':scope,'k':k,'step_minutes':step}
                    runs.append({**tag,**result});raw.extend({**tag,**p} for p in pred)
            save('runs.json',runs)
            print(seed,scope,'complete',len(runs),flush=True)
    summary=[]
    for scope in old.SCOPES:
        for step in STEPS:
            for k in old.KS:
                items=[r for r in runs if r['scope']==scope and r['step_minutes']==step and r['k']==k]
                base=[r for r in runs if r['scope']==scope and r['step_minutes']==step and r['k']==0]
                for metric in ('brier','logloss','auc','cindex','stopped_rmst_mae'):
                    values=[r['metrics'][metric] for r in items]
                    effect=[(r['metrics'][metric]-b['metrics'][metric])*(1 if metric in ('auc','cindex') else -1) for r,b in zip(items,base)]
                    summary.append({'scope':scope,'step_minutes':step,'k':k,'metric':metric,'value':old.ci(values),'paired_improvement':old.ci(effect),'positive_seeds':sum(v>0 for v in effect),'seed_effects':effect})
    save('summary.json',summary);save('split_manifest.json',split);save('data_hashes.json',hashes)
    with (OUT/'predictions.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=raw[0]);w.writeheader();w.writerows(raw)
    # Deterministic repeat of the first fitted condition, without model selection on test.
    repeat,_=run(old.make_rows(old.build(old.SEEDS[0]),0,'pooled','performance'),1.)
    assert repeat=={key:runs[0][key] for key in repeat}
    after={p:sha(ROOT.parent/p) for p in before}; assert before==after
    save('validation.json',{**validation,'same_frozen_data':'PASS','subject_disjoint':'PASS','same_test_all_k_steps':'PASS','deterministic_repeat':'PASS','train_only_preprocessing':'PASS','validation_only_selection':'PASS','all_optimizer_converged':'PASS','protected_files_unchanged':'PASS','runs':len(runs),'predictions':len(raw),'max_scaled_gradient':max(r['optimizer']['scaled_gradient'] for r in runs)})
    save('manifest.json',{p.name:sha(p) for p in OUT.iterdir() if p.is_file()})

if __name__=='__main__':
    main()
