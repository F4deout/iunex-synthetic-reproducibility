"""Inference helper for the exported synthetic PRETASK research bundle."""
from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
BUNDLE=ROOT/"artifacts"/"pretask_model_phase1"/"research_model_bundle_seed110.json"


def _predict(model, features):
    x=np.asarray([np.nan if features.get(k) is None else float(features[k]) for k in model["features"]],float)
    med=np.asarray(model["impute_median"]); mean=np.asarray(model["scale_mean"]); sd=np.asarray(model["scale_sd"])
    z=(np.where(np.isnan(x),med,x)-mean)/sd
    value=float(model["intercept"]+z@np.asarray(model["coefficients"]))
    return value


def _prepare(features):
    values=dict(features)
    task=values.get("task_type")
    for name in ("AEROBIC","LOADED_MOVEMENT","BODYWEIGHT_CIRCUIT"):
        values.setdefault("task_"+name,float(task==name))
    return values


def _safety_status(features, bundle):
    gate=bundle["safety_gate_research_only"]
    qualities=[features.get(k) for k in ("quality_hr","quality_temperature","quality_spo2")]
    if any(q is not None and not 0<=float(q)<=1 for q in qualities): return "ABSTAIN_INVALID_INPUT"
    hr,temp,spo2=features.get("t0_hr"),features.get("t0_temperature"),features.get("t0_spo2")
    if hr is None and temp is None and spo2 is None: return "ABSTAIN_MISSING"
    if hr is not None and (hr<gate["resting_hr_low_bpm"] or hr>gate["resting_hr_high_bpm"]): return "SAFETY_HOLD"
    if temp is not None and temp>=gate["temperature_high_c"]: return "SAFETY_HOLD"
    if spo2 is not None and spo2<gate["spo2_low_pct"]: return "SAFETY_HOLD"
    return "MODEL_ALLOWED"


def _ood_features(features,bundle):
    # Only current/planned context is used for abstention; sparse history is imputed.
    check=("t0_hr","t0_temperature","t0_spo2","planned_demand","planned_duration","observed_anchor","gap_days")
    out=[]
    for key in check:
        value=features.get(key); bound=bundle.get("train_feature_bounds",{}).get(key)
        if value is not None and bound and not (bound["minimum"]<=float(value)<=bound["maximum"]): out.append(key)
    return out


def predict(features, bundle_path=BUNDLE):
    """Return separated research estimates after safety/OOD abstention."""
    bundle=json.loads(Path(bundle_path).read_text(encoding="utf-8"))
    values=_prepare(features); safety=_safety_status(values,bundle)
    if safety!="MODEL_ALLOWED": return {"status":safety,"subjective_state":None,"task_outcome":None,"warning":bundle["warning"]}
    ood=_ood_features(values,bundle)
    if ood: return {"status":"ABSTAIN_OUT_OF_DISTRIBUTION","out_of_range_features":ood,"subjective_state":None,"task_outcome":None,"warning":bundle["warning"]}
    count=int(values.get("history_count",max([values.get(k,0) or 0 for k in values if k.startswith("hist_") and k.endswith("_n")],default=0)))
    level=max(k for k in bundle["history_levels"] if k<=count) if count>=0 else 0; model_set=bundle["models_by_history"][str(level)]
    raw={name:_predict(model,values) for name,model in model_set["continuous_models"].items()}; logit=_predict(model_set["completion_model"],values)
    return {"status":"MODEL_OUTPUT","history_count":count,"trained_history_length":level,"subjective_state":{"pre_fatigue":raw["pre_fatigue"],"pre_condition":raw["pre_condition"]},"task_outcome":{"completion_probability":1/(1+math.exp(-max(-30,min(30,logit)))),"stop_time_if_not_completed":raw["stop_time"],"post_burden":raw["post_burden"],"recovery_delay":raw["recovery_delay"]},"warning":bundle["warning"]}
