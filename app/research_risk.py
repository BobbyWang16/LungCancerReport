"""Versioned JSON-only Cox inference. No training or external calls at prediction time."""
import math
from .features import LOOKUP, CATEGORIES, validate_value
from .settings import AppError

FORMAT='report_recurrence_cox_bundle_v1'
AUTO_PRIORITY=('PATH_CE','PATH_NCE','PATH')

def score_automatic(features,scope_confirmed,m,modalities=None):
    """Route by available inputs, never by predicted risk or test-set AUC.

    CE-before-NCE is a fixed convention, not a superiority claim.
    Failed candidates are recorded so any fallback remains visible.
    """
    present=set(modalities) if modalities is not None else {f['key'].split('.')[0] for f in features}
    candidates=[k for k in AUTO_PRIORITY if k in m['models'] and
                (m['models'][k]['modality'] is None or m['models'][k]['modality'] in present)]
    selection=dict(mode='automatic',policy='available_inputs_ce_nce_path_v1',
                   candidates=candidates,skipped=[],selected_model=None,
                   ignored_modalities=['PET_CT'] if 'PET_CT' in present else [])
    if 'PATH' not in present:
        result=blocked('请添加病理报告后再评估。')
    elif not scope_confirmed:
        result=blocked('请先核对并确认患者符合模型适用人群。')
    else:
        result=blocked('没有可用的研究模型。')
        for key in candidates:
            result=score_bundle(features,True,m,key)
            if result['status']=='available':
                selection['selected_model']=key
                break
            selection['skipped'].append(dict(model=key,reason=result['reason'],
                                            missing_features=result.get('missing_features',[])))
    result['model_selection']=selection
    return result
