"""Post-review simple baselines on frozen paper test sessions; no simulator edits."""
from pathlib import Path
import os
for _key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[_key] = '1'
import argparse, concurrent.futures as cf, csv, gzip, hashlib, json, math, sys
from collections import defaultdict
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'vendor'))
import numpy as np
from scipy.stats import t
from scipy.special import expit
import simulator_pretask_model as pre
import simulator_rq1_physiological_history_value as phv
import run_pretask_model as fit
import run_v21_tolerance_prediction as e4

PROTOCOL = ROOT/'REVIEW_SIMPLE_BASELINES_PROTOCOL_20261026.json'
OUT = ROOT/'artifacts/review_simple_baselines_20261026'
SCALE = ROOT/'artifacts/scale_stability_20261006'
FOLLOW = ROOT/'artifacts/rq1_physiological_history_value_phase1'
RULES = ('global_mean','global_median','personal_mean','personal_last','task_mean','task_last','exact_context_mean','exact_context_last')

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def save(p, obj):
    p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

def normal(row, branch, prefix=''):
    if branch=='E4':
        return dict(subject=prefix+row['subject'],session=prefix+row['session'],
                    fold='test' if row['fold']=='id_test' else row['fold'],order=row['event_order'],
                    phase=row['event_type'],task='E4',anchor=row['v5_kmh'],demand=row['u_anchor'],
                    duration=row['planned_minutes'],gap=row['gap_h'],
                    targets={'E4_stop_minutes':row['observed_stop_minutes']},
                    outcomes={'E4_stop_minutes':row['observed_stop_minutes']})
    follow=branch!='PRETASK'
    target_map={'pre_fatigue':'pre_fatigue','pre_condition':'pre_condition','post_burden':'post_burden','completed':'completed',
                'recovery_delay_h' if follow else 'recovery_delay':'recovery_delay_h' if follow else 'recovery_delay'}
    if follow: target_map['stop_time_min']='observed_stop_time_min'
    targets={name:row['targets'][name] for name in target_map}
    outcomes={name:row['history_observable'][source] for name,source in target_map.items()}
    return dict(subject=prefix+row['subject_id'],session=prefix+row['session_id'],fold=row['fold'],
                order=row['session_index'],phase=row['phase'],task=row['task_type'],anchor=row['observed_anchor'],
                demand=row['planned_demand'],duration=row['planned_duration_min' if follow else 'planned_duration'],
                gap=row['gap_days'],targets=targets,outcomes=outcomes)

def samples(observed, branch, prefix=''):
    grouped=defaultdict(list)
    for r in observed:
        n=normal(r,branch,prefix); grouped[n['subject']].append(n)
    result=[]
    for subject,seq in grouped.items():
        seq.sort(key=lambda x:x['order'])
        for i,r in enumerate(seq):
            if r['phase']!='evaluation': continue
            if branch=='E4':
                if r['duration']!=12 or not r['session']: continue
                # E4 uses the original fixed calibration window, not preceding evaluation sessions.
                original=next(x for x in observed if prefix+x['session']==r['session'])
                if original['event_id']!='E4': continue
                past=[x for x in seq if x['phase']=='calibration'][-20:]
            else: past=seq[max(0,i-20):i]
            assert len(past)==20
            assert all(x['subject']==subject and x['order']<r['order'] and x['session']!=r['session'] for x in past)
            result.append(dict(r,past=past))
    return sorted(result,key=lambda x:(x['subject'],x['session']))

def split_check(rows, expected):
    actual={f:sorted({r['subject'] for r in rows if r['fold']==f}) for f in ('train','validation','test')}
    expected={('test' if k=='id_test' else k):v for k,v in expected.items()}
    assert actual==expected, 'split manifest mismatch'
    sets=list(map(set,actual.values()))
    assert not (sets[0]&sets[1] or sets[0]&sets[2] or sets[1]&sets[2])
    assert len({r['session'] for r in rows})==len(rows)
    return actual

def close(a,b):
    return math.isclose(a,b,rel_tol=0,abs_tol=1e-9)

def eligible(current,target,method):
    past=current['past']
    if method.startswith('exact_context'):
        past=[p for p in past if p['task']==current['task'] and all(close(p[k],current[k]) for k in ('demand','duration','gap'))]
    elif method.startswith('task_'):
        past=[p for p in past if p['task']==current['task'] and (current['task']!='E4' or close(p['demand'],current['demand']))]
    return [p['outcomes'][target] for p in past if p['outcomes'][target] is not None]

