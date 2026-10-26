"""Post-review HR versus HR/temperature/SpO2 comparison; frozen generators."""
from pathlib import Path
import os
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'): os.environ[key]='1'
import concurrent.futures as cf, csv, gzip, hashlib, json, math, sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'vendor'))
import numpy as np
from scipy.stats import t
import simulator_pretask_model as sim
import run_pretask_model as fit
import simulator_e4_daily_state_20261026 as day
import run_e4_daily_state_20261026 as dayfit
from run_review_simple_baselines_20261026 import metric

OUT=ROOT/'artifacts/review_sensor_ablation_20261026'
PROTOCOL=ROOT/'REVIEW_SENSOR_ABLATION_PROTOCOL_20261026.json'
SCALE=ROOT/'artifacts/scale_stability_20261006'
DAILY=ROOT/'artifacts/e4_daily_state_20261026'

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x): p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def digest(x): return hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest()
def removed(name): return 'temperature' in name or 'spo2' in name

def subset(rows,arm,variant):
    if arm=='PRETASK':
        return [{k:v for k,v in r.items() if variant=='THREE' or not removed(k)} for r in rows]
    return [dict(r,features={k:v for k,v in r['features'].items() if variant=='THREE' or not removed(k)}) for r in rows]

def fit_pre(rows,target):
    names=fit.keys(rows);X=fit.matrix(rows,names)
    y=np.asarray([r['targets'][target] for r in rows],float)
    folds=np.asarray([r['fold'] for r in rows]);tr=folds=='train';va=folds=='validation';te=folds=='test';final=tr|va
    xt,state=fit.transform_fit(X[tr]);xv=fit.transform(X[va],state)
    grid=(.1,1.,10.) if target=='completed' else fit.ALPHAS
    predictor=fit.logistic if target=='completed' else fit.ridge
    def loss(y,p): return float(np.mean((p-y)**2)) if target=='completed' else fit.mae(y,p)
    trials=[(loss(y[va],predictor(xt,y[tr],xv,a)),a) for a in grid]
    # Preserve the original first-in-grid tie handling.
    alpha=min(trials,key=lambda v:v[0])[1]
    xf,state=fit.transform_fit(X[final]);xe=fit.transform(X[te],state)
    prediction=predictor(xf,y[final],xe,alpha)
    held=[r for r in rows if r['fold']=='test']
    model=dict(names=names,alpha=alpha,validation_scores=trials,
               preprocessing=dict(median=state[0].tolist(),mean=state[1].tolist(),sd=state[2].tolist()),
               selection_preprocessing='train only',final_preprocessing='train+validation',
               train_n=int(tr.sum()),validation_n=int(va.sum()),test_n=int(te.sum()))
    return [(r['subject_id'],r['session_id'],float(v),float(p)) for r,v,p in zip(held,y[te],prediction)],model

def split_check(rows,arm):
    sk,ik=('subject_id','session_id') if arm=='PRETASK' else ('subject','session')
    groups={f:sorted({r[sk] for r in rows if r['fold']==f}) for f in ('train','validation','test')}
    assert [len(groups[f]) for f in groups]==[288,96,96]
    sets=list(map(set,groups.values()))
    assert all(not(a&b) for i,a in enumerate(sets) for b in sets[i+1:])
    assert len({r[ik] for r in rows})==len(rows)
    return groups