def finite(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
def blocked(reason,missing=None):
    return dict(status='unavailable',reason=reason,is_demo=False,recurrence_probability=None,horizon_months=None,top_sites=[],missing_features=missing or [])

def validate_bundle(m):
    if m.get('format')!=FORMAT or m.get('is_demo') is not False:raise ValueError('错误的研究模型格式')
    for key in ('model_id','version','scope','time_origin','training_data_reference','validation_summary'):
        if not isinstance(m.get(key),str) or not m[key]:raise ValueError('缺少模型元数据')
    if m.get('validation_status')!='research' or m.get('clinical_deployment_allowed') is not False:raise ValueError('本格式仅支持研究用途')
    if not finite(m.get('horizon_months')) or not 1<=m['horizon_months']<=120:raise ValueError('无效时间窗')
    if not finite(m.get('minimum_observed_fraction')) or not .5<=m['minimum_observed_fraction']<=1:raise ValueError('无效覆盖阈值')
    models=m.get('models')
    if not isinstance(models,dict) or not models or not set(models)<= {'PATH','PATH_CE','PATH_NCE','PATH_PET_CT'}:raise ValueError('无效模型集合')
    if m.get('default_model') not in models:raise ValueError('默认模型不存在')
    if not isinstance(m.get('required_observed'),list) or not m['required_observed'] or any(k not in LOOKUP for k in m['required_observed']):raise ValueError('无效必需特征')
    for name,model in models.items():
        if model.get('modality')!={'PATH':None,'PATH_CE':'CE','PATH_NCE':'NCE','PATH_PET_CT':'PET_CT'}[name]:raise ValueError('模态不匹配')
        ins,coef=model.get('inputs'),model.get('coefficients')
        if not isinstance(ins,list) or not 1<=len(ins)<=200 or not isinstance(coef,list) or len(coef)!=len(ins) or not all(finite(v) for v in coef):raise ValueError('无效设计矩阵或系数')
        if not finite(model.get('baseline_cumulative_hazard')) or model['baseline_cumulative_hazard']<0:raise ValueError('基线风险无效')
        if not isinstance(model.get('research_enabled'),bool):raise ValueError('须声明研究启用状态')
        for s in ins:
            if s.get('key') not in LOOKUP or s.get('transform') not in ('identity','equals','missing'):raise ValueError('未知模型输入')
            if s['key'].split('.')[0] not in ('PATH',model['modality']):raise ValueError('模型跨模态混用')
            if not finite(s.get('center')) or not finite(s.get('scale')) or s['scale']<=0:raise ValueError('标准化参数无效')
            if s['transform']!='missing' and not finite(s.get('impute')):raise ValueError('填补参数无效')
            if s['transform']=='identity' and (not finite(s.get('lower')) or not finite(s.get('upper')) or s['lower']>=s['upper']):raise ValueError('截尾参数无效')
            if s['transform']=='equals':
                cats=s.get('allowed_categories')
                if not finite(s.get('category')) or not isinstance(cats,list) or not cats or not all(finite(c) for c in cats) or s['category'] not in cats or s['impute'] not in cats:raise ValueError('分类定义无效')
    # The saved site heads failed validation; do not enable them through this adapter.
    if m.get('site_model',{}).get('enabled') is not False:raise ValueError('未验证部位模型必须禁用')
    return m

def public_bundle(m):
    base=m['models'][m['default_model']]
    return dict(ready=True,format=FORMAT,**{k:m[k] for k in ('model_id','version','scope','time_origin','horizon_months','validation_status','validation_summary')},scope_en=m.get('scope_en'),time_origin_en=m.get('time_origin_en'),validation_summary_en=m.get('validation_summary_en'),required_features=m['required_observed'],sha256=m.get('_sha256'),default_model=m['default_model'],model_options=[dict(key=k,enabled=v['research_enabled'],n=v['validation']['n'],auc=v['validation']['auc_ipcw']) for k,v in m['models'].items()],selection_mode='automatic',selection_priority=list(AUTO_PRIORITY),sites_enabled=False,site_reason='validation_insufficient',feature_importance=m.get('importance',{}))

def score_bundle(features,scope_confirmed,m,model_key=None):
    if not scope_confirmed:return blocked('请先核对并确认患者符合模型适用人群。')
    key=model_key or m['default_model'];model=m['models'].get(key)
    if not model or not model['research_enabled']:return blocked('该研究模型尚未达到启用条件。')
    fmap={f['key']:f for f in features};required=list(dict.fromkeys(s['key'] for s in model['inputs']))
    if model['modality'] and not any(k.startswith(model['modality']+'.') for k in fmap):return blocked('该模型需要对应模态报告。')
    # User scope confirmation cannot override an explicit contrary finding.
    checks={'PATH.histology_code':lambda v:CATEGORIES['histology_code'].get(v) in ('LUAD','LUSC'),
            'PATH.invasion_status':lambda v:v==2,'PATH.residual_R_code':lambda v:v==0,
            'PATH.yp_prefix_present':lambda v:v==0,
            'PATH.pM_code':lambda v:'M1' not in CATEGORIES['pM_code'].get(v,'').upper(),
            'PATH.pStage_code':lambda v:not CATEGORIES['pStage_code'].get(v,'').upper().startswith('IV')}
    full=m.get('population_policy')=='all_events_or_dfs_gt_12'
    if full:checks={'PATH.histology_code':lambda v:v in CATEGORIES['histology_code']}
    for field,check in checks.items():
        f=fmap.get(field);v=f.get('value') if f else None
        if finite(v) and v>=0 and not check(v):return blocked('已记录的病理结果不符合研究模型适用人群。',[field])
    values={};imputed=[];missing=[]
    for field in m['required_observed']:
        f=fmap.get(field)
        if not f or not f.get('reviewed') or not finite(f.get('value')) or f['value']<0 or f.get('status') in ('conflict','uncertain'):
            missing.append(field)
    for field in required:
        f=fmap.get(field)
        if not f or not f.get('reviewed'):missing.append(field);continue
        v=f.get('value')
        if full and field in m.get('adeno_only_keys',[]) and CATEGORIES['histology_code'].get(fmap.get('PATH.histology_code',{}).get('value'))!='LUAD':v=None
        if finite(v) and int(v)==v:v=m.get('category_aliases',{}).get(field,{}).get(str(int(v)),v)
        signed=field.endswith('_hu')
        if f.get('status') in ('conflict','uncertain') or not signed and finite(v) and v in ((-8,-6,-5) if full else (-8,-7,-6,-5)):missing.append(field);continue
        if v is None or not signed and v in ((-9,-7) if full else (-9,)):
            if field in m['required_observed']:missing.append(field)
            values[field]=None;imputed.append(field);continue
        try:validate_value(LOOKUP[field],v)
        except (AppError,TypeError,ValueError):missing.append(field);continue
        if not finite(v) or not signed and v<0:missing.append(field);continue
        for s in model['inputs']:
            if s['key']==field and s['transform']=='equals' and v not in s['allowed_categories']:missing.append(field)
        values[field]=v
    if missing:return blocked('模型所需特征缺失、不确定或尚未核对；请补充关键特征。',list(dict.fromkeys(missing)))
    observed=sum(v is not None for v in values.values())
    if observed/len(required)<m['minimum_observed_fraction']:return blocked('已记录特征不足，暂不能评估；请补充报告。',imputed)
    image_required=sum(k.startswith(model['modality']+'.') for k in required) if model['modality'] else 0
    if model['modality'] and sum(v is not None and k.startswith(model['modality']+'.') for k,v in values.items())<min(2,image_required):
        return blocked('本模态可用特征不足，请核对报告。')
    vector=[]
    for s in model['inputs']:
        v=values[s['key']]
        if s['transform']=='missing':z=float(v is None)
        elif s['transform']=='identity':z=max(s['lower'],min(s['upper'],s['impute'] if v is None else v))
        else:z=float((s['impute'] if v is None else v)==s['category'])
        vector.append((z-s['center'])/s['scale'])
    lp=sum(a*b for a,b in zip(vector,model['coefficients']))
    if not math.isfinite(lp):return blocked('模型计算超出数值范围，请检查参数。')
    probability=-math.expm1(-model['baseline_cumulative_hazard']*math.exp(max(-35,min(35,lp))))
    return dict(status='available',reason='',is_demo=False,recurrence_probability=probability,death_without_recurrence_probability=None,no_event_probability=None,
                horizon_months=m['horizon_months'],time_origin=m['time_origin'],time_origin_en=m.get('time_origin_en'),risk_level=None,
                top_sites=[],site_status='not_validated',site_reason='部位模型验证不足，未输出排名或概率。',
                model_id=m['model_id'],selected_model=key,model_version=m['version'],model_sha256=m.get('_sha256'),validation_status='research',
                scope=m['scope'],scope_en=m.get('scope_en'),missing_features=[],imputed_features=imputed,observed_feature_count=observed,required_feature_count=len(required),
                prediction_type='research_recorded_recurrence_net_risk',validation_summary=m['validation_summary'],
                interpretation='术后30天起算的24个月记录复发研究估计；不是已验证竞争风险累计发生率。填补仅使用冻结训练参数；部位模型因验证不足禁用。')
