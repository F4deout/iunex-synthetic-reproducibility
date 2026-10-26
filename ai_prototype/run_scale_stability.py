"""Fixed-generator scale audit; existing experiments and frozen files remain untouched."""
from pathlib import Path
import concurrent.futures as cf
import csv, gzip, hashlib, json, time, traceback
import numpy as np
from scipy.stats import t
import simulator_pretask_model as sim
import run_pretask_model as run
import audit_pretask_inference_maturity as maturity
import run_v21_tolerance_prediction as e4

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'artifacts'/'scale_stability_20261006'
P = json.loads((OUT/'PROTOCOL.json').read_text(encoding='utf-8'))
KS = P['history_k']

def digest(x):
    return hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest()

def check_rows(rows, idkey, sessionkey, folds):
    ids={f:{r[idkey] for r in rows if r['fold']==f} for f in folds}
    assert all(not(ids[a]&ids[b]) for i,a in enumerate(folds) for b in folds[i+1:])
    assert len({r[sessionkey] for r in rows})==len(rows)
    return {f:sorted(v) for f,v in ids.items()}

def worker(seed):
    dest=OUT/f'seed_{seed}'
    dest.mkdir(exist_ok=False)
    started=time.monotonic()
    sim.verify_lock(); e4.verify_locks()
    pre={k:[] for k in KS}; tol={k:[] for k in KS}
    records=[]; splits={}; hashes=[]
    with gzip.open(dest/'predictions.csv.gz','wt',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['arm','population','seed','k','target','subject','session','truth','prediction'])
        for block in range(4):
            bs=seed+1000003*block
            data=sim.generate(bs)
            histories={k:sim.history_rows(data,'current' if k==0 else 'full',k) for k in KS}
            # Check actual history windows, not just evaluation indices.
            bysub={}
            for r in data['observed']:bysub.setdefault(r['subject_id'],[]).append(r)
            for seq in bysub.values():
                seq.sort(key=lambda x:x['session_index'])
                for i,r in enumerate(seq):
                    if r['phase']=='evaluation':
                        for k in KS:
                            past=seq[max(0,i-k):i]
                            assert len(past)==k and all(x['subject_id']==r['subject_id'] and x['session_index']<r['session_index'] for x in past)
            hashes.append({'block':block,'seed':bs,'pretask_observed':digest(data['observed'])})
            for k,rows in histories.items():
                for r in rows:
                    r['subject_id']=f'B{block}:{r["subject_id"]}';r['session_id']=f'B{block}:{r["session_id"]}'
                pre[k].extend(rows)
            generated=e4.data.build(bs)
            tr=e4.rows_for_seed(generated)
            hashes[-1]['e4_generation']=generated['generation_hash']
            for k,rows in tr.items():
                for r in rows:
                    r['subject']=f'B{block}:{r["subject"]}';r['session']=f'B{block}:{r["session"]}'
                tol[k].extend(rows)
            n=(block+1)*120
            if n not in P['populations']:continue
            splits[str(n)]={'PRETASK':check_rows(pre[0],'subject_id','session_id',['train','validation','test']),
                            'E4':check_rows(tol[0],'subject','session',['train','validation','id_test'])}
            assert [len(v) for v in splits[str(n)]['PRETASK'].values()]==[n*3//5,n//5,n//5]
            for k in KS:
                rows=pre[k]
                assert [r['session_id'] for r in rows]==[r['session_id'] for r in pre[0]]
                assert all(a['targets']==b['targets'] for a,b in zip(rows,pre[0]))
                assert not any(any(token in key for token in ('latent','capacity','tolerance','debt','relative','depletion')) for key in run.keys(rows))
                for target in run.TARGETS:
                    metric,raw,_=run.fit_cont(rows,target)
                    records.append(dict(arm='PRETASK',population=n,seed=seed,k=k,target=target,primary=metric['mae'],**metric))
                    for sid,sub,y,p in raw:w.writerow(['PRETASK',n,seed,k,target,sub,sid,y,p])
                test,y,p=maturity.binary_raw(rows)
                primary=float(np.mean((p-y)**2))
                records.append(dict(arm='PRETASK',population=n,seed=seed,k=k,target='completed',primary=primary,brier=primary,n=len(y)))
                for r,truth,pred in zip(test,y,p):w.writerow(['PRETASK',n,seed,k,'completed',r['subject_id'],r['session_id'],truth,pred])
                rows=tol[k]
                assert [(r['subject'],r['session']) for r in rows]==[(r['subject'],r['session']) for r in tol[0]]
                train=[r for r in rows if r['fold']=='train'];val=[r for r in rows if r['fold']=='validation'];test=[r for r in rows if r['fold']=='id_test']
                names=list(rows[0]['features']);yv=np.array([r['time_minutes'] for r in val])
                trials=[(e4.score(yv,e4.predict_minutes(e4.fit_log_ridge(train,names,a),val))['mae'],a) for a in e4.ALPHAS]
                alpha=min(trials)[1];pred=e4.predict_minutes(e4.fit_log_ridge(train+val,names,alpha),test)
                truth=np.array([r['time_minutes'] for r in test]);metric=e4.score(truth,pred)
                records.append(dict(arm='E4',population=n,seed=seed,k=k,target='E4_stop_minutes',primary=metric['mae'],alpha=alpha,**metric))
                for r,y,p in zip(test,truth,pred):w.writerow(['E4',n,seed,k,'E4_stop_minutes',r['subject'],r['session'],y,p])
            print(f'seed={seed} N={n} completed ({time.monotonic()-started:.1f}s)',flush=True)
    (dest/'metrics.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    (dest/'split_manifest.json').write_text(json.dumps(splits),encoding='utf-8')
    (dest/'generation_hashes.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
    return records

def stats(v,alpha=.05):
    a=np.asarray(v,float);m=float(a.mean());sd=float(a.std(ddof=1));h=float(t.ppf(1-alpha/2,len(a)-1)*sd/np.sqrt(len(a)))
    return {'mean':m,'sd':sd,'ci':[m-h,m+h],'halfwidth':h,'n':len(a)}

def summarize(records):
    lookup={(r['population'],r['seed'],r['k'],r['target']):r['primary'] for r in records}
    curves=[];decisions={};seeds=P['base_seeds']
    for target,tol in P['precision_tolerances'].items():
        for n in P['populations']:
            for repeats in (5,10,20,30):
                ss=seeds[:repeats]
                for k in KS:
                    v=[lookup[n,s,k,target] for s in ss];d=[lookup[n,s,0,target]-lookup[n,s,k,target] for s in ss]
                    curves.append(dict(target=target,population=n,repeats=repeats,k=k,error=stats(v),improvement=stats(d),positive_seeds=sum(x>0 for x in d)))
        effects={n:np.array([lookup[n,s,0,target]-lookup[n,s,20,target] for s in seeds]) for n in P['populations']}
        checks={}
        for n in P['populations']:
            err=stats([lookup[n,s,20,target] for s in seeds]);eff=stats(effects[n]);simult=stats(effects[n],.05/6)
            checks[str(n)]={'error':err,'effect':eff,'simultaneous_effect_ci':simult['ci'],'positive_seeds':int(sum(effects[n]>0)),
                            'direction_pass':bool(sum(effects[n]>0)>=27 and simult['ci'][0]>0),'precision_pass':err['halfwidth']<=tol and eff['halfwidth']<=tol}
        plateau=stats(effects[240]-effects[480],.05/6);original=stats(effects[120]-effects[480],.05/6)
        old_error=stats([lookup[120,s,20,target] for s in seeds[:5]]);old_effect=stats(effects[120][:5])
        decisions[target]={'tolerance':tol,'by_population':checks,'N240_minus_N480_effect':plateau,'N120_minus_N480_effect':original,
                           'plateau_pass':bool(-tol<=plateau['ci'][0] and plateau['ci'][1]<=tol),
                           'original_population_pass':bool(-tol<=original['ci'][0] and original['ci'][1]<=tol),
                           'five_repeat_precision_pass':old_error['halfwidth']<=tol and old_effect['halfwidth']<=tol,
                           'five_error':old_error,'five_effect':old_effect,'new25_effect_N120':stats(effects[120][5:])}
    return {'curves':curves,'decisions':decisions}

def main():
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    assert sha(OUT/'PROTOCOL.json')==(OUT/'PROTOCOL.sha256').read_text().split()[0]
    for name,h in P['files'].items():assert sha(ROOT/name)==h,name
    (OUT/'RUNNER.sha256').write_text(sha(Path(__file__))+'  run_scale_stability.py\n')
    results=[];failures=[]
    with cf.ProcessPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(worker,s):s for s in P['base_seeds']}
        for f in cf.as_completed(futures):
            try:results.extend(f.result())
            except Exception:failures.append({'seed':futures[f],'error':traceback.format_exc()});print(failures[-1],flush=True)
    (OUT/'failures.json').write_text(json.dumps(failures,indent=2))
    if failures:raise RuntimeError('Audit incomplete; inspect failures.json. No parameter changes.')
    summary=summarize(results)
    # Reproduce the original five-seed PRETASK k0/k20 results.
    old=json.loads((ROOT/'artifacts/pretask_model_phase1/results.json').read_text())
    for r in results:
        if r['arm']=='PRETASK' and r['population']==120 and r['seed'] in run.SEEDS and r['k'] in (0,20):
            rec=old['seed_results'][str(r['seed'])]['current' if r['k']==0 else 'full']
            expected=rec['completion']['brier'] if r['target']=='completed' else rec['continuous'][r['target']]['mae']
            assert abs(r['primary']-expected)<1e-9,(r,expected)
    for name,h in P['files'].items():assert sha(ROOT/name)==h,name
    for name,h in P['config_hashes'].items():assert sha(ROOT/name)==h,name
    summary['validation']={'old_pretask_replication':'PASS','frozen_code_and_parameters':'PASS','split_same_sessions_past_history':'PASS','notes':'CI unit is seed; final preprocessing train+validation refit preserved.'}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    (OUT/'all_metrics.json').write_text(json.dumps(results),encoding='utf-8')
    manifest={str(p.relative_to(OUT)):sha(p) for p in OUT.rglob('*') if p.is_file() and p.name!='MANIFEST.json'}
    (OUT/'MANIFEST.json').write_text(json.dumps(manifest,indent=2))
    print('COMPLETE',len(results),'metric records',flush=True)

if __name__=='__main__':main()
