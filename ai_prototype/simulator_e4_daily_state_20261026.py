"""Separate, locked E4 daily-state extension. Original simulator stays untouched."""
from pathlib import Path
import hashlib,json,math
from collections import defaultdict
import numpy as np
import build_v21_deployable_controlled as legacy
import simulator_v21_running as core

ROOT=Path(__file__).resolve().parent
PARAM=ROOT/'E4_DAILY_STATE_PARAMETERS_20261026.json'
DESIGN_LOCK=ROOT/'E4_DAILY_STATE_DESIGN_LOCK_20261026.json'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def verify():
    for entry in json.loads(DESIGN_LOCK.read_text(encoding='utf-8-sig')):
        assert sha(ROOT/entry['path'])==entry['sha256'],entry['path']
    legacy.check_locks()

def rng(seed,subject,session,process):
    token=f'E4-day-20261026|{seed}|{subject}|{session}|{process}'
    return np.random.default_rng(int.from_bytes(hashlib.sha256(token.encode()).digest()[:16],'big'))

def cases():
    p=json.loads(PARAM.read_text())
    base={k:v['BASE'] for k,v in p['families'].items()}
    return {'BASE':base,**{f'{family}_{level}':dict(base,**{family:values[level]}) for family,values in p['families'].items() for level in ('LOW','HIGH')}}

def bounded_normal(r,mean,sd,low,high):
    count=0
    while True:
        value=float(r.normal(mean,sd))
        if low<value<high:return value,count
        count+=1

def sensor(r,true,channel,case,p):
    cfg=p['sensor']
    missing=bool(r.random()<cfg['missing_probability'])
    artifact=bool(r.random()<cfg['artifact_probability'])
    quality=float(np.clip(cfg['quality_center']-cfg['quality_artifact_penalty']*artifact+r.normal(0,cfg['quality_sd']),0,1))
    sd=cfg['measurement_sd'][channel]*case['measurement_multiplier']*(cfg['artifact_sd_multiplier'] if artifact else 1)
    endpoint=False
    if channel=='spo2':
        center=cfg['spo2_beta_reference_mean']
        concentration=center*(100-center)/(sd*sd)-1
        assert concentration>0 and 0<true<100
        fraction=true/100
        value=100*float(r.beta(fraction*concentration,(1-fraction)*concentration))
        if value<=0 or value>=100:
            endpoint=True
            value=float(np.nextafter(0.,100.) if value<=0 else np.nextafter(100.,0.))
    else:value=float(true+r.normal(0,sd))
    return None if missing else value,quality,dict(missing=missing,artifact=artifact,numeric_endpoint=endpoint,nominal_sd=sd)

def next_state(previous_z,gap,epsilon,tau,first=False):
    rho=0. if first else math.exp(-gap/tau)
    z=rho*previous_z+math.sqrt(1-rho*rho)*epsilon
    return z,math.tanh(z/2)

def day_core(profile,fraction,debt,gap,speed,planned,state,hidden,case):
    day=dict(profile)
    day['dprime']=profile['dprime']*math.exp(-case['reserve_state_amplitude']*state+case['hidden_reserve_amplitude']*hidden)
    result=core.core(day,fraction*day['dprime'],debt,gap,speed,planned)
    return result,day['dprime']

