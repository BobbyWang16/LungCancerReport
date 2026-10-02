import json, math, hashlib
from pathlib import Path
from .settings import ROOT
from .features import LOOKUP
from .research_risk import FORMAT, validate_bundle, public_bundle, score_bundle, score_automatic
from .multihorizon_risk import FORMAT as MULTI_FORMAT,FORMATS as MULTI_FORMATS,validate_multihorizon,public_multihorizon,score_multihorizon

SITE_LABELS = {'brain': '脑', 'bone': '骨', 'liver': '肝', 'lung_pleura': '肺 / 胸膜',
               'locoregional': '局部 / 区域淋巴结', 'multisite': '同期多部位', 'other': '其他部位'}
MODEL_PATH = ROOT / 'models/active_model.json'

def finite(v): return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)

def validate_model(m):
    if isinstance(m,dict) and m.get('format') in MULTI_FORMATS:return validate_multihorizon(m)
    if isinstance(m,dict) and m.get('format')==FORMAT:return validate_bundle(m)
    if not isinstance(m, dict) or m.get('format') != 'fixed_horizon_multinomial_v1': raise ValueError('不支持的模型格式')
    if m.get('is_demo') is not False: raise ValueError('演示模型不能用于真实报告')
    for key in ('model_id', 'version', 'scope', 'time_origin', 'training_data_reference', 'validation_summary'):
        if not isinstance(m.get(key), str) or not m[key].strip(): raise ValueError('模型缺少必要元数据：'+key)
    if m.get('validation_status') not in ('research', 'external_validated'): raise ValueError('须声明模型验证状态')
    if not finite(m.get('horizon_months')) or not 1 <= m['horizon_months'] <= 120: raise ValueError('预测时间窗无效')
    inputs, outcomes = m.get('inputs'), m.get('outcomes')
    if not isinstance(inputs, list) or not 1 <= len(inputs) <= 200: raise ValueError('输入定义为空或过多')
    for x in inputs:
        if not isinstance(x, dict) or x.get('key') not in LOOKUP: raise ValueError('模型引用未知特征')
        if x.get('transform') not in ('identity', 'equals'): raise ValueError('未知变换')
        if not finite(x.get('center', 0)) or not finite(x.get('scale', 1)) or x.get('scale', 1) <= 0: raise ValueError('标准化参数无效')
        if x['transform'] == 'equals' and not finite(x.get('category')): raise ValueError('分类变换缺少category')
    required = {'no_event', 'death_without_recurrence'}
    if not isinstance(outcomes, dict) or not required <= set(outcomes): raise ValueError('模型必须区分无事件与未复发死亡')
    if not set(outcomes) <= required | set(SITE_LABELS) or len(set(outcomes) & set(SITE_LABELS)) < 3: raise ValueError('至少需要三个明确定义的复发部位类别')
    for data in outcomes.values():
        if not isinstance(data, dict) or not finite(data.get('intercept')): raise ValueError('截距无效')
        coef = data.get('coefficients')
        if not isinstance(coef, list) or len(coef) != len(inputs) or not all(finite(v) for v in coef): raise ValueError('模型系数维度或数值无效')
    thresholds = m.get('risk_thresholds')
    if thresholds is not None and (not isinstance(thresholds, list) or len(thresholds)!=2 or not all(finite(v) for v in thresholds) or not 0 < thresholds[0] < thresholds[1] < 1):
        raise ValueError('风险分层阈值无效')
    return m

def load_model(path=None):
    p = Path(path) if path else MODEL_PATH
    if not p.exists(): return None, '尚未接入完成训练与验证的复发模型'
    try:
        if p.stat().st_size > 8_000_000: return None, '模型文件过大'
        m = validate_model(json.loads(p.read_text(encoding='utf-8')))
        m['_sha256'] = hashlib.sha256(p.read_bytes()).hexdigest()
        return m, ''
    except (ValueError, OSError, KeyError, TypeError): return None, '模型文件不符合约定，请检查models目录的接口文档'

def model_public():
    m, error = load_model()
    if not m: return {'ready': False, 'reason': error}
    if m['format'] in MULTI_FORMATS:return public_multihorizon(m)
    if m['format']==FORMAT:return public_bundle(m)
    return {'ready': True, **{k: m[k] for k in ('model_id','version','scope','time_origin','horizon_months','validation_status','validation_summary')},
            'required_features': list(dict.fromkeys(x['key'] for x in m['inputs'])), 'sha256': m['_sha256']}

def unavailable(reason, missing=None):
    return {'status': 'unavailable', 'reason': reason, 'recurrence_probability': None, 'horizon_months': None,
            'top_sites': [], 'missing_features': missing or [], 'is_demo': False}

def score(features, scope_confirmed=False, model=None, model_key=None, modalities=None):
    if model is None:
        model, error = load_model()
        if model is None: return unavailable(error + '；不由语言模型生成复发概率或部位排名。')
    else: validate_model(model)
    if model['format'] in MULTI_FORMATS:return score_multihorizon(features,scope_confirmed,model,model_key,modalities)
    if model['format']==FORMAT:
        return score_bundle(features,scope_confirmed,model,model_key) if model_key is not None else score_automatic(features,scope_confirmed,model,modalities)
    if not scope_confirmed: return unavailable('请先核对并确认患者符合模型适用人群。')
    fmap = {f['key']: f for f in features}
    missing, vector = [], []
    for spec in model['inputs']:
        f = fmap.get(spec['key']); value = f.get('value') if f else None
        if not f or not f.get('reviewed') or not finite(value) or value < 0 or f.get('status') in ('conflict', 'missing', 'uncertain'):
            missing.append(spec['key']); continue
        x = value if spec['transform'] == 'identity' else float(value == spec['category'])
        vector.append((x-spec.get('center',0))/spec.get('scale',1))
    if missing: return unavailable('模型所需特征缺失、不确定或尚未核对；没有进行默认阴性填充。', list(dict.fromkeys(missing)))
    logits = {key: data['intercept'] + sum(a*b for a,b in zip(data['coefficients'],vector)) for key,data in model['outcomes'].items()}
    if not all(math.isfinite(v) for v in logits.values()): return unavailable('模型计算超出数值范围，请检查参数。')
    shift = max(logits.values()); weights = {k: math.exp(v-shift) for k,v in logits.items()}; total=sum(weights.values())
    probs = {k:v/total for k,v in weights.items()}
    recurrence = sum(v for k,v in probs.items() if k in SITE_LABELS)
    sites = sorted([{'site':k,'label':SITE_LABELS[k],'absolute_probability':v,
                     'conditional_probability':v/recurrence if recurrence>0 else None} for k,v in probs.items() if k in SITE_LABELS],key=lambda x:x['absolute_probability'],reverse=True)[:3]
    if recurrence == 0: sites = []
    level=None
    if model.get('risk_thresholds'):
        a,b=model['risk_thresholds'];level='低' if recurrence<a else '中' if recurrence<b else '高'
    return {'status':'available','reason':'','is_demo':False,'recurrence_probability':recurrence,
            'death_without_recurrence_probability':probs['death_without_recurrence'],'no_event_probability':probs['no_event'],
            'horizon_months':model['horizon_months'],'time_origin':model['time_origin'],'risk_level':level,'top_sites':sites,
            'model_id':model['model_id'],'model_version':model['version'],'model_sha256':model.get('_sha256'),
            'validation_status':model['validation_status'],'scope':model['scope'], 'missing_features':[],
            'interpretation':'部位概率是同一时间窗内首次复发类别的绝对概率；并非诊断。同期多部位须由训练终点统一定义。'}
