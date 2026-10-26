"""Chronological PMData ridge baselines. No neural-network performance claim.

Target: next-calendar-day PMSys fatigue response (1 tired .. 5 fresh).
Daily derived Fitbit values are treated as available at UTC day end; publication
timestamps are unavailable. This is a retrospective assumption, not proven live latency.
"""
import argparse, csv, datetime as dt, hashlib, json, math
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'/'pmdata'
OUT=ROOT/'artifacts'
UTC=dt.timezone.utc
BASE=['resting_hr','sleep_score','sleep_hours','light_minutes','moderate_minutes',
      'vigorous_minutes','exercise_minutes','session_load','last_fatigue','fatigue_age_days']
PERSONAL=['mean_fatigue','sd_fatigue','n_prior_reports','hr_deviation','sleep_deviation','activity_deviation']
TRAIN_END='2020-01-15'
VAL_END='2020-02-15'
RESPONSE=['activity_deviation','session_load','sleep_deviation','hr_deviation','last_fatigue']
MIN_RESPONSE_RECORDS=12

def response_matrix(shared,rows):
    indices=[shared['names'].index(k) for k in RESPONSE]
    x=matrix(rows,RESPONSE)
    med=np.array(shared['median'])[indices]
    mean=np.array(shared['mean'])[indices]
    scale=np.array(shared['scale'])[indices]
    # Missing values contribute zero correction, not an invented personal response.
    return np.column_stack([np.ones(len(rows)),np.where(np.isnan(x),0,(x-mean)/scale)])

def fit_response(shared,rows,alpha):
    profiles={}
    for subject in sorted({r['subject'] for r in rows}):
        personal_rows=[r for r in rows if r['subject']==subject]
        if len(personal_rows)<MIN_RESPONSE_RECORDS: continue
        z=response_matrix(shared,personal_rows)
        residual=np.array([r['target'] for r in personal_rows])-predict(shared,personal_rows)
        # All corrections shrink toward zero (= shared model), including the intercept.
        coef=np.linalg.solve(z.T@z+alpha*np.eye(z.shape[1]),z.T@residual)
        profiles[subject]={'coef':coef.tolist(),'n':len(personal_rows),
                           'trained_until':max(r['date'] for r in personal_rows)}
    return {'shared':shared,'profiles':profiles,'response_alpha':alpha,
            'response_names':RESPONSE,'minimum_records':MIN_RESPONSE_RECORDS}

def response_details(model,record):
    subject=record.get('subject')
    profile=model['profiles'].get(subject) if isinstance(subject,str) else None
    if profile and (not record.get('date') or record['date']<=profile['trained_until']):
        profile=None
    if profile is None:
        return {'mode':'shared_fallback','training_records':0,'correction':0.0,
                'reason':'No eligible personal profile before the prediction date'}
    contributions=response_matrix(model['shared'],[record])[0]*np.array(profile['coef'])
    return {'mode':'personal_response','training_records':profile['n'],
            'trained_until':profile['trained_until'],'correction':float(contributions.sum()),
            'contributions':dict(zip(['intercept']+RESPONSE,contributions.tolist())),
            'coefficients_per_shared_sd':dict(zip(['intercept']+RESPONSE,profile['coef']))}

def stamp(s):
    t=dt.datetime.fromisoformat(str(s).strip().replace('Z','+00:00'))
    return t.replace(tzinfo=UTC) if t.tzinfo is None else t.astimezone(UTC)

def number(x):
    try:
        v=float(x)
        return v if math.isfinite(v) else None
    except (ValueError,TypeError): return None

def read_csv(path):
    if not path.exists(): return []
    with path.open(encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))

def avg(values):
    values=[v for v in values if v is not None]
    return float(np.mean(values)) if values else None