def worker(seed):
    dest=OUT/f'seed_{seed}';dest.mkdir(exist_ok=False)
    sim.verify_lock();day.verify()
    pre={0:[],20:[]};generation=[];history=[]
    expected=json.loads((SCALE/f'seed_{seed}/generation_hashes.json').read_text())
    for b in range(4):
        data=sim.generate(seed+1000003*b)
        assert digest(data['observed'])==expected[b]['pretask_observed']
        generation.append(dict(block=b,pretask_observed=digest(data['observed'])))
        grouped={}
        for r in data['observed']:grouped.setdefault(r['subject_id'],[]).append(r)
        for sid,seq in grouped.items():
            seq.sort(key=lambda r:r['session_index'])
            for i,r in enumerate(seq):
                if r['phase']!='evaluation':continue
                past=seq[i-20:i];assert len(past)==20
                assert all(x['subject_id']==sid and x['session_index']<r['session_index'] for x in past)
                history.append(dict(subject=f'B{b}:'+sid,session=f'B{b}:'+r['session_id'],sources=[f'B{b}:'+x['session_id'] for x in past]))
        for k in pre:
            rows=sim.history_rows(data,'current' if k==0 else 'full',k)
            for r in rows:r['subject_id']=f'B{b}:'+r['subject_id'];r['session_id']=f'B{b}:'+r['session_id']
            pre[k].extend(rows)
    assert [(r['session_id'],r['targets']) for r in pre[0]]==[(r['session_id'],r['targets']) for r in pre[20]]
    splits={'PRETASK':split_check(pre[0],'PRETASK')}
    old=[r for r in json.loads((SCALE/f'seed_{seed}/metrics.json').read_text()) if r['arm']=='PRETASK' and r['population']==480]
    records=[];models={};references={};feature_checks=[]
    with gzip.open(dest/'predictions.csv.gz','wt',encoding='utf-8',newline='') as stream:
        w=csv.writer(stream);w.writerow(['arm','seed','k','variant','target','subject','session','truth','prediction'])
        for k,rows in pre.items():
            for variant in ('HR','THREE'):
                use=subset(rows,'PRETASK',variant);names=fit.keys(use)
                assert not any(n.startswith(('latent','true_','audit_')) for n in names)
                assert variant=='THREE' or not any(removed(n) for n in names)
                feature_checks.append(dict(arm='PRETASK',k=k,variant=variant,names=names))
                for target in (*fit.TARGETS,'completed'):
                    raw,model=fit_pre(use,target)
                    ids=[(s,i,y) for s,i,y,p in raw]
                    key=('PRETASK',k,target)
                    if key in references:assert references[key]==ids
                    else:references[key]=ids
                    values=metric([r[2] for r in raw],[r[3] for r in raw],target)
                    records.append(dict(arm='PRETASK',seed=seed,k=k,variant=variant,target=target,**values))
                    if variant=='THREE':
                        baseline=next(r for r in old if r['k']==k and r['target']==target)
                        assert abs(values['primary']-baseline['primary'])<1e-9,(seed,k,target,'old reproduction')
                    models[f'PRETASK|{k}|{variant}|{target}']=model
                    for sub,sid,y,p in raw:w.writerow(['PRETASK',seed,k,variant,target,sub,sid,y,p])
        # Reuse saved BASE observations; never regenerate or alter the daily-state data.
        source=DAILY/f'seed_{seed}/BASE/observed.jsonl.gz'
        with gzip.open(source,'rt',encoding='utf-8') as f:obs=[json.loads(line) for line in f]
        dayrows=[];dayhistory=[]
        for b in range(4):
            rs,ms=day.features(dict(observed_events=[r for r in obs if r['block']==b],
                                  audit_only=[dict(session=r['session'],state=0) for r in obs if r['block']==b]),f'B{b}:')
            # Dummy audit state is never used: oracle rows are excluded immediately.
            dayrows.extend(r for r in rs if r['variant']!='oracle');dayhistory.extend(ms)
        splits['E4_DAILY_BASE']=split_check([r for r in dayrows if r['variant']=='full'],'E4')
        daily_old=json.loads((DAILY/f'seed_{seed}/metrics.json').read_text())
        for k,name in ((0,'current'),(20,'full')):
            base=[r for r in dayrows if r['variant']==name]
            for variant in ('HR','THREE'):
                use=subset(base,'E4',variant);names=list(use[0]['features'])
                assert not any(n.startswith(('true_','audit_','latent_')) for n in names)
                assert variant=='THREE' or not any(removed(n) for n in names)
                feature_checks.append(dict(arm='E4_DAILY_BASE',k=k,variant=variant,names=names))
                pred,model=dayfit.fit_variant(use)
                held=[r for r in use if r['fold']=='test' and r['target'] is not None]
                raw=[(r['subject'],r['session'],r['target'],pred[r['session']]) for r in held]
                key=('E4',k,'E4_stop_minutes');ids=[(s,i,y) for s,i,y,p in raw]
                if key in references:assert references[key]==ids
                else:references[key]=ids
                values=metric([r[2] for r in raw],[r[3] for r in raw],'E4_stop_minutes')
                records.append(dict(arm='E4_DAILY_BASE',seed=seed,k=k,variant=variant,target='E4_stop_minutes',**values))
                if variant=='THREE':
                    baseline=next(r for r in daily_old if r['scenario']=='BASE' and r['method']==name)
                    assert abs(values['mae']-baseline['mae'])<1e-9
                models[f'E4|{k}|{variant}']=model
                for sub,sid,y,p in raw:w.writerow(['E4_DAILY_BASE',seed,k,variant,'E4_stop_minutes',sub,sid,y,p])
    save(dest/'metrics.json',records);save(dest/'selected_models.json',models)
    save(dest/'split_manifest.json',splits);save(dest/'feature_manifest.json',feature_checks)
    save(dest/'generation_hashes.json',generation)
    with gzip.open(dest/'history_manifest.json.gz','wt',encoding='utf-8') as f:json.dump(dict(PRETASK=history,E4=dayhistory),f)
    save(dest/'validation.json',dict(subject_session_split='PASS',history_past_only='PASS',same_targets_sessions='PASS',
                                    full_sensor_old_results_reproduced='PASS',excluded_channels_and_quality_removed='PASS',
                                    observed_only='PASS',test_not_selected_on='PASS',daily_input_sha256=sha(source)))
    print(f'seed {seed} complete',flush=True)
    return records