def rule_predict(current,target,method,fallback):
    values=eligible(current,target,method)
    if not values: return fallback, True
    return float(values[-1] if method.endswith('last') else np.mean(values)), False

def metric(y,p,target):
    y,p=np.asarray(y,float),np.asarray(p,float)
    assert len(y)>0 and np.isfinite(y).all() and np.isfinite(p).all()
    if target=='completed':
        assert ((p>=0)&(p<=1)).all()
        pos=int(sum(y==1)); neg=len(y)-pos
        # Tied ranks matter for constant/last-value probability predictors.
        from scipy.stats import rankdata
        auc=float((rankdata(p)[y==1].sum()-pos*(pos+1)/2)/(pos*neg)) if pos and neg else None
        ece=0.
        for lo in np.linspace(0,.9,10):
            mask=(p>=lo)&((p<lo+.1) if lo<.9 else (p<=1))
            if mask.any(): ece+=float(mask.mean()*abs(y[mask].mean()-p[mask].mean()))
        brier=float(np.mean((y-p)**2))
        return dict(n=len(y),primary=brier,brier=brier,positive_rate=float(y.mean()),auroc=auc,ece10=ece)
    denom=float(np.sum((y-y.mean())**2))
    mae=float(np.mean(abs(y-p)))
    return dict(n=len(y),primary=mae,mae=mae,rmse=float(np.sqrt(np.mean((y-p)**2))),r2=float(1-np.sum((y-p)**2)/denom) if denom else None)

def design(rows,branch):
    if branch=='E4': return np.asarray([[r['anchor'],r['order']] for r in rows],float)
    return np.asarray([[r['anchor'],r['demand'],r['duration'],r['gap']]+[float(r['task']==k) for k in pre.TASKS] for r in rows],float)

def anchor_predict(rows,target,branch):
    use=[r for r in rows if r['targets'][target] is not None]
    X=design(use,branch); y=np.asarray([r['targets'][target] for r in use],float)
    folds=np.asarray([r['fold'] for r in use]); train=folds=='train'; val=folds=='validation'; test=folds=='test'
    assert train.any() and val.any() and test.any()
    xt,state=fit.transform_fit(X[train]); xv=fit.transform(X[val],state)
    grid=(.1,1.,10.) if target=='completed' else (1.,10.,100.)
    logged=branch=='E4'
    def predict(x,yy,xp,alpha):
        if target=='completed': return fit.logistic(x,yy,xp,alpha)
        pred=fit.ridge(x,np.log(yy) if logged else yy,xp,alpha)
        return np.exp(pred) if logged else pred
    scores=[(metric(y[val],predict(xt,y[train],xv,a),target)['primary'],a) for a in grid]
    alpha=min(scores)[1]
    final=train|val; xf,state=fit.transform_fit(X[final]); xe=fit.transform(X[test],state)
    p=predict(xf,y[final],xe,alpha)
    return {r['session']:float(v) for r,v in zip([r for r in use if r['fold']=='test'],p)},dict(alpha=alpha,validation_scores=scores,train_n=int(sum(train)),validation_n=int(sum(val)),final_fit_n=int(sum(final)),test_n=int(sum(test)),feature_names=['anchor','evaluation_order'] if branch=='E4' else ['anchor','planned_demand','planned_duration','gap']+['task_'+x for x in pre.TASKS])

