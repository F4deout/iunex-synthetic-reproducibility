"""Dated 5-km performance + matched running sessions -> reported exertion (0..10).

Session-end retrospective estimation, NOT time-to-exhaustion or clinical inference.
No RPE-derived input: RPE is exclusively the training target.
"""
import argparse,collections,csv,datetime as dt,json,math,zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
import model

OUT=model.ROOT/'artifacts'/'capacity_v03'
RAW=['duration_minutes','speed_kmh','average_hr','hr_above_rest','elevation_per_km']
RELATIVE=['reference_speed_kmh','speed_fraction_5k','duration_fraction_5k']
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

def profiles():
    """Read only explicit Excel dates; no inferred dates or max-HR timestamps."""
    result={}
    with zipfile.ZipFile(model.DATA/'participant-overview.xlsx') as z:
        strings=[''.join(t.itertext()) for t in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si',NS)]
        for row in ET.fromstring(z.read('xl/worksheets/sheet1.xml')).findall('.//s:row',NS):
            cells={}
            for c in row:
                value=c.find('s:v',NS)
                if value is not None:
                    cells[''.join(k for k in c.attrib['r'] if k.isalpha())]=strings[int(value.text)] if c.attrib.get('t')=='s' else value.text
            person=cells.get('A','')
            if not person.startswith('p') or len(person)!=3:continue
            date=model.number(cells.get('G')); minutes=model.number(cells.get('H')); seconds=model.number(cells.get('I'))
            valid=date is not None and minutes is not None and seconds is not None and 0<=seconds<60 and minutes>0
            result[person]={'subject':person,'reference_date':(dt.date(1899,12,30)+dt.timedelta(days=date)).isoformat() if valid else None,
                            'reference_5k_minutes':minutes+seconds/60 if valid else None,
                            'raw_date':cells.get('G'),'source':'participant-overview.xlsx',
                            'status':'dated_reference' if valid else 'unusable_date_or_result'}
    return result

def finite(value,name,lo,hi,optional=False):
    if value is None and optional:return None
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not lo<=value<=hi:
        raise ValueError(f'{name}: expected finite number in {lo}..{hi}')
    return float(value)

def make_features(record):
    if not isinstance(record,dict):raise ValueError('JSON object required')
    p=record.get('profile');s=record.get('session')
    if not isinstance(p,dict) or not isinstance(s,dict):raise ValueError('profile and session required')
    subject=record.get('subject')
    if not isinstance(subject,str) or not subject.strip():raise ValueError('subject required')
    if p.get('subject')!=subject or s.get('subject')!=subject:raise ValueError('Profile/session subject mismatch')
    try:
        reference_day=dt.date.fromisoformat(p['reference_date']);day=dt.date.fromisoformat(s['date'])
    except (KeyError,TypeError,ValueError):raise ValueError('Exact YYYY-MM-DD reference and session dates required')
    if reference_day>=day:raise ValueError('Reference test must precede the exercise day')
    if s.get('activity')!='running':raise ValueError('Only running is supported by this model')
    duration=finite(s.get('duration_minutes'),'duration_minutes',1,600)
    distance=finite(s.get('distance_km'),'distance_km',.05,100)
    reference=finite(p.get('reference_5k_minutes'),'reference_5k_minutes',10,120)
    hr=finite(s.get('average_hr'),'average_hr',30,240,True)
    rest=finite(s.get('resting_hr'),'resting_hr',20,150,True)
    elevation=finite(s.get('elevation_gain_m'),'elevation_gain_m',0,5000,True)
    speed=distance/duration*60
    if not 1<=speed<=35:raise ValueError('Running speed outside supported 1..35 km/h')
    ref_speed=300/reference
    return {'duration_minutes':duration,'speed_kmh':speed,'average_hr':hr,
            'hr_above_rest':hr-rest if hr is not None and rest is not None else None,
            'elevation_per_km':elevation/distance if elevation is not None else None,
            'reference_speed_kmh':ref_speed,'speed_fraction_5k':speed/ref_speed,
            'duration_fraction_5k':duration/reference}

def dataset():
    ps=profiles();rows=[];counts=collections.Counter();audit=[]
    for subject in model.load_all():
        person=subject['id'];profile=ps.get(person)
        if not profile or profile['status']!='dated_reference':
            counts['excluded_profile']+=1;continue
        exercise=json.loads((model.DATA/person/'fitbit'/'exercise.json').read_text())
        runs=[r for r in exercise if r.get('activityName')=='Run' and r.get('distanceUnit')=='Kilometer' and model.number(r.get('distance')) is not None and r['distance']>0]
        candidates=[]
        for report in model.read_csv(model.DATA/person/'pmsys'/'srpe.csv'):
            if 'running' not in report['activity_names']:continue
            counts['running_reports']+=1
            end=model.stamp(report['end_date_time']);minutes=model.number(report['duration_min']);target=model.number(report['perceived_exertion'])
            if minutes is None or minutes<=0 or target is None or not 0<=target<=10:continue
            matches=[]
            for run in runs:
                start=model.stamp(run['startTime']);duration=run['duration']/60000
                finish=start+dt.timedelta(minutes=duration)
                if abs((finish-end).total_seconds())<=900 and abs(duration-minutes)<=max(5,.2*minutes):matches.append((run,start,finish))
            if len(matches)!=1:
                counts['no_unique_time_match']+=1;continue
            candidates.append((report,end,target,*matches[0]))
        uses=collections.Counter(c[3]['logId'] for c in candidates)
        for report,end,target,run,start,finish in candidates:
            if uses[run['logId']]!=1:
                counts['duplicate_session_match']+=1;continue
            # Do not split a single person's multiple reports of one run across folds.
            day=start.date()
            if profile['reference_date']>=day.isoformat():counts['reference_not_yet_available']+=1;continue
            duration=run['duration']/60000
            rest=subject['daily'].get(day-dt.timedelta(days=1),{}).get('resting_hr')
            record={'subject':person,'profile':profile,'session':{'subject':person,'date':day.isoformat(),
                    'activity':'running','duration_minutes':duration,'distance_km':run['distance'],
                    'average_hr':model.number(run.get('averageHeartRate')),'resting_hr':rest,
                    'elevation_gain_m':model.number(run.get('elevationGain'))}}
            try:f=make_features(record)
            except ValueError:counts['invalid_features']+=1;continue
            row={'subject':person,'date':max(end,finish).date().isoformat(),'features':f,'target':target,'input':record}
            rows.append(row)
            audit.append({'subject':person,'log_id':run['logId'],'exercise_start':start.isoformat(),
                          'exercise_end':finish.isoformat(),'report_end':end.isoformat(),
                          'end_difference_seconds':(end-finish).total_seconds(),'reference_date':profile['reference_date']})
    rows.sort(key=lambda r:(r['date'],r['subject']))
    return rows,{'counts':dict(counts),'profiles':ps,'matched_sessions':audit}

def fit(rows,names,alpha):
    x=model.matrix(rows,names)
    med=np.array([np.median(c[np.isfinite(c)]) if np.isfinite(c).any() else 0 for c in x.T])
    fill=np.where(np.isnan(x),med,x);mean=fill.mean(0);scale=fill.std(0);scale[scale<1e-8]=1
    z=model.transform(x,med,mean,scale);penalty=np.eye(z.shape[1])*alpha;penalty[0,0]=0
    coef=np.linalg.solve(z.T@z+penalty,z.T@np.array([r['target'] for r in rows]))
    return dict(names=names,median=med.tolist(),mean=mean.tolist(),scale=scale.tolist(),coef=coef.tolist(),alpha=alpha)

def predict(m,rows):
    z=model.transform(model.matrix(rows,m['names']),np.array(m['median']),np.array(m['mean']),np.array(m['scale']))
    return np.clip(z@np.array(m['coef']),0,10)

def train():
    rows,audit=dataset();days=sorted({r['date'] for r in rows})
    if len(days)<15:raise ValueError('Too few distinct days for evaluation')
    # Split by dates, never by windows from the same workout. Fixed 60/20/20 rule.
    train_end=days[int(len(days)*.6)-1];val_end=days[int(len(days)*.8)-1]
    tr=[r for r in rows if r['date']<=train_end];va=[r for r in rows if train_end<r['date']<=val_end];te=[r for r in rows if r['date']>val_end]
    if min(len(tr),len(va),len(te))<5:raise ValueError('Insufficient chronological data')
    fitted={};validation={}
    for name,names in [('absolute',RAW),('relative',RAW+RELATIVE)]:
        trials=[(model.score(va,predict(fit(tr,names,a),va))['mae'],a) for a in [1.,10.,100.]]
        best=min(trials)[1];validation[name]={'trials':trials,'chosen_alpha':best};fitted[name]=fit(tr+va,names,best)
    metrics={k:model.score(te,predict(m,te)) for k,m in fitted.items()}
    global_mean=float(np.mean([r['target'] for r in tr+va]))
    personal={s:float(np.mean([r['target'] for r in tr+va if r['subject']==s])) for s in {r['subject'] for r in tr+va}}
    metrics['training_mean']=model.score(te,[global_mean]*len(te))
    metrics['personal_training_mean']=model.score(te,[personal.get(r['subject'],global_mean) for r in te])
    fitted['metadata']={'target':'session self-reported RPE 0..10; NOT breathlessness or time to exhaustion',
                       'trained_until':val_end,'reference':'dated prior 5-km performance, not proven maximal capacity',
                       'feature_ranges':{k:[float(min(r['features'][k] for r in tr+va if r['features'][k] is not None)),
                                            float(max(r['features'][k] for r in tr+va if r['features'][k] is not None))] for k in RAW+RELATIVE if any(r['features'][k] is not None for r in tr+va)}}
    report={'counts':{'train':len(tr),'validation':len(va),'test':len(te),'participants':len({r['subject'] for r in rows})},
            'train_end':train_end,'validation_end':val_end,'validation':validation,'test':metrics,
            'status':'small exploratory observational evaluation; not military or clinical validation',
            'target':'session RPE 0..10; incomparable with earlier next-day fatigue MAE'}
    OUT.mkdir(exist_ok=True)
    for file,data in [('models.json',fitted),('evaluation.json',report),('data_audit.json',audit),('example_input.json',te[0]['input'])]:
        (OUT/file).write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
    with (OUT/'test_predictions.csv').open('w',newline='',encoding='utf-8-sig') as out:
        w=csv.DictWriter(out,fieldnames=['subject','date','target','absolute','relative']);w.writeheader()
        for r,a,b in zip(te,predict(fitted['absolute'],te),predict(fitted['relative'],te)):
            w.writerow({'subject':r['subject'],'date':r['date'],'target':r['target'],'absolute':float(a),'relative':float(b)})
    (OUT/'test_records.json').write_text(json.dumps(te,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(report,indent=2));return report

def infer(record):
    f=make_features(record);m=json.loads((OUT/'models.json').read_text(encoding='utf-8'))
    if record['session']['date']<=m['metadata']['trained_until']:raise ValueError('Session date must be after model training cutoff')
    warnings=[]
    for k,(lo,hi) in m['metadata']['feature_ranges'].items():
        if f[k] is not None and not lo<=f[k]<=hi:warnings.append('Outside training range: '+k)
    age=(dt.date.fromisoformat(record['session']['date'])-dt.date.fromisoformat(record['profile']['reference_date'])).days
    if age>90:warnings.append('Reference performance is older than 90 days; refresh recommended')
    return {'predictions':{k:float(predict(m[k],[{'features':f}])[0]) for k in ['absolute','relative']},
            'features':f,'warnings':warnings,'reference_age_days':age,'missing_features':[k for k in RAW if f[k] is None],
            'target':m['metadata']['target'],'model_trained_until':m['metadata']['trained_until'],
            'interpretation':'Speed relative to prior 5-km performance; ratios are not percent exhaustion or safe duration',
            'clinical_or_duty_decision':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['train','predict']);p.add_argument('--input',type=Path);args=p.parse_args()
    if args.command=='train':train()
    else:
        if not args.input:p.error('--input required')
        print(json.dumps(infer(json.loads(args.input.read_text(encoding='utf-8-sig'))),ensure_ascii=False,indent=2))