def interval(v,alpha=.05):
    x=np.asarray(v,float);m=float(x.mean());sd=float(x.std(ddof=1));h=float(t.ppf(1-alpha/2,len(x)-1)*sd/math.sqrt(len(x)))
    return dict(mean=m,sd=sd,ci95=[m-h,m+h],n=len(x))

def main():
    p=json.loads(PROTOCOL.read_text(encoding='utf-8'))
    assert sha(PROTOCOL)==PROTOCOL.with_suffix('.sha256').read_text().split()[0]
    for name,value in p['protected_files'].items():assert sha(ROOT/name)==value,name
    OUT.mkdir(exist_ok=False)
    save(OUT/'protocol_snapshot.json',p)
    records=[]
    with cf.ProcessPoolExecutor(max_workers=2) as pool:
        for rows in pool.map(worker,p['seeds']):records.extend(rows)
    save(OUT/'all_metrics.json',records)
    summary=[];paired=[]
    for arm,k,target in sorted({(r['arm'],r['k'],r['target']) for r in records}):
        groups={v:sorted([r for r in records if (r['arm'],r['k'],r['target'],r['variant'])==(arm,k,target,v)],key=lambda r:r['seed']) for v in ('HR','THREE')}
        for variant,rs in groups.items():
            assert len(rs)==30
            fields=('primary','brier','auroc') if target=='completed' else ('primary','mae','rmse','r2')
            summary.append(dict(arm=arm,k=k,target=target,variant=variant,**{f:interval([r[f] for r in rs]) for f in fields}))
        hr,three=groups['HR'],groups['THREE'];assert [r['seed'] for r in hr]==[r['seed'] for r in three]
        d=[a['primary']-b['primary'] for a,b in zip(hr,three)]
        # One simultaneous family: 5 targets x 2 histories, plus 2 daily-state contrasts.
        ci=interval(d,.05/12)['ci95']
        paired.append(dict(arm=arm,k=k,target=target,difference_HR_minus_THREE=interval(d),
                           relative_reduction=interval([x/a['primary'] for x,a in zip(d,hr)]),
                           simultaneous_ci=ci,three_better_seeds=sum(v>0 for v in d),seed_differences=d,
                           decision='THREE_BETTER' if ci[0]>0 else 'HR_BETTER' if ci[1]<0 else 'INCONCLUSIVE'))
    save(OUT/'summary.json',summary);save(OUT/'paired_comparisons.json',paired)
    for name,value in p['protected_files'].items():assert sha(ROOT/name)==value,name
    save(OUT/'validation.json',dict(status='PASS',protected_files_unchanged=True,seeds=len(p['seeds']),
                                   old_results_reproduced=True,paired_contrasts=12,scope='Synthetic information ablation, not device accuracy validation'))
    save(OUT/'MANIFEST.json',{str(q.relative_to(OUT)):sha(q) for q in OUT.rglob('*') if q.is_file() and q.name!='MANIFEST.json'})
    print('COMPLETE',len(records),flush=True)

if __name__=='__main__':main()
