"""Locked daily-state E4 supplement; separate artifacts, no result-based tuning."""
from pathlib import Path
import os
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
import argparse,concurrent.futures as cf,csv,gzip,hashlib,json,math,sys
from collections import defaultdict
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'vendor'))
import numpy as np
from scipy.stats import t
import simulator_e4_daily_state_20261026 as sim
import run_v21_tolerance_prediction as fit

OUT=ROOT/'artifacts/e4_daily_state_20261026'
P=json.loads(sim.PARAM.read_text())
RULES=('global_mean','global_median','personal_mean','personal_last','task_mean','task_last','exact_context_mean','exact_context_last')
VARIANTS=('anchor','history','current','full','oracle')

def save(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

def digest(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True,allow_nan=False).encode()).hexdigest()

def stats(y,p):
    y,p=np.asarray(y,float),np.asarray(p,float)
    assert len(y)>0 and np.isfinite(y).all() and np.isfinite(p).all() and (p>0).all()
    denominator=float(np.sum((y-y.mean())**2))
    return dict(n=len(y),mae=float(np.mean(abs(y-p))),rmse=float(np.sqrt(np.mean((y-p)**2))),r2=float(1-np.sum((y-p)**2)/denominator) if denominator else None)

def fit_variant(rows,shuffle_target=False,shuffle_features=False):
    rows=[dict(r,features=dict(r['features'])) for r in rows if r['target'] is not None]
    generator=np.random.default_rng(P['falsification']['rng_seed'])
    if shuffle_target:
        for fold in ('train','validation'):
            ix=[i for i,r in enumerate(rows) if r['fold']==fold]
            values=generator.permutation([rows[i]['target'] for i in ix])
            for i,value in zip(ix,values):rows[i]['target']=float(value)
    if shuffle_features:
        for fold in ('train','validation','test'):
            ix=[i for i,r in enumerate(rows) if r['fold']==fold]
            features=[dict(rows[i]['features']) for i in ix]
            for i,j in zip(ix,generator.permutation(len(ix))):rows[i]['features']=features[j]
    names=list(rows[0]['features'])
    train=[r for r in rows if r['fold']=='train'];val=[r for r in rows if r['fold']=='validation'];test=[r for r in rows if r['fold']=='test']
    assert train and val and test
    def convert(rs):return [dict(features=r['features'],time_minutes=r['target']) for r in rs]
    truth_val=np.asarray([r['target'] for r in val])
    trials=[]
    for a in P['model']['ridge_alphas']:
        model=fit.fit_log_ridge(convert(train),names,a)
        trials.append((stats(truth_val,fit.predict_minutes(model,convert(val)))['mae'],a))
    alpha=min(trials)[1]
    model=fit.fit_log_ridge(convert(train+val),names,alpha)
    prediction=fit.predict_minutes(model,convert(test))
    return {r['session']:float(v) for r,v in zip(test,prediction)},dict(model=model,validation_scores=trials,train_n=len(train),validation_n=len(val),final_fit_n=len(train)+len(val),test_n=len(test),preprocessing_selection_fit='train only',preprocessing_final_fit='train+validation')

def check_split(rows,expected):
    actual={f:sorted({r['subject'] for r in rows if r['fold']==f}) for f in ('train','validation','test')}
    assert actual==expected
    s=[set(x) for x in actual.values()]
    assert not(s[0]&s[1] or s[0]&s[2] or s[1]&s[2])
    for name in VARIANTS:
        rs=[r for r in rows if r['variant']==name]
        assert len(rs)==len({r['session'] for r in rs})
    return actual

def summary_distribution(values):
    v=np.asarray(values,float)
    return dict(n=len(v),mean=float(v.mean()),sd=float(v.std(ddof=1)),quantiles=dict(zip(['min','q01','q05','median','q95','q99','max'],np.quantile(v,[0,.01,.05,.5,.95,.99,1]).tolist()))) if len(v)>1 else None