def load_subject(path):
    wellness=[]
    for r in read_csv(path/'pmsys'/'wellness.csv'):
        try: t=stamp(r['effective_time_frame'])
        except (ValueError,KeyError): continue
        y=number(r.get('fatigue'))
        if y is None or y not in (1,2,3,4,5): continue
        wellness.append({'time':t,'fatigue':y,'sleep_hours':number(r.get('sleep_duration_h'))})
    wellness.sort(key=lambda r:r['time'])
    # One target per person/day; choose last report, deterministically.
    byday={r['time'].date():r for r in wellness}
    wellness=[byday[k] for k in sorted(byday)]
    daily={}
    def put(day,key,value): daily.setdefault(day,{})[key]=value
    for filename,key in [('resting_heart_rate.json','resting_hr'),('lightly_active_minutes.json','light_minutes'),
                         ('moderately_active_minutes.json','moderate_minutes'),('very_active_minutes.json','vigorous_minutes')]:
        file=path/'fitbit'/filename
        if not file.exists(): continue
        for r in json.loads(file.read_text(encoding='utf-8')):
            try: day=stamp(r['dateTime']).date()
            except (KeyError,ValueError): continue
            v=r.get('value'); v=v.get('value') if isinstance(v,dict) else v
            put(day,key,number(v))
    for r in read_csv(path/'fitbit'/'sleep_score.csv'):
        try: day=stamp(r['timestamp']).date()
        except (KeyError,ValueError): continue
        put(day,'sleep_score',number(r.get('overall_score')))
    for r in wellness: put(r['time'].date(),'sleep_hours',r['sleep_hours'])
    sessions=[]
    for r in read_csv(path/'pmsys'/'srpe.csv'):
        try: t=stamp(r['end_date_time'])
        except (KeyError,ValueError): continue
        minutes=number(r.get('duration_min')); rpe=number(r.get('perceived_exertion'))
        if minutes is None or minutes<0: continue
        sessions.append({'time':t,'minutes':minutes,'load':minutes*rpe if rpe is not None and 0<=rpe<=10 else None})
    # An absent session report is not a confirmed rest day; retain missing values.
    for day in {r['time'].date() for r in sessions}:
        rs=[r for r in sessions if r['time'].date()==day]
        put(day,'exercise_minutes',sum(r['minutes'] for r in rs))
        put(day,'session_load',sum(r['load'] for r in rs) if all(r['load'] is not None for r in rs) else None)
    return {'id':path.name,'wellness':wellness,'daily':daily}

def features(subject,target_day):
    """Never read target-day or future observations. Fixed 28-day past baseline."""
    cutoff=dt.datetime.combine(target_day,dt.time.min,tzinfo=UTC)
    yesterday=target_day-dt.timedelta(days=1)
    past=[r for r in subject['wellness'] if cutoff-dt.timedelta(days=28)<=r['time']<cutoff]
    if len(past)<3: return None
    age=(target_day-past[-1]['time'].date()).days
    if age>7: return None
    prior_day=subject['daily'].get(yesterday,{})
    if sum(prior_day.get(k) is not None for k in ('resting_hr','sleep_score','light_minutes','moderate_minutes','vigorous_minutes'))<2: return None
    f={key:prior_day.get(key) for key in BASE}
    f['last_fatigue']=past[-1]['fatigue']; f['fatigue_age_days']=age
    f['mean_fatigue']=avg([r['fatigue'] for r in past]); f['sd_fatigue']=float(np.std([r['fatigue'] for r in past])); f['n_prior_reports']=len(past)
    # Reference interval excludes yesterday, so deviations retain recent change.
    earlier=[r for day,r in subject['daily'].items() if target_day-dt.timedelta(days=28)<=day<yesterday]
    for source,dest in [('resting_hr','hr_deviation'),('sleep_score','sleep_deviation'),('vigorous_minutes','activity_deviation')]:
        ref=avg([r.get(source) for r in earlier]); v=f.get(source)
        f[dest]=v-ref if v is not None and ref is not None else None
    return f

def load_all():
    return [load_subject(p) for p in sorted(DATA.glob('p[0-9][0-9]')) if (p/'pmsys'/'wellness.csv').exists()]

def records(subjects):
    rows=[]; audit=[]
    for s in subjects:
        valid=0
        for r in s['wellness']:
            day=r['time'].date(); f=features(s,day)
            if f is None: continue
            rows.append({'subject':s['id'],'date':day.isoformat(),'target':r['fatigue'],'features':f}); valid+=1
        audit.append({'subject':s['id'],'reports':len(s['wellness']),'eligible':valid,'excluded':len(s['wellness'])-valid})
    return rows,audit

def matrix(rows,names):
    return np.array([[r['features'].get(k) if r['features'].get(k) is not None else np.nan for k in names] for r in rows],dtype=float)

def transform(x,med,mean,scale):
    missing=np.isnan(x).astype(float)
    filled=np.where(np.isnan(x),med,x)
    return np.column_stack([np.ones(len(x)),(filled-mean)/scale,missing])

