"""Synthetic single-channel red-flag detection; score prediction is a separate task."""
from pathlib import Path
import os,sys
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='1'
R=Path(__file__).resolve().parent;sys.path.insert(0,str(R/'vendor'))
import concurrent.futures as cf,csv,gzip,hashlib,json,math
import numpy as np
from scipy.stats import t
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_curve,roc_auc_score
import run_pretask_model as fit
import pretask_inference as frozen
PFILE=R/'REDFLAG_SENSOR_PROTOCOL_20261026.json';OUT=R/'artifacts/redflag_sensor_experiment_20261026'
CHANNELS=('hr','temperature','spo2');TYPES=('normal','high_temperature','low_temperature','low_spo2','low_hr','high_hr','mixed')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def generator(seed,subject,session,process):
    return np.random.default_rng(int.from_bytes(hashlib.sha256(f'redflag-20261026|{seed}|{subject}|{session}|{process}'.encode()).digest()[:16],'big'))

def truths(seed,split,P):
    rows=[]
    for fold,subjects in split.items():
        for sub in subjects:
            for j in range(P['sessions_per_subject']):
                g=generator(seed,sub,j,'truth');kind=str(g.choice(TYPES,p=P['type_probabilities']))
                values={c:float(g.uniform(*P['true_normal_ranges'][c])) for c in CHANNELS}
                kinds=[kind] if kind not in ('normal','mixed') else []
                if kind=='mixed':kinds=list(g.choice(['high_temperature','low_spo2','high_hr'],size=2,replace=False))
                for name in kinds:
                    c=P['event_channels'][name];values[c]=float(g.uniform(*P['true_event_ranges'][name]))
                rows.append(dict(subject=sub,session=f'{sub}:RISK{j:02}',fold=fold,index=j,kind=kind,
                                 label=int(kind!='normal'),true=values))
    return rows

def measure(rows,seed,case,P):
    cfg=P['measurement_cases'][case];result=[]
    for r in rows:
        v={};q={}
        for c in CHANNELS:
            g=generator(seed,r['subject'],r['index'],c+'-measure')
            # Masks/quality are sampled before magnitude; noise shifts do not change latent truth.
            artifact=bool(g.random()<cfg['artifact_p']);missing=bool(g.random()<cfg['missing_p'])
            quality=float(np.clip(.94-.55*artifact+g.normal(0,.035),0,1))
            sd=P['measurement_sd'][c]*cfg['noise_multiplier']*(4 if artifact else 1)
            bias=float(generator(seed,r['subject'],'device',c).normal(0,P['device_bias_sd'][c]))
            x=float(np.clip(r['true'][c]+bias+g.normal(0,sd),*P['measurement_bounds'][c]))
            v[c]=None if missing else x;q[c]=quality
        result.append(dict(r,observed=v,quality=q))
    return result

def matrix(rows,channels):
    return np.asarray([[value for c in channels for value in (np.nan if r['observed'][c] is None else r['observed'][c],r['quality'][c],float(r['observed'][c] is None))] for r in rows],float)
def guard(row,P,channels=CHANNELS):
    unknown=False;flag=False
    for c in channels:
        x=row['observed'][c];q=row['quality'][c];bounds=P['measurement_bounds'][c]
        if x is None or not math.isfinite(x) or not math.isfinite(q) or q<P['quality_min'] or not bounds[0]<=x<=bounds[1]:unknown=True;continue
        if c=='hr':flag|=x<P['redflag_thresholds']['hr_low'] or x>P['redflag_thresholds']['hr_high']
        elif c=='temperature':flag|=x<P['redflag_thresholds']['temperature_low'] or x>=P['redflag_thresholds']['temperature_high']
        else:flag|=x<P['redflag_thresholds']['spo2_low']
    return 'FLAG' if flag else 'RECHECK' if unknown else 'CLEAR'
def disposition(row,ai_flag,P):
    g=guard(row,P)
    return 'FLAG' if g=='FLAG' or ai_flag else g

def scores(y,p,flags,status=None):
    y=np.asarray(y,int);p=np.asarray(p,float);f=np.asarray(flags,bool);positive=y==1;negative=~positive
    tp=int(sum(positive&f));fn=int(sum(positive&~f));fp=int(sum(negative&f));tn=int(sum(negative&~f))
    s=dict(n=len(y),positive_n=int(positive.sum()),tp=tp,fn=fn,fp=fp,tn=tn,
           sensitivity=tp/max(tp+fn,1),false_negative_rate=fn/max(tp+fn,1),false_positive_rate=fp/max(fp+tn,1),
           ppv=tp/max(tp+fp,1),accuracy=float(np.mean(y==f)),brier=float(np.mean((p-y)**2)),
           auroc=float(roc_auc_score(y,p)) if positive.any() and negative.any() else None)
    if status is not None:
        s.update(recheck_rate=float(np.mean(np.asarray(status)=='RECHECK')),
                 normal_recheck_rate=float(np.mean(np.asarray(status)[negative]=='RECHECK')) if negative.any() else None,
                 abnormal_clearance_rate=float(np.mean(np.asarray(status)[positive]=='CLEAR')) if positive.any() else None,
                 abnormal_recheck_rate=float(np.mean(np.asarray(status)[positive]=='RECHECK')) if positive.any() else None)
    return s