def evaluate(rows,branch,seed,reference,writer):
    records=[]; fits={}
    test=[r for r in rows if r['fold']=='test']
    assert len({r['session'] for r in test})==len(test)
    targets=list(rows[0]['targets'])
    for target in targets:
        held=[r for r in test if r['targets'][target] is not None]
        truths=np.asarray([r['targets'][target] for r in held],float)
        fit_y=[r['targets'][target] for r in rows if r['fold']!='test' and r['targets'][target] is not None]
        assert fit_y
        mean,median=float(np.mean(fit_y)),float(np.median(fit_y))
        methods=tuple(x for x in RULES if target!='completed' or x!='global_median')+('anchor_context',)
        anchor, fit_info=anchor_predict(rows,target,branch); fits[target]=fit_info
        def emit(method,values,flags):
            record=dict(arm=branch,seed=seed,target=target,method=method,**metric(truths,values,target),fallback_n=sum(flags))
            records.append(record)
            for row,y,p,flag in zip(held,truths,values,flags):
                writer.writerow([branch,seed,target,method,row['subject'],row['session'],float(y),float(p),int(flag)])
        for method in methods:
            if method=='anchor_context': values=[anchor[r['session']] for r in held]; flags=[False]*len(held)
            elif method.startswith('global_'): values=[median if method=='global_median' else mean]*len(held); flags=[False]*len(held)
            else:
                pairs=[rule_predict(r,target,method,mean) for r in held]
                values,flags=zip(*pairs)
            emit(method,values,flags)
        for method,saved in reference.items():
            # Every reference must have exactly the same observed target test sessions.
            pairs=saved[target]
            assert set(pairs)=={r['session'] for r in held}, (branch,seed,target,method,'session mismatch')
            assert all(float(r['targets'][target])==pairs[r['session']][0] for r in held), 'target mismatch'
            emit(method,[pairs[r['session']][1] for r in held],[False]*len(held))
    return records,fits

def scale_reference(seed):
    result={f'saved_k{k}':defaultdict(dict) for k in (0,20)}
    path=SCALE/f'seed_{seed}/predictions.csv.gz'
    manifest=json.loads((SCALE/'MANIFEST.json').read_text())
    assert sha(path)==manifest[str(path.relative_to(SCALE))]
    with gzip.open(path,'rt',encoding='utf-8',newline='') as f:
        for r in csv.DictReader(f):
            if r['population']=='480' and r['k'] in ('0','20'):
                result['saved_k'+r['k']][r['target']][r['session']]=(float(r['truth']),float(r['prediction']))
    return result

def work_main(seed):
    records=[]; all_splits={}; manifests=[]
    reference=scale_reference(seed)
    expected=json.loads((SCALE/f'seed_{seed}/split_manifest.json').read_text())['480']
    expected_hash=json.loads((SCALE/f'seed_{seed}/generation_hashes.json').read_text())
    rows_by_branch={'PRETASK':[],'E4':[]}
    for block in range(4):
        bs=seed+1000003*block; data=pre.generate(bs)
        assert hashlib.sha256(json.dumps(data['observed'],sort_keys=True).encode()).hexdigest()==expected_hash[block]['pretask_observed']
        rows_by_branch['PRETASK'].extend(samples(data['observed'],'PRETASK',f'B{block}:'))
        generated=e4.data.build(bs)
        assert generated['generation_hash']==expected_hash[block]['e4_generation']
        rows_by_branch['E4'].extend(samples(generated['observed_events'],'E4',f'B{block}:'))
    dest=OUT/f'main_seed_{seed}'; dest.mkdir(exist_ok=False)
    with gzip.open(dest/'predictions.csv.gz','wt',encoding='utf-8',newline='') as f, gzip.open(dest/'history_manifest.jsonl.gz','wt',encoding='utf-8') as h:
        writer=csv.writer(f); writer.writerow(['arm','seed','target','method','subject','session','truth','prediction','fallback'])
        fits={}
        for branch,rows in rows_by_branch.items():
            all_splits[branch]=split_check(rows,expected[branch])
            targets=set(rows[0]['targets'])
            ref={m:{k:v for k,v in d.items() if k in targets} for m,d in reference.items()}
            rec,fitted=evaluate(rows,branch,seed,ref,writer); records.extend(rec); fits[branch]=fitted
            for r in rows:
                if r['fold']=='test': h.write(json.dumps(dict(arm=branch,session=r['session'],subject=r['subject'],sources=[p['session'] for p in r['past']],orders=[p['order'] for p in r['past']],order=r['order']))+'\n')
    save(dest/'metrics.json',records); save(dest/'selected_models.json',fits); save(dest/'split_manifest.json',all_splits)
    save(dest/'validation.json',dict(generation_hash_match=True,subject_split_match=True,history_past_same_subject=True,same_saved_sessions_and_truth=True,test_not_used_for_selection=True))
    print(f'MAIN seed={seed} complete',flush=True)
    return records

