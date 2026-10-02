"""Frozen 1/3/5-year survival curves plus an independently validated site ranker."""
import math,struct
from .features import LOOKUP,validate_value,CATEGORIES
from .settings import AppError
from .research_risk import validate_bundle,score_bundle,blocked,finite

FORMAT='report_recurrence_multihorizon_v2'
FULL_FORMAT='report_recurrence_multihorizon_v3'
FORMATS=(FORMAT,FULL_FORMAT)
YEARS=(1,3,5)
PRIORITY=('PATH_CE','PATH_NCE','PATH_PET_CT','PATH')
LABELS={'lung':'肺','nodes':'淋巴结','pleura':'胸膜 / 胸腔','bone':'骨','brain':'脑 / 脑膜','liver':'肝','adrenal':'肾上腺','other':'其他部位'}

def legacy_view(m,year=1):
    return {**m,'format':'report_recurrence_cox_bundle_v1','horizon_months':year*12,
            'site_model':{'enabled':False},'models':{k:{**v,'baseline_cumulative_hazard':v['horizons'][str(year)]['baseline_cumulative_hazard']} for k,v in m['models'].items()}}

def validate_multihorizon(m):
    if m.get('feature_schema_version')=='CF_20260930' and m.get('histology_codebook')!={str(k):v for k,v in CATEGORIES['histology_code'].items()}:raise ValueError('病理分组字典与模型不匹配，请同步更新资源文件')
    full=m.get('format')==FULL_FORMAT
    origin=0 if full else 30
    if m.get('format') not in FORMATS or m.get('years_after_surgery')!=[1,3,5] or m.get('landmark_days')!=origin:raise ValueError('无效的多时间点模型定义')
    if full and (m.get('population_policy')!='all_events_or_dfs_gt_12' or m.get('required_observed')!=['PATH.histology_code']):raise ValueError('全病理队列策略不匹配')
    for model in m['models'].values():
        hs=model.get('horizons',{})
        if set(hs)!=set(map(str,YEARS)):raise ValueError('缺少1/3/5年风险参数')
        previous=-1
        for year in YEARS:
            h=hs[str(year)];b=h.get('baseline_cumulative_hazard')
            if not finite(b) or b<previous:raise ValueError('累计风险参数必须有限且不递减')
            if not isinstance(h.get('research_enabled'),bool) or h.get('years_after_surgery')!=year or h.get('days_from_landmark')!=year*365.25-origin:raise ValueError('时间点定义错误')
            previous=b
    validate_bundle(legacy_view(m))
    site=m.get('site_model',{})
    if site.get('format')!='conditional_recorded_site_ranker_v2' or not isinstance(site.get('enabled'),bool) or site.get('clinical_deployment_allowed') is not False:raise ValueError('无效部位模型')
    labels=site.get('labels',[]);inputs=site.get('inputs',[])
    if len(labels)<3 or len(labels)!=len(set(labels)) or set(labels)-set(LABELS):raise ValueError('无效部位类别')
    if any(not s['key'].startswith('PATH.') for s in inputs):raise ValueError('部位模型只接受病理输入')
    for key,aliases in site.get('category_aliases',{}).items():
        if key not in ('PATH.pT_code','PATH.pStage_code'):raise ValueError('不支持的类别别名字段')
        categories=CATEGORIES[key.split('.')[1]]
        for src,target in aliases.items():
            if int(src) not in categories or target not in categories:raise ValueError('类别映射与软件字典不一致')
            normalize=lambda label:label.replace('期','').strip().upper()
            if normalize(categories[int(src)])!=normalize(categories[target]):raise ValueError('类别别名含义不一致')
    # Reuse the strict design-matrix checks independently of the recurrence heads.
    validation=legacy_view(m);validation['models']={'PATH':dict(modality=None,research_enabled=False,inputs=inputs,coefficients=[0.]*len(inputs),baseline_cumulative_hazard=0.)};validation['default_model']='PATH'
    validate_bundle(validation)
    if not .5<=site.get('minimum_observed_fraction',0)<=1 or any(k not in LOOKUP for k in site.get('required_observed',[])):raise ValueError('无效部位缺失值策略')
    if site['enabled']:
        v=site.get('validation',{})
        if v.get('ranking_supported') is not True or v.get('recall_gain_ci95',[0])[0]<=0:raise ValueError('部位排序缺少验证增益')
    if site.get('reference_prevalence') is not None:
        p=site['reference_prevalence']
        if len(p)!=len(labels) or any(not finite(v) or not 0<=v<=1 for v in p):raise ValueError('无效队列部位参考')
    if site.get('algorithm')=='random_forest':
        trees=site.get('trees',[])
        if not 1<=len(trees)<=300:raise ValueError('无效树数量')
        for t in trees:
            n=len(t['left'])
            if not 1<=n<=1024 or any(len(t[k])!=n for k in ['right','feature','threshold','probabilities']):raise ValueError('树维度错误')
            for i in range(n):
                left,right=t['left'][i],t['right'][i];p=t['probabilities'][i]
                if len(p)!=len(labels) or any(not finite(v) or not 0<=v<=1 for v in p):raise ValueError('部位评分无效')
                if left==-1 and right==-1:continue
                if not (i<left<n and i<right<n and 0<=t['feature'][i]<len(inputs) and finite(t['threshold'][i])):raise ValueError('树链接或分裂参数无效')
    elif site.get('algorithm')=='logistic':
        heads=site.get('heads',[])
        if len(heads)!=len(labels) or any(not finite(h['intercept']) or len(h['coefficients'])!=len(inputs) or not all(finite(v) for v in h['coefficients']) for h in heads):raise ValueError('部位回归参数无效')
    else:raise ValueError('未知部位模型算法')
    return m