def generate(seed,base,case):
    """Reuse original stable subjects/split/schedule; regenerate day-varying sessions."""
    p=json.loads(PARAM.read_text());cfg=p['sensor'];old=core.scenario()
    profiles=base['profiles_audit_only']; grouped=defaultdict(list)
    for row in base['observed_events']:grouped[row['subject']].append(row)
    observed=[];audit=[];profile_audit=[]
    for sid,events in sorted(grouped.items()):
        profile=profiles[sid]
        prng=rng(seed,sid,'profile','extra-baselines')
        temp0=float(prng.normal(cfg['temperature_baseline_mean_c'],cfg['temperature_baseline_sd_c']))
        spo0,reject0=bounded_normal(prng,cfg['spo2_baseline_mean_pct'],cfg['spo2_baseline_sd_pp'],*cfg['spo2_baseline_bounds'])
        profile_audit.append(dict(subject=sid,temperature_baseline=temp0,spo2_baseline=spo0,spo2_baseline_rejections=reject0))
        previous_z=0.;fraction=1.;debt=0.
        for i,event in enumerate(sorted(events,key=lambda e:e['event_order'])):
            session=event['session'];gap=event['gap_h']
            epsilon=float(rng(seed,sid,session,'daily-state').normal())
            z,state=next_state(previous_z,gap,epsilon,case['state_tau_hours'],first=i==0)
            hidden=math.tanh(float(rng(seed,sid,session,'hidden-performance').normal())/p['state_bounding_scale'])
            # Pre-exercise sensors are generated before the task outcome, from shared state only.
            true_hr=profile['baseline_hr']+case['sensor_coupling']*cfg['hr_state_gain_bpm']*state+float(rng(seed,sid,session,'hr-process').normal(0,cfg['hr_process_sd_bpm']))
            true_temp=temp0+case['sensor_coupling']*cfg['temperature_state_gain_c']*state+float(rng(seed,sid,session,'temp-process').normal(0,cfg['temperature_process_sd_c']))
            true_spo,rejections=bounded_normal(rng(seed,sid,session,'spo-process'),spo0-cfg['spo2_state_gain_pp']*math.tanh(case['sensor_coupling']*state),cfg['spo2_process_sd_pp'],0,100)
            values={};qualities={};sensor_audit={}
            for channel,true in [('hr',true_hr),('temperature',true_temp),('spo2',true_spo)]:
                values[channel],qualities[channel],sensor_audit[channel]=sensor(rng(seed,sid,session,channel+'-measurement'),true,channel,case,p)
            state_result,d_day=day_core(profile,fraction,debt,gap,event['commanded_speed_kmh'],event['planned_minutes'],state,hidden,case)
            post_hr=float(state_result['true_hr_mean']+rng(seed,sid,session,'post-hr-physiology').normal(0,old['physiology_sd'])+rng(seed,sid,session,'post-hr-measurement').normal(0,old['measurement_sd']))
            state_result=dict(state_result,observed_hr=post_hr,gap_h=gap,speed_kmh=event['commanded_speed_kmh'],planned_minutes=event['planned_minutes'])
            row=legacy.observed_log(state_result,sid,event['fold'],event['event_id'],event['event_order'],event['event_type'],event['u_anchor'],event['v5_kmh'])
            clock_bound=False
            if not row['completed']:
                raw_seconds=round(state_result['actual_minutes']*60+rng(seed,sid,session,'clock').uniform(-p['clock']['uniform_error_halfwidth_seconds'],p['clock']['uniform_error_halfwidth_seconds']))
                upper=round(event['planned_minutes']*60)-1
                seconds=max(1,min(raw_seconds,upper));clock_bound=seconds!=raw_seconds
                row['actual_minutes']=seconds/60;row['observed_stop_minutes']=seconds/60
            # Legacy 'censored' means stopped; explicit survival flags avoid reinterpreting it.
            row['event_observed']=not row['completed'];row['right_censored']=row['completed']
            for channel in values:
                row['pre_'+channel]=values[channel];row['quality_'+channel]=qualities[channel]
            observed.append(row)
            audit.append(dict(subject=sid,session=session,event_id=event['event_id'],fold=event['fold'],order=event['event_order'],
                              z=z,state=state,hidden=hidden,d_day=d_day,reserve_fraction_before=fraction,
                              true_pre_hr=true_hr,true_pre_temperature=true_temp,true_pre_spo2=true_spo,
                              true_actual_minutes=state_result['actual_minutes'],clock_boundary=clock_bound,
                              true_spo2_rejections=rejections,sensors=sensor_audit))
            fraction=state_result['q_end']/d_day;debt=state_result['debt_after'];previous_z=z
            assert 0<=fraction<=1+1e-12
    return dict(observed_events=observed,audit_only=audit,profiles_audit_only=profile_audit,subject_split=base['subject_split'])

CURRENT_FEATURES=tuple(x for c in ('hr','temperature','spo2') for x in ('pre_'+c,'quality_'+c))