def fit(rows,personal,alpha):
    names=BASE+PERSONAL if personal else BASE
    x=matrix(rows,names)
    med=np.array([float(np.median(c[np.isfinite(c)])) if np.isfinite(c).any() else 0.0 for c in x.T])
    filled=np.where(np.isnan(x),med,x); mean=filled.mean(axis=0); scale=filled.std(axis=0); scale[scale<1e-8]=1
    z=transform(x,med,mean,scale)
    y=np.array([r['target'] for r in rows])
    if personal: y=y-np.array([r['features']['mean_fatigue'] for r in rows])
    penalty=np.eye(z.shape[1])*alpha; penalty[0,0]=0
    coef=np.linalg.solve(z.T@z+penalty,z.T@y)
    return {'names':names,'median':med.tolist(),'mean':mean.tolist(),'scale':scale.tolist(),
            'coef':coef.tolist(),'personal':personal,'alpha':alpha}

def predict(model,rows):
    if 'profiles' in model:
        base=predict(model['shared'],rows)
        return np.clip(base+np.array([response_details(model,r)['correction'] for r in rows]),1,5)
    x=matrix(rows,model['names'])
    z=transform(x,np.array(model['median']),np.array(model['mean']),np.array(model['scale']))
    y=z@np.array(model['coef'])
    if model['personal']: y+=np.array([r['features']['mean_fatigue'] for r in rows])
    return np.clip(y,1,5)

def score(rows,preds):
    y=np.array([r['target'] for r in rows]); err=np.array(preds)-y
    per={s:float(np.mean([abs(float(p)-r['target']) for r,p in zip(rows,preds) if r['subject']==s])) for s in sorted({r['subject'] for r in rows})}
    return {'mae':float(np.mean(abs(err))),'rmse':float(np.sqrt(np.mean(err**2))),
            'macro_subject_mae':float(np.mean(list(per.values()))),'per_subject_mae':per,'n':len(rows),'subjects':len(per)}

def train():
    OUT.mkdir(exist_ok=True)
    if not (DATA/'provenance.json').exists(): raise ValueError('Original data download is incomplete: provenance.json missing')
    subjects=load_all(); rows,audit=records(subjects)
    tr=[r for r in rows if r['date']<=TRAIN_END]
    va=[r for r in rows if TRAIN_END<r['date']<=VAL_END]
    te=[r for r in rows if r['date']>VAL_END]
    if min(map(len,(tr,va,te)))<20: raise ValueError('Insufficient chronological split data')
    models={}; validation={}
    for name,personal in [('population',False),('personalized',True)]:
        trials=[]
        for alpha in [0.1,1.0,10.0,100.0]:
            m=fit(tr,personal,alpha); metric=score(va,predict(m,va))['mae']; trials.append((metric,alpha))
        best=min(trials)[1]
        validation[name]={'alpha_trials':trials,'chosen_alpha':best}
        models[name]=fit(tr+va,personal,best)
    # Freeze candidates before reading the already-used exploratory test period.
    shared_validation=fit(tr,True,validation['personalized']['chosen_alpha'])
    trials=[]
    for alpha in [10.0,100.0,1000.0]:
        candidate=fit_response(shared_validation,tr,alpha)
        trials.append((score(va,predict(candidate,va))['mae'],alpha))
    best=min(trials)[1]
    validation['response']={'alpha_trials':trials,'chosen_alpha':best}
    models['response']=fit_response(models['personalized'],tr+va,best)
    for name in models: models[name]['trained_until']=VAL_END
    provenance=json.loads((DATA/'provenance.json').read_text())
    models['metadata']={'target':'PMSys fatigue response: 1=tired, 5=fresh; not fitness for duty',
       'target_timing':'next UTC calendar day','source':'original PMData ZIP','source_etag':provenance['etag'],
       'trained_until':VAL_END,'evaluation':'existing-subject chronological, rolling observed history',
       'availability_assumption':'daily summaries available at UTC day end; report effective timestamp used; submission timestamps unavailable'}
    (OUT/'models.json').write_text(json.dumps(models,indent=2),encoding='utf-8')
    predictions={'last_value':np.array([r['features']['last_fatigue'] for r in te]),
                 'personal_mean':np.array([r['features']['mean_fatigue'] for r in te])}
    predictions.update({name:predict(models[name],te) for name in ('population','personalized','response')})
    metrics={name:score(te,pred) for name,pred in predictions.items()}
    per=metrics['personalized']['per_subject_mae']; pop=metrics['population']['per_subject_mae']
    differences=np.array([per[s]-pop[s] for s in per])
    rng=np.random.default_rng(20260915)
    boot=np.array([rng.choice(differences,len(differences),replace=True).mean() for _ in range(2000)])
    report={'data_source':'real public PMData','train_end':TRAIN_END,'validation_end':VAL_END,
            'counts':{'train':len(tr),'validation':len(va),'test':len(te)},'audit':audit,'validation':validation,
            'test':metrics,'personal_minus_population_macro_mae':float(differences.mean()),
            'paired_subject_bootstrap_95_interval':np.quantile(boot,[.025,.975]).tolist(),
            'evaluation_status':'exploratory reuse of previously inspected v0.1 test period',
            'limitations':['Small observational cohort; not clinical validation','Daily reports are subjective, not recovery completion',
                          'Retrospective availability assumption; no upload timestamps','Not unseen-person generalization',
                          'No ECG/PCG raw-signal model; derived wearable features only']}
    (OUT/'evaluation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    with (OUT/'test_predictions.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=['subject','date','target']+list(predictions)); writer.writeheader()
        for i,r in enumerate(te): writer.writerow({**{k:r[k] for k in ['subject','date','target']},**{k:float(v[i]) for k,v in predictions.items()}})
    example={'subject':te[0]['subject'],'date':te[0]['date'],'features':te[0]['features']}
    (OUT/'example_input.json').write_text(json.dumps(example,indent=2),encoding='utf-8')
    (OUT/'data_audit.json').write_text(json.dumps({'subjects':audit,'feature_names':BASE+PERSONAL,'n_rows':len(rows)},indent=2))
    print(json.dumps({'counts':report['counts'],'test':{k:{m:v[m] for m in ['mae','macro_subject_mae','n','subjects']} for k,v in metrics.items()},'interval':report['paired_subject_bootstrap_95_interval']},indent=2))
    return report