def follow_reference():
    result={}
    with gzip.open(FOLLOW/'raw_predictions.jsonl.gz','rt',encoding='utf-8') as f:
        for line in f:
            r=json.loads(line)
            if r['k']!=20 or r['condition'] not in ('C1','C5','C6','C7'): continue
            key=(r['dataset'],r['seed']); result.setdefault(key,{x:defaultdict(dict) for x in ('C1','C5','C6','C7')})
            dest=result[key][r['condition']]; sid=r['session_id']
            for target in ('pre_fatigue','pre_condition','post_burden','recovery_delay_h'):
                dest[target][sid]=(r['truth_continuous'][target],r['prediction_continuous'][target])
            dest['completed'][sid]=(r['truth_completed'],r['prediction_completed'])
            if r['truth_stop_time_min'] is not None:
                dest['stop_time_min'][sid]=(r['truth_stop_time_min'],r['prediction_stopped_only_min'])
    return result

def work_follow(seed,dataset):
    data=phv.generate(seed,dataset)
    rows=samples(data['observed'],dataset)
    expected=json.loads((FOLLOW/'split_manifest.json').read_text())[str(seed)][dataset]
    splits=split_check(rows,expected)
    reference=json.loads((OUT/f'follow_reference_{dataset}_{seed}.json').read_text())
    dest=OUT/f'follow_{dataset}_{seed}'; dest.mkdir(exist_ok=False)
    with gzip.open(dest/'predictions.csv.gz','wt',encoding='utf-8',newline='') as f, gzip.open(dest/'history_manifest.jsonl.gz','wt',encoding='utf-8') as h:
        writer=csv.writer(f); writer.writerow(['arm','seed','target','method','subject','session','truth','prediction','fallback'])
        records,fits=evaluate(rows,dataset,seed,reference,writer)
        for r in rows:
            if r['fold']=='test': h.write(json.dumps(dict(session=r['session'],subject=r['subject'],sources=[p['session'] for p in r['past']],orders=[p['order'] for p in r['past']],order=r['order']))+'\n')
    save(dest/'metrics.json',records); save(dest/'selected_models.json',fits); save(dest/'split_manifest.json',splits)
    save(dest/'validation.json',dict(subject_split_match=True,history_past_same_subject=True,same_saved_sessions_and_truth=True,no_latent_inputs=True,test_not_used_for_selection=True))
    print(f'FOLLOW {dataset} seed={seed} complete',flush=True)
    return records

def interval(values,alpha=.05):
    x=np.asarray(values,float); mean=float(x.mean()); sd=float(x.std(ddof=1)); half=float(t.ppf(1-alpha/2,len(x)-1)*sd/math.sqrt(len(x)))
    return dict(mean=mean,sd=sd,ci95=[mean-half,mean+half],n=len(x))