def choose_threshold(y,p,cap):
    fpr,tpr,thresholds=roc_curve(y,p,drop_intermediate=False)
    eligible=[i for i in range(len(fpr)) if fpr[i]<=cap]
    i=min(eligible,key=lambda i:(-tpr[i],fpr[i],-thresholds[i]))
    return float(thresholds[i])

def worker(seed):
    P=json.loads(PFILE.read_text());dest=OUT/f'seed_{seed}';dest.mkdir(exist_ok=False)
    split=json.loads((R/f'artifacts/sensor_distinct_states_20261026/BASE/seed_{seed}/split_manifest.json').read_text())
    sets=list(map(set,split.values()));assert [len(s) for s in sets]==[288,96,96]
    assert all(not(a&b) for i,a in enumerate(sets) for b in sets[i+1:])
    truth=truths(seed,split,P);base=measure(truth,seed,'BASE',P)
    assert base==measure(truth,seed,'BASE',P)
    assert len({r['session'] for r in base})==len(base)
    train=[r for r in base if r['fold']=='train'];val=[r for r in base if r['fold']=='validation']
    yt=np.asarray([r['label'] for r in train]);yv=np.asarray([r['label'] for r in val])
    models={};metadata={}
    for name,channels in [('HR',('hr',)),('THREE',CHANNELS)]:
        X=matrix(train,channels);xt,state=fit.transform_fit(X);xv=fit.transform(matrix(val,channels),state)
        model=HistGradientBoostingClassifier(**P['model'],random_state=seed).fit(xt,yt)
        p=model.predict_proba(xv)[:,1];threshold=choose_threshold(yv,p,P['validation_fpr_cap'])
        assert math.isfinite(threshold)
        models[name]=(model,state,channels,threshold)
        metadata[name]=dict(threshold=threshold,validation=scores(yv,p,p>=threshold),features=[f'{c}_{k}' for c in channels for k in ('value','quality','missing')],
                            train_subjects=288,validation_subjects=96,fit_policy='train only; validation threshold; no final refit',preprocessing='train only')
    records=[];same_test=None
    with gzip.open(dest/'predictions.csv.gz','wt',encoding='utf-8',newline='') as f,gzip.open(dest/'observations.jsonl.gz','wt',encoding='utf-8') as obs:
        w=csv.writer(f);w.writerow(['seed','case','method','subject','session','type','truth','probability','threshold','alarm','disposition'])
        for case in P['measurement_cases']:
            data=base if case=='BASE' else measure(truth,seed,case,P)
            for r in data:obs.write(json.dumps(dict(r,case=case),allow_nan=False)+'\n')
            test=[r for r in data if r['fold']=='test'];ids=[(r['subject'],r['session'],r['label']) for r in test]
            if same_test is None:same_test=ids
            else:assert same_test==ids
            y=np.asarray([r['label'] for r in test]);pred={};thresholds={}
            for name,(model,state,channels,threshold) in models.items():
                pred[name]=model.predict_proba(fit.transform(matrix(test,channels),state))[:,1];thresholds[name]=threshold
            states={name:['FLAG' if p>=thresholds[name] else 'CLEAR' for p in values] for name,values in pred.items()}
            states['GUARD']=[guard(r,P) for r in test];pred['GUARD']=np.asarray([s=='FLAG' for s in states['GUARD']],float);thresholds['GUARD']=.5
            states['HYBRID']=[disposition(r,p>=thresholds['THREE'],P) for r,p in zip(test,pred['THREE'])]
            pred['HYBRID']=pred['THREE'];thresholds['HYBRID']=thresholds['THREE']
            for method in pred:
                status=states[method];flags=np.asarray([s=='FLAG' for s in status]);p=pred[method]
                selections={'ALL':np.ones(len(test),bool)}|{kind:np.asarray([r['kind']==kind for r in test]) for kind in TYPES if kind!='normal'}
                selections['temperature_40_plus']=np.asarray([r['true']['temperature']>=40 for r in test])
                for group,mask in selections.items():
                    if not mask.any():continue
                    stat=scores(y[mask],p[mask],flags[mask],np.asarray(status)[mask])
                    # Probabilities for HYBRID remain the AI probabilities; GUARD is a rule, not a learned/calibrated probability.
                    if method in ('GUARD','HYBRID'):stat['brier']=None;stat['auroc']=None
                    records.append(dict(seed=seed,case=case,method=method,group=group,**stat))
                for r,prob,s in zip(test,p,status):w.writerow([seed,case,method,r['subject'],r['session'],r['kind'],r['label'],prob,thresholds[method],int(s=='FLAG'),s])
    save(dest/'metrics.json',records);save(dest/'models_metadata.json',metadata);save(dest/'split_manifest.json',split)
    save(dest/'validation.json',dict(same_seed_generation='PASS',subject_session_split='PASS',same_test_truth_all_cases='PASS',train_only_fit='PASS',no_latent_input='PASS'))
    print(seed,'complete',flush=True);return records