def public_multihorizon(m):
    return dict(feature_importance=m.get("importance",{}),ready=True,format=m['format'],**{k:m[k] for k in ['model_id','version','scope','scope_en','time_origin','time_origin_en','validation_status','validation_summary','validation_summary_en']},sha256=m.get('_sha256'),required_features=m['required_observed'],years_after_surgery=list(YEARS),selection_mode='automatic',selection_priority=list(PRIORITY),sites_enabled=m['site_model']['enabled'],site_mode='exploratory_ranking' if m['site_model']['enabled'] else 'cohort_reference' if m['site_model'].get('reference_prevalence') else 'not_validated',model_options=[dict(key=k,enabled=v['research_enabled'],years=[y for y,h in v['horizons'].items() if h['research_enabled']]) for k,v in m['models'].items()])

def site_vector(features,site):
    fmap={f['key']:f for f in features};values={};imputed=[]
    full=site.get('population_policy')=='all_events_or_dfs_gt_12'
    for key in site['required_observed']:
        f=fmap.get(key)
        if not f or not f.get('reviewed') or not finite(f.get('value')) or f['value']<0 or f.get('status') in ('conflict','uncertain'):return None,[]
    for key in dict.fromkeys(s['key'] for s in site['inputs']):
        f=fmap.get(key)
        if not f or not f.get('reviewed'):return None,[]
        v=f.get('value')
        if full and key in site.get('adeno_only_keys',[]) and CATEGORIES['histology_code'].get(fmap.get('PATH.histology_code',{}).get('value'))!='LUAD':v=None
        if finite(v) and int(v)==v:v=site.get('category_aliases',{}).get(key,{}).get(str(int(v)),v)
        if f.get('status') in ('conflict','uncertain') or finite(v) and v in ((-8,-6,-5) if full else (-8,-7,-6,-5)):return None,[]
        if v is None or v in ((-9,-7) if full else (-9,)):
            if key in site['required_observed']:return None,[]
            values[key]=None;imputed.append(key);continue
        try:validate_value(LOOKUP[key],v)
        except (AppError,ValueError,TypeError):return None,[]
        if not finite(v) or v<0:return None,[]
        if any(s['transform']=='equals' and v not in s['allowed_categories'] for s in site['inputs'] if s['key']==key):return None,[]
        values[key]=v
    if sum(v is not None for v in values.values())/len(values)<site['minimum_observed_fraction']:return None,[]
    vector=[]
    for s in site['inputs']:
        v=values[s['key']]
        if s['transform']=='missing':z=float(v is None)
        elif s['transform']=='identity':z=max(s['lower'],min(s['upper'],s['impute'] if v is None else v))
        else:z=float((s['impute'] if v is None else v)==s['category'])
        vector.append((z-s['center'])/s['scale'])
    return vector,imputed

def site_scores(vector,site):
    if site['algorithm']=='random_forest':
        # sklearn's forest predictor casts the design to float32 before traversal.
        x=[struct.unpack('f',struct.pack('f',v))[0] for v in vector];p=[0.]*len(site['labels'])
        for t in site['trees']:
            i=0
            while t['left'][i]!=-1:i=t['left'][i] if x[t['feature'][i]]<=t['threshold'][i] else t['right'][i]
            for j,v in enumerate(t['probabilities'][i]):p[j]+=v/len(site['trees'])
        return p
    p=[]
    for h in site['heads']:
        z=h['intercept']+sum(v*b for v,b in zip(vector,h['coefficients']));p.append(1/(1+math.exp(-max(-700,min(700,z)))))
    return p