def features(data,prefix=''):
    grouped=defaultdict(list)
    for r in data['observed_events']:grouped[r['subject']].append(r)
    audit={r['session']:r for r in data['audit_only']}
    rows=[];manifests=[]
    for sid,seq in sorted(grouped.items()):
        cal=sorted([r for r in seq if r['event_type']=='calibration'],key=lambda r:r['event_order'])
        assert len(cal)==20
        current=next(r for r in seq if r['event_id']=='E4')
        assert all(r['subject']==sid and r['event_order']<current['event_order'] for r in cal)
        old,meta=legacy.history_features(cal,20,current['v5_kmh'])
        old=dict(old,evaluation_order=current['event_order'])
        for c in ('hr','temperature','spo2'):
            v=[r['pre_'+c] for r in cal if r['pre_'+c] is not None]
            old.update({f'past_pre_{c}_mean':float(np.mean(v)) if v else None,
                        f'past_pre_{c}_sd':float(np.std(v)) if v else None,
                        f'past_pre_{c}_last':v[-1] if v else None,f'past_pre_{c}_n':len(v)})
        allowed={k:current[k] for k in CURRENT_FEATURES}
        whitelist=set(old)|set(CURRENT_FEATURES)|{'v5_kmh','evaluation_order'}
        variants={'anchor':{'v5_kmh':current['v5_kmh'],'evaluation_order':current['event_order']},
                  'history':old,'current':dict(v5_kmh=current['v5_kmh'],evaluation_order=current['event_order'],**allowed),
                  'full':dict(old,**allowed)}
        for f in variants.values():
            assert set(f)<=whitelist
            assert not any(k.startswith(('true_','latent_')) or k in ('state','hidden','d_day','observed_stop_minutes','actual_minutes','event_observed','right_censored','completed','censored') for k in f)
        variants['oracle']=dict(variants['full'],audit_state=audit[current['session']]['state'])
        for name in variants:
            rows.append(dict(subject=prefix+sid,session=prefix+current['session'],fold='test' if current['fold']=='id_test' else current['fold'],variant=name,features=variants[name],target=current['observed_stop_minutes'],completed=current['completed']))
        stopped=[r for r in cal if r['observed_stop_minutes'] is not None]
        task=[r for r in stopped if abs(r['u_anchor']-current['u_anchor'])<1e-9]
        exact=[r for r in task if abs(r['planned_minutes']-current['planned_minutes'])<1e-9 and abs(r['gap_h']-current['gap_h'])<1e-9]
        baseline={}
        for name,group in [('personal',stopped),('task',task),('exact_context',exact)]:
            values=[r['observed_stop_minutes'] for r in group]
            baseline[name+'_mean']=float(np.mean(values)) if values else None
            baseline[name+'_last']=values[-1] if values else None
        manifests.append(dict(subject=prefix+sid,session=prefix+current['session'],fold='test' if current['fold']=='id_test' else current['fold'],
                              history_sources=[prefix+r['session'] for r in cal],history_orders=[r['event_order'] for r in cal],current_order=current['event_order'],
                              exact_sources=[prefix+r['session'] for r in exact],baseline=baseline,target=current['observed_stop_minutes']))
    return rows,manifests

def unit_tests():
    case=cases()['BASE']
    p={'dprime':130.,'cs':3.,'tau_fast':4.,'tau_slow':24.,'baseline_hr':60.,'delta_hr':0.}
    better,d1=day_core(p,1,0,72,12.,12.,-.5,0,case)
    worse,d2=day_core(p,1,0,72,12.,12.,.5,0,case)
    assert d1>d2 and better['actual_minutes']>worse['actual_minutes']
    assert next_state(0,72,.7,24)==next_state(0,72,.7,24)
    z,s=next_state(.5,72,.7,24);assert -1<s<1
    cfg=json.loads(PARAM.read_text())
    rr=rng(1,'A','B','bias-test')
    measurements=[sensor(rr,97.5,'spo2',case,cfg)[0] for _ in range(10000)]
    usable=[x for x in measurements if x is not None]
    assert abs(float(np.mean(usable))-97.5)<.06
    assert all(0<x<100 for x in usable)
    print('daily-state generator unit tests PASS',flush=True)

if __name__=='__main__':verify();unit_tests()