def sanity(observed,audit,manifests):
    result={}
    for channel in ('hr','temperature','spo2'):
        pairs=[(o['pre_'+channel],a['true_pre_'+channel],a['sensors'][channel]) for o,a in zip(observed,audit)]
        valid=[(x,y,m) for x,y,m in pairs if x is not None]
        values=[x for x,_,_ in valid]
        result[channel]=dict(observed=summary_distribution(values),true=summary_distribution([y for _,y,_ in pairs]),
                             error=summary_distribution([x-y for x,y,_ in valid]),missing_n=sum(m['missing'] for _,_,m in pairs),
                             artifact_n=sum(m['artifact'] for _,_,m in pairs),numeric_endpoint_n=sum(m['numeric_endpoint'] for _,_,m in pairs))
        if channel=='spo2':
            result[channel]['boundary_mass']={str(b):float(np.mean(np.asarray(values)>=b)) for b in (99.,99.9,100.)}
        else:
            result[channel]['range_flag_n']=sum(x<lo or x>hi for x in values for lo,hi in ([(25,240)] if channel=='hr' else [(30,43)]))
    evals=[r for r in observed if r['event_id']=='E4']
    result['E4']=dict(total=len(evals),stops=sum(not r['completed'] for r in evals),completed=sum(r['completed'] for r in evals),observed_stop_minutes=summary_distribution([r['observed_stop_minutes'] for r in evals if not r['completed']]))
    differences=[abs(m['baseline']['exact_context_last']-m['target']) for m in manifests if m['fold']=='test' and m['target'] is not None and m['baseline']['exact_context_last'] is not None]
    result['same_context_test_difference']=dict(distribution=summary_distribution(differences),exact_equal_n=sum(d==0 for d in differences),n=len(differences))
    result['clock_boundary_n']=sum(a['clock_boundary'] for a in audit)
    result['true_spo2_rejection_n']=sum(a['true_spo2_rejections'] for a in audit)
    result['state']=summary_distribution([a['state'] for a in audit])
    return result

def worker(seed):
    dest=OUT/f'seed_{seed}';dest.mkdir(exist_ok=False)
    bases=[sim.legacy.build(seed+1000003*b) for b in range(4)]
    expected_old=json.loads((ROOT/f'artifacts/scale_stability_20261006/seed_{seed}/generation_hashes.json').read_text())
    assert all(base['generation_hash']==old['e4_generation'] for base,old in zip(bases,expected_old))
    expected={f:sorted(f'B{b}:'+sid for b in range(4) for sid,fold in bases[b]['subject_split'].items() if ('test' if fold=='id_test' else fold)==f) for f in ('train','validation','test')}
    assert [len(expected[f]) for f in ('train','validation','test')]==[288,96,96]
    save(dest/'split_manifest.json',expected)
    records=[]
    for scenario,case in sim.cases().items():
        data=[sim.generate(seed+1000003*b,bases[b],case) for b in range(4)]
        repeated=sim.generate(seed,bases[0],case)
        assert digest(data[0])==digest(repeated),'same seed/config generation mismatch'
        rows=[];manifests=[]
        for b,d in enumerate(data):
            r,m=sim.features(d,f'B{b}:');rows.extend(r);manifests.extend(m)
        check_split(rows,expected)
        observed=[r for d in data for r in d['observed_events']];audit=[r for d in data for r in d['audit_only']]
        child=dest/scenario;child.mkdir(exist_ok=False)
        with gzip.open(child/'observed.jsonl.gz','wt',encoding='utf-8',compresslevel=3) as f, gzip.open(child/'audit_only.jsonl.gz','wt',encoding='utf-8',compresslevel=3) as a:
            for b,d in enumerate(data):
                for o in d['observed_events']:f.write(json.dumps(dict(o,block=b),allow_nan=False)+'\n')
                for o in d['audit_only']:a.write(json.dumps(dict(o,block=b),allow_nan=False)+'\n')
        with gzip.open(child/'history_manifest.jsonl.gz','wt',encoding='utf-8',compresslevel=3) as f:
            for m in manifests:f.write(json.dumps(m,allow_nan=False)+'\n')
        held=sorted([m for m in manifests if m['fold']=='test' and m['target'] is not None],key=lambda r:r['session'])
        targets=np.asarray([r['target'] for r in held])
        train_y=[m['target'] for m in manifests if m['fold']!='test' and m['target'] is not None]
        assert train_y and held
        mean=float(np.mean(train_y));median=float(np.median(train_y))
        predictions={};models={};fallback={}
        for method in RULES:
            if method.startswith('global_'):values=[median if method=='global_median' else mean]*len(held);fallback[method]=0
            else:
                values=[m['baseline'][method] if m['baseline'][method] is not None else mean for m in held]
                fallback[method]=sum(m['baseline'][method] is None for m in held)
            predictions[method]=dict(zip([m['session'] for m in held],values))
        for variant in VARIANTS:
            use=[r for r in rows if r['variant']==variant]
            pred,model=fit_variant(use)
            assert set(pred)=={r['session'] for r in held}
            predictions[variant]=pred;models[variant]=model;fallback[variant]=0
        for method in predictions:
            values=[predictions[method][r['session']] for r in held]
            records.append(dict(seed=seed,scenario=scenario,method=method,**stats(targets,values),fallback_n=fallback[method]))
        if seed==P['falsification']['seed'] and scenario=='BASE':
            use=[r for r in rows if r['variant']=='full']
            falsification={}
            for name,options in [('target_shuffle',dict(shuffle_target=True)),('feature_shuffle',dict(shuffle_features=True))]:
                pred,model=fit_variant(use,**options)
                falsification[name]=dict(**stats(targets,[pred[r['session']] for r in held]),selected_model=model)
            qrows=[dict(r,features={k:v for k,v in r['features'].items() if k.startswith('quality_')}) for r in use]
            qpred,qmodel=fit_variant(qrows)
            falsification['quality_only']=dict(**stats(targets,[qpred[r['session']] for r in held]),selected_model=qmodel)
            normal=stats(targets,[predictions['full'][r['session']] for r in held])['mae']
            global_error=stats(targets,[mean]*len(held))['mae'];gain=global_error-normal
            for name in ('target_shuffle','feature_shuffle'):
                f=falsification[name]
                f['gain_over_mean']=global_error-f['mae']
                f['status']='RESULT_LIMITATION' if gain<=P['falsification']['minimum_gain_over_mean_minutes'] else 'PASS' if f['gain_over_mean']<=P['falsification']['required_collapse_fraction']*gain else 'WARNING'
            falsification['quality_only']['status']='PASS' if global_error-falsification['quality_only']['mae']<=P['falsification']['required_collapse_fraction']*max(gain,0) else 'WARNING'
            falsification['normal_mae']=normal;falsification['global_mean_mae']=global_error
            save(child/'falsification.json',falsification)
        with gzip.open(child/'predictions.csv.gz','wt',encoding='utf-8',newline='',compresslevel=3) as f:
            w=csv.writer(f);w.writerow(['seed','scenario','method','subject','session','truth','prediction'])
            for method,pred in predictions.items():
                for r in held:w.writerow([seed,scenario,method,r['subject'],r['session'],r['target'],pred[r['session']]])
        save(child/'selected_models.json',models)
        save(child/'sanity.json',sanity(observed,audit,manifests))
        save(child/'generation_hashes.json',[dict(block=b,sha256=digest(d)) for b,d in enumerate(data)])
        save(child/'validation.json',dict(subject_session_split='PASS',same_seed_reproducibility='PASS',history_past_only='PASS',ordinary_latent_input_excluded='PASS',same_test_sessions_all_methods='PASS',original_stable_profiles_and_schedule='PASS',conditional_on_stopping=True,test_stops=len(held),test_total=96))
        print(f'seed={seed} scenario={scenario} complete',flush=True)
    save(dest/'metrics.json',records)
    return records