def ranked_sites(features,site):
    if not site['enabled']:
        p=site.get('reference_prevalence')
        if p is None:return dict(top_sites=[],site_status='not_validated',site_imputed_features=[])
        order=sorted(range(len(p)),key=lambda j:(-p[j],j))[:3]
        return dict(top_sites=[dict(site=site['labels'][j],label=LABELS[site['labels'][j]],rank=i+1) for i,j in enumerate(order)],site_status='cohort_reference',site_reason='个体部位排序增益未获验证支持，显示队列常见部位参考。',site_imputed_features=[],site_interpretation='队列中已记录复发患者的常见部位参考；不代表该患者的个体预测或绝对概率。')
    vector,imputed=site_vector(features,site)
    if vector is None:return dict(top_sites=[],site_status='insufficient_features',site_imputed_features=[])
    p=site_scores(vector,site);order=sorted(range(len(p)),key=lambda j:(-p[j],j))[:3]
    return dict(top_sites=[dict(site=site['labels'][j],label=LABELS[site['labels'][j]],rank=i+1,ranking_score=p[j]) for i,j in enumerate(order)],site_status='exploratory_ranking',site_imputed_features=imputed,site_interpretation=site['interpretation'])

def score_multihorizon(features,scope_confirmed,m,model_key=None,modalities=None):
    if m.get('feature_schema_version')=='CF_20260930' and m.get('histology_codebook')!={str(k):v for k,v in CATEGORIES['histology_code'].items()}:raise ValueError('病理分组字典与模型不匹配，请同步更新资源文件')
    full=m.get('format')==FULL_FORMAT
    hist=CATEGORIES['histology_code'].get(next((f.get('value') for f in features if f['key']=='PATH.histology_code'),None),'')
    hist=hist.replace('（','(').replace('）',')')
    def supported(model,year):
        return model['horizons'][str(year)]['research_enabled'] and (not full or model.get('histology_support',{}).get(hist,{}).get(str(year),{}).get('enabled',False))
    present=set(modalities) if modalities is not None else {f['key'].split('.')[0] for f in features}
    candidates=[k for k in PRIORITY if k in m['models'] and (m['models'][k]['modality'] is None or m['models'][k]['modality'] in present)]
    if model_key is not None:candidates=[model_key]
    selection=dict(mode='automatic' if model_key is None else 'validation_override',policy='available_inputs_ce_nce_pet_path_v3',candidates=candidates,skipped=[],selected_model=None,ignored_modalities=['PET_CT'] if 'PET_CT' in present and 'PATH_PET_CT' not in m['models'] else [])
    def failed(reason,missing=None):
        return {**blocked(reason,missing),'risks_by_year':{str(y):dict(probability=None,status='unavailable') for y in YEARS},'model_selection':selection}
    if not scope_confirmed:return failed('请先核对并确认患者符合模型适用人群。')
    if 'PATH' not in present:return failed('请添加病理报告后再评估。')
    result=None;key=None
    for candidate in candidates:
        model=m['models'].get(candidate)
        if not model or not model['research_enabled']:
            selection['skipped'].append(dict(model=candidate,reason='model_validation_insufficient'));continue
        allowed=[y for y in YEARS if supported(model,y)]
        if not allowed:
            selection['skipped'].append(dict(model=candidate,reason='histology_validation_insufficient'));continue
        probe=score_bundle(features,True,legacy_view(m,allowed[0]),candidate)
        if probe['status']!='available':
            selection['skipped'].append(dict(model=candidate,reason=probe['reason'],missing_features=probe.get('missing_features',[])));result=probe;continue
        key=candidate;result=probe;break
    if key is None:return failed(result['reason'] if result else '没有满足验证及输入要求的研究模型。',result.get('missing_features') if result else None)
    selection['selected_model']=key;risks={}
    for year in YEARS:
        h=m['models'][key]['horizons'][str(year)]
        if supported(m['models'][key],year):
            r=score_bundle(features,True,legacy_view(m,year),key)
            risks[str(year)]=dict(probability=r['recurrence_probability'],status='available',years_after_surgery=year)
        else:risks[str(year)]=dict(probability=None,status='validation_insufficient',years_after_surgery=year,reasons=h['disabled_reasons'] or ['histology_validation_insufficient'])
    result.update(prediction_type='research_multihorizon_recorded_recurrence_net_risk',recurrence_probability=None,horizon_months=None,risks_by_year=risks,model_selection=selection,
                  interpretation='术后第30天评估至术后1/3/5年的记录复发净风险；部位为条件性探索排序，不是器官绝对概率。',**ranked_sites(features,m['site_model']))
    if full:
        result['interpretation']='从手术日起算的1/3/5年记录复发研究估计，来自全部复发者及DFS>12个月未复发者组成的选择队列；不代表未经选择总体的已校准绝对风险。'
        if m['site_model'].get('enabled') and hist not in m['site_model'].get('supported_histologies',[]):
            result.update(top_sites=[],site_status='not_validated',site_reason='该病理类型的个体部位排序验证不足。')
    return result