def infer(record):
    models=json.loads((OUT/'models.json').read_text(encoding='utf-8'))
    if not isinstance(record,dict) or not isinstance(record.get('features'),dict): raise ValueError('features object required')
    f=record['features']
    if not isinstance(record.get('subject'),str) or not record['subject'].strip():
        raise ValueError('Nonempty subject ID required')
    try: prediction_date=dt.date.fromisoformat(record.get('date',''))
    except (TypeError,ValueError): raise ValueError('Prediction date must be YYYY-MM-DD')
    if prediction_date.isoformat()<=models['metadata']['trained_until']:
        raise ValueError('Prediction date must be after the training cutoff')
    for k in BASE+PERSONAL:
        if k not in f: raise ValueError('Missing field: '+k)
        if f[k] is not None and (isinstance(f[k],bool) or number(f[k]) is None): raise ValueError('Invalid number: '+k)
        f[k]=number(f[k])
    if f['mean_fatigue'] is None or not 1<=f['mean_fatigue']<=5: raise ValueError('Personal baseline must be 1..5')
    if f['n_prior_reports'] is None or f['n_prior_reports']<3: raise ValueError('At least 3 previous reports required')
    if f['last_fatigue'] is None or not 1<=f['last_fatigue']<=5: raise ValueError('Last response must be 1..5')
    if f['fatigue_age_days'] is None or not 1<=f['fatigue_age_days']<=7: raise ValueError('Recent personal history required (1..7 days)')
    if sum(f[k] is not None for k in ('resting_hr','sleep_score','light_minutes','moderate_minutes','vigorous_minutes'))<2: raise ValueError('Insufficient observed inputs')
    for k,lo,hi in [('resting_hr',20,250),('sleep_score',0,100),('sleep_hours',0,24),
                    ('light_minutes',0,1440),('moderate_minutes',0,1440),('vigorous_minutes',0,1440),
                    ('exercise_minutes',0,1440),('session_load',0,14400),('sd_fatigue',0,2),('n_prior_reports',3,28)]:
        if f[k] is not None and not lo<=f[k]<=hi: raise ValueError(f'{k} outside supported range {lo}..{hi}')
    values={name:float(predict(models[name],[record])[0]) for name in ['population','personalized','response']}
    return {'predictions':values,'scale':'1=very tired, 5=very fresh','target':'Next-day subjective fatigue response',
            'personal_response':response_details(models['response'],record),
            'model_trained_until':models['metadata']['trained_until'],'clinical_or_duty_decision':False,
            'missing_features':[k for k in BASE if f[k] is None]}

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('command',choices=['train','predict']); parser.add_argument('--input',type=Path)
    args=parser.parse_args()
    if args.command=='train': train()
    else:
        if not args.input: parser.error('--input is required')
        print(json.dumps(infer(json.loads(args.input.read_text(encoding='utf-8-sig'))),indent=2,ensure_ascii=False))

if __name__=='__main__': main()