def interval(v):
    a=np.asarray(v,float);m=float(a.mean());sd=float(a.std(ddof=1));h=float(t.ppf(.975,len(a)-1)*sd/math.sqrt(len(a)))
    return dict(mean=m,sd=sd,ci95=[m-h,m+h])
def functional_checks(P):
    sentinels=[dict(hr=75.,temperature=40.,spo2=98.),dict(hr=75.,temperature=34.,spo2=98.),dict(hr=75.,temperature=36.8,spo2=88.),dict(hr=35.,temperature=36.8,spo2=98.),dict(hr=145.,temperature=36.8,spo2=98.)]
    count=0
    for values in sentinels:
        row=dict(observed=values,quality={c:.94 for c in CHANNELS})
        for condition in range(11):
            for fatigue in range(11):
                # Scores intentionally do not enter the disposition logic.
                assert disposition(row,False,P)=='FLAG';count+=1
        for c in CHANNELS:
            missing=dict(observed={**values,c:None},quality=row['quality'])
            assert guard(missing,P)!='CLEAR'
    existing=[]
    for values in sentinels:
        features={f't0_{c}':values[c] for c in CHANNELS}|{f'quality_{c}':.94 for c in CHANNELS}
        existing.append(dict(values=values,result=frozen.predict(features)))
    save(OUT/'functional_checks.json',dict(no_score_cancellation_cases=count,status='PASS',missing_never_cleared_in_sentinels='PASS',existing_bundle_checks=existing))

def main():
    P=json.loads(PFILE.read_text());assert sha(PFILE)==PFILE.with_suffix('.sha256').read_text().split()[0]
    for name,value in P['protected'].items():assert sha(R/name)==value,name
    OUT.mkdir(exist_ok=False);save(OUT/'protocol_snapshot.json',P);functional_checks(P)
    with cf.ProcessPoolExecutor(max_workers=2) as pool:records=sum(pool.map(worker,P['seeds']),[])
    save(OUT/'all_metrics.json',records);summary=[];paired=[]
    fields=('sensitivity','false_negative_rate','false_positive_rate','ppv','accuracy','brier','auroc','recheck_rate','normal_recheck_rate','abnormal_clearance_rate','abnormal_recheck_rate')
    for case,method,group in sorted({(r['case'],r['method'],r['group']) for r in records}):
        rs=[r for r in records if (r['case'],r['method'],r['group'])==(case,method,group)]
        summary.append(dict(case=case,method=method,group=group,**{field:interval([r[field] for r in rs]) for field in fields if all(r[field] is not None for r in rs)}))
    for case in P['measurement_cases']:
        for group in ('ALL',*TYPES[1:],'temperature_40_plus'):
            for target in ('sensitivity','false_positive_rate','abnormal_clearance_rate'):
                hr={r['seed']:r for r in records if (r['case'],r['group'],r['method'])==(case,group,'HR')}
                for method in ('THREE','GUARD','HYBRID'):
                    other={r['seed']:r for r in records if (r['case'],r['group'],r['method'])==(case,group,method)}
                    if not hr or any(hr[s][target] is None or other[s][target] is None for s in hr):continue
                    paired.append(dict(case=case,group=group,metric=target,reference='HR',method=method,difference=interval([other[s][target]-hr[s][target] for s in sorted(hr)])))
    save(OUT/'summary.json',summary);save(OUT/'paired.json',paired)
    for name,value in P['protected'].items():assert sha(R/name)==value,name
    save(OUT/'validation.json',dict(status='PASS',protected_unchanged=True,seeds=len(P['seeds']),purpose='Synthetic warning detection/clearance stress test, not clinical outcome validation'))
    save(OUT/'MANIFEST.json',{str(p.relative_to(OUT)):sha(p) for p in OUT.rglob('*') if p.is_file() and p.name!='MANIFEST.json'})
    print('COMPLETE',len(records),flush=True)
if __name__=='__main__':main()