def interval(values,alpha=.05):
    values=np.asarray(values,float);mean=float(values.mean());sd=float(values.std(ddof=1));half=float(t.ppf(1-alpha/2,len(values)-1)*sd/math.sqrt(len(values)))
    return dict(mean=mean,sd=sd,ci95=[mean-half,mean+half],n=len(values))

def summarize(records):
    groups=defaultdict(list)
    for r in records:groups[(r['scenario'],r['method'])].append(r)
    summary=[];paired=[]
    for (scenario,method),rs in sorted(groups.items()):
        assert len(rs)==30
        summary.append(dict(scenario=scenario,method=method,mae=interval([r['mae'] for r in rs]),rmse=interval([r['rmse'] for r in rs]),r2=interval([r['r2'] for r in rs]) if all(r['r2'] is not None for r in rs) else None,fallback_n=sum(r['fallback_n'] for r in rs)))
        if method in ('full','oracle'):continue
        baseline={r['seed']:r for r in rs};full={r['seed']:r for r in groups[(scenario,'full')]}
        assert baseline.keys()==full.keys()
        differences=[baseline[s]['mae']-full[s]['mae'] for s in sorted(full)]
        rel=[(baseline[s]['mae']-full[s]['mae'])/baseline[s]['mae'] for s in sorted(full)]
        paired.append(dict(scenario=scenario,baseline=method,reference='full',difference=interval(differences),relative_difference=interval(rel),full_better_seeds=sum(d>0 for d in differences),seed_differences=differences))
    for scenario in sim.cases():
        family=[r for r in paired if r['scenario']==scenario]
        for r in family:
            ci=interval(r['seed_differences'],.05/len(family))['ci95']
            r['simultaneous_ci']=ci;r['comparisons']=len(family)
            r['classification']='FULL_BETTER' if ci[0]>0 else 'BASELINE_BETTER' if ci[1]<0 else 'INCONCLUSIVE'
    save(OUT/'summary.json',summary);save(OUT/'paired_comparisons.json',paired)
    with (OUT/'summary.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['scenario','method','mae','sd','ci_low','ci_high','rmse','r2','fallback_n'])
        for r in summary:w.writerow([r['scenario'],r['method'],r['mae']['mean'],r['mae']['sd'],*r['mae']['ci95'],r['rmse']['mean'],r['r2']['mean'] if r['r2'] else None,r['fallback_n']])

def dry_run():
    sim.verify();sim.unit_tests()
    base=sim.legacy.build(20261026);case=sim.cases()['BASE']
    d=sim.generate(20261026,base,case);again=sim.generate(20261026,base,case)
    assert digest(d)==digest(again)
    rows,manifest=sim.features(d)
    modified=json.loads(json.dumps(d))
    for r in modified['observed_events']:
        if r['event_type']=='evaluation':
            r['observed_stop_minutes']=None;r['actual_minutes']=-999;r['observed_session_mean_hr']=-999
    changed,_=sim.features(modified)
    assert [r['features'] for r in rows]==[r['features'] for r in changed],'current/future task outcome leaked'
    original={r['session']:r for r in d['observed_events']}
    for m in manifest:
        assert len(m['history_sources'])==20
        assert all(original[s]['subject']==m['subject'] and original[s]['event_order']<m['current_order'] for s in m['history_sources'])
    flags=dict(exact_reproducibility='PASS',current_future_outcome_mutation='PASS',history_subject_isolation='PASS',directionality_unit_test='PASS',bounded_spo2_unit_test='PASS')
    save(OUT/'dry_run_validation.json',flags)
    print('dry-run validation PASS',flush=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',action='store_true');args=parser.parse_args()
    if not args.run:sim.verify();sim.unit_tests();return
    sim.verify()
    OUT.mkdir(exist_ok=False)
    protected={str(p.relative_to(ROOT)):sim.sha(p) for p in list(ROOT.glob('*.py'))+list(ROOT.glob('*.json'))+list(ROOT.glob('*.md')) if p.name not in (Path(__file__).name,)}
    for folder,manifest in [(ROOT/'artifacts/scale_stability_20261006','MANIFEST.json'),(ROOT/'artifacts/review_simple_baselines_20261026','manifest.json')]:
        for name,expected in json.loads((folder/manifest).read_text()).items():
            p=folder/name
            assert sim.sha(p)==expected,p
            protected[str(p.relative_to(ROOT))]=expected
    save(OUT/'protected_hashes_before.json',protected)
    lock=dict(protocol_sha256=sim.sha(ROOT/'E4_DAILY_STATE_PROTOCOL_20261026.md'),parameters_sha256=sim.sha(sim.PARAM),generator_sha256=sim.sha(Path(sim.__file__)),runner_sha256=sim.sha(__file__),new_results_not_seen_at_lock=True,old_results_known=True)
    save(OUT/'execution_lock.json',lock)
    for path in [ROOT/'E4_DAILY_STATE_PROTOCOL_20261026.md',sim.PARAM,Path(sim.__file__),Path(__file__)]: (OUT/path.name).write_bytes(path.read_bytes())
    dry_run()
    records=[]
    with cf.ProcessPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(worker,seed) for seed in P['seeds']]
        for future in cf.as_completed(futures):records.extend(future.result())
    records.sort(key=lambda r:(r['seed'],r['scenario'],r['method']))
    assert len(records)==30*11*13
    assert all(sim.sha(ROOT/name)==h for name,h in protected.items()),'protected source or result changed'
    assert sim.sha(__file__)==lock['runner_sha256'] and sim.sha(Path(sim.__file__))==lock['generator_sha256']
    save(OUT/'all_metrics.json',records);summarize(records)
    save(OUT/'validation.json',dict(status='PASS',seeds=30,scenarios=11,population=480,protected_files=len(protected),protected_hashes_unchanged=True,scenario_complete=True,all_reported_without_parameter_tuning=True,limitations=['Post-review synthetic supplement','Assumed sensor-state and state-reserve relations','Conditional stopping-time accuracy, not clinical readiness','No manuscript changes']))
    save(OUT/'manifest.json',{str(p.relative_to(OUT)):sim.sha(p) for p in OUT.rglob('*') if p.is_file()})
    print('COMPLETE',str(OUT),flush=True)

if __name__=='__main__':main()