def summarize(records):
    groups=defaultdict(list)
    for r in records: groups[(r['arm'],r['target'],r['method'])].append(r)
    summary=[]; paired=[]
    for (arm,target,method),rs in sorted(groups.items()):
        item=dict(arm=arm,target=target,method=method,primary=interval([r['primary'] for r in rs]),fallback_total=sum(r['fallback_n'] for r in rs),test_total=sum(r['n'] for r in rs))
        for name in ('mae','rmse','r2','brier','positive_rate','auroc','ece10'):
            if all(r.get(name) is not None for r in rs): item[name]=interval([r[name] for r in rs])
        summary.append(item)
        if method.startswith('saved_') or method in ('C1','C5','C6','C7'): continue
        references=('saved_k0','saved_k20') if arm in ('PRETASK','E4') else ('C1','C5','C6','C7')
        for ref in references:
            baseline={r['seed']:r for r in rs}; model={r['seed']:r for r in groups[(arm,target,ref)]}
            assert baseline.keys()==model.keys()
            diff=[baseline[s]['primary']-model[s]['primary'] for s in sorted(baseline)]
            relative=[(baseline[s]['primary']-model[s]['primary'])/baseline[s]['primary'] for s in sorted(baseline) if baseline[s]['primary']>0]
            paired.append(dict(arm=arm,target=target,baseline=method,reference=ref,difference=interval(diff),relative_difference=interval(relative) if len(relative)==len(diff) else None,relative_unavailable_seeds=len(diff)-len(relative),model_better_seeds=sum(d>0 for d in diff),paired_seed_differences=diff))
    for arm in {r['arm'] for r in paired}:
        comparisons=[r for r in paired if r['arm']==arm]; count=len(comparisons)
        for r in comparisons:
            ci=interval(r['paired_seed_differences'],.05/count)['ci95']
            r['simultaneous_ci']=ci; r['bonferroni_comparisons']=count
            r['classification']='MODEL_BETTER' if ci[0]>0 else 'BASELINE_BETTER' if ci[1]<0 else 'INCONCLUSIVE'
    save(OUT/'summary.json',summary); save(OUT/'paired_comparisons.json',paired)
    with (OUT/'summary.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['arm','target','method','mean','sd','ci_low','ci_high','fallback_total','test_total'])
        for r in summary:w.writerow([r['arm'],r['target'],r['method'],r['primary']['mean'],r['primary']['sd'],*r['primary']['ci95'],r['fallback_total'],r['test_total']])

def self_test():
    r=dict(subject='A',session='A3',order=3,task='X',demand=1.,duration=10.,gap=1.,targets={'y':999},past=[
        dict(subject='A',session='A1',order=1,task='X',demand=1.,duration=10.,gap=1.,outcomes={'y':2.}),
        dict(subject='A',session='A2',order=2,task='Y',demand=1.,duration=10.,gap=1.,outcomes={'y':8.})])
    assert rule_predict(r,'y','personal_mean',0)==(5.,False)
    assert rule_predict(r,'y','personal_last',0)==(8.,False)
    assert rule_predict(r,'y','exact_context_last',0)==(2.,False)
    r['targets']['y']=-999
    assert rule_predict(r,'y','personal_mean',0)==(5.,False)
    r['task']='Z'; assert rule_predict(r,'y','task_last',7)==(7,True)
    assert metric([0,1],[.5,.5],'completed')['auroc']==.5
    assert metric([1,2],[1,2],'y')['primary']==0
    print('baseline self-tests PASS',flush=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',action='store_true');args=parser.parse_args()
    self_test()
    if not args.run:return
    assert sha(PROTOCOL)==PROTOCOL.with_suffix('.sha256').read_text().strip()
    protocol=json.loads(PROTOCOL.read_text())
    OUT.mkdir(exist_ok=False)
    protected={}
    for p in list(ROOT.glob('*.py'))+list(ROOT.glob('*.json'))+list(ROOT.glob('*.md')):
        if p.name!=Path(__file__).name: protected[str(p.relative_to(ROOT))]=sha(p)
    for folder,manifest in ((SCALE,'MANIFEST.json'),(FOLLOW,'PHASE1_FREEZE_SHA256.json')):
        for name,expected in json.loads((folder/manifest).read_text()).items():
            p=folder/name
            if p.is_file():
                assert sha(p)==expected,(p,'old artifact hash mismatch')
                protected[str(p.relative_to(ROOT))]=expected
    save(OUT/'preserved_hashes_before.json',protected)
    save(OUT/'execution_lock.json',dict(protocol_sha256=sha(PROTOCOL),runner_sha256=sha(__file__),analysis_started_after_lock=True,original_results_previously_known=True))
    (OUT/'protocol_snapshot.json').write_bytes(PROTOCOL.read_bytes())
    (OUT/'runner_snapshot.py').write_bytes(Path(__file__).read_bytes())
    refs=follow_reference()
    for (dataset,seed),ref in refs.items():save(OUT/f'follow_reference_{dataset}_{seed}.json',ref)
    records=[]
    with cf.ProcessPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(work_main,s) for s in protocol['main']['seeds']]
        futures += [pool.submit(work_follow,s,d) for d in protocol['followup']['datasets'] for s in protocol['followup']['seeds']]
        for future in cf.as_completed(futures):records.extend(future.result())
    assert all(sha(ROOT/name)==digest for name,digest in protected.items()),'protected file changed'
    records.sort(key=lambda r:(r['arm'],r['seed'],r['target'],r['method']))
    save(OUT/'all_metrics.json',records);summarize(records)
    save(OUT/'validation.json',dict(self_tests='PASS',original_hashes='PASS',original_protected_files=len(protected),main_seeds=30,followup_seeds_each=5,all_workers_completed=True,no_simulator_or_original_model_changes=True,no_manuscript_changes=True,post_review_reused_test_data=True,limitations=['Not independent confirmation','No mixed-effects or sensor ablation','No latent-target history baselines','No new survival C-index analysis']))
    manifest={str(p.relative_to(OUT)):sha(p) for p in OUT.rglob('*') if p.is_file()}
    save(OUT/'manifest.json',manifest)
    print('COMPLETE',str(OUT),flush=True)

if __name__=='__main__':main()
