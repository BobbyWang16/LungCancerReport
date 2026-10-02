"""Evidence-linked report checks for every histology, independent of risk scoring.

These are report-review prompts, not treatment advice or prognostic weights.
No clinical fact is inferred from absent fields or from a histology family.
"""
from .features import CATEGORIES

def pair(zh,en):return {'zh':zh,'en':en}

def review_report(features,model_info=None):
    fmap={f['key']:f for f in features if f['key'].startswith('PATH.')}
    def valid(field):
        f=fmap.get('PATH.'+field,{})
        v=f.get('value')
        return isinstance(v,(int,float)) and v>=0 and f.get('status') not in ('conflict','uncertain','missing')
    h=fmap.get('PATH.histology_code',{})
    label=CATEGORIES['histology_code'].get(h.get('value'),'') if valid('histology_code') else ''
    label=label.replace('（','(').replace('）',')')
    note=pair('所有肺部肿瘤病理均可提取现有字典特征；以下为报告核对提示。','Existing dictionary fields can be extracted across lung-tumour histologies; the following are report-review prompts.')
    prompts=[]
    if not label:
        prompts.append(pair('病理类型未确定或字典未覆盖：请核对原始诊断，保留原文，不强制归为腺癌或鳞癌。','Histology is uncertain or unmapped: review the original diagnosis and retain its wording; do not force an adenocarcinoma or squamous category.'))
    elif label=='LUAD':
        prompts.append(pair('核对原位、微浸润或浸润性描述；组织学亚型、STAS和浸润径均按原文记录，不能用总径代替浸润径。','Check in situ, minimally invasive or invasive wording. Record subtypes, STAS and invasive size as reported; total size is not invasive size.'))
    elif label=='LUSC':
        prompts.append(pair('多数肺鳞癌为浸润性癌；不要求报告另写“浸润”才纳入分析。核对分化、切缘和淋巴结；若原文明示原位病变，则单独核对。','Most pulmonary squamous carcinomas are invasive; analysis inclusion must not require the additional word “invasive”. Review differentiation, margins and nodes; an explicitly reported in situ lesion requires separate review.'))
    elif label in ('SCLC','NET'):
        prompts.append(pair('保留神经内分泌肿瘤的具体诊断；核对原文中的坏死、有丝分裂及Ki-67描述，不单凭Ki-67改判类型。现有字典未覆盖的内容请在原文中核对。','Retain the specific neuroendocrine diagnosis. Review reported necrosis, mitoses and Ki-67; do not reclassify from Ki-67 alone. Check items outside the dictionary in the original report.'))
    elif label in ('ASC','MIX'):
        prompts.append(pair('保留混合或复合病理类型，核对各成分及原文比例；不要归并成单纯腺癌、鳞癌或小细胞癌。','Retain mixed or combined histology and review its components and reported proportions; do not collapse it into a pure carcinoma category.'))
    elif label in ('HEME','MESC'):
        prompts.append(pair('核对原始诊断及肿瘤来源。既有NSCLC(...)编码不证明其为上皮性肺癌；分期与分级须按实际肿瘤类别解释。','Review the original diagnosis and tumour origin. A legacy NSCLC(...) code does not establish epithelial lung carcinoma; interpret staging and grading for the actual tumour type.'))
    else:
        prompts.append(pair('保留具体病理名称，核对原发或转移性质、分级、切缘及淋巴结记录；不要套用腺癌专属分级或复发权重。','Retain the specific diagnosis; review primary versus metastatic origin, grade, margins and nodes. Do not apply adenocarcinoma-specific grading or recurrence weights.'))
    highlights=[]
    for field in ('histology_code','path_max_diameter_mm','grade_upper','margin_positive','residual_R_code','nodes_examined','nodes_positive','pT_code','pN_code','pM_code','pStage_code','lymphovascular_invasion','perineural_invasion','pleural_PL_code','STAS','ki67_upper_pct'):
        if valid(field):
            f=fmap['PATH.'+field]
            highlights.append({k:f.get(k) for k in ('key','field','label','value','display','evidence','report_ids','reviewed','manual_override')})
    missing=['PATH.'+field for field in ('histology_code','path_max_diameter_mm','margin_positive','nodes_examined','nodes_positive') if not valid(field)]
    conflicts=[f['key'] for f in fmap.values() if f.get('status') in ('conflict','uncertain')]
    n=fmap.get('PATH.nodes_examined',{}).get('value');pos=fmap.get('PATH.nodes_positive',{}).get('value')
    if valid('nodes_examined') and valid('nodes_positive') and pos>n:
        prompts.append(pair('阳性淋巴结数大于检查总数，请回查原文和计数单位。','Positive node count exceeds examined node count; review source text and counting units.'))
    if valid('margin_positive') and valid('residual_R_code') and fmap['PATH.margin_positive']['value']==1 and fmap['PATH.residual_R_code']['value']==0:
        prompts.append(pair('切缘阳性与R0编码不一致，请核对标本、切缘类型及原文。','Positive margin and R0 codes disagree; review the specimen, margin type and source.'))
    scope=pair('按当前CF病理分组核对原始诊断；个体风险输出取决于当前模型的分组与时间点验证支持。','Review the original diagnosis within its current CF histology group. Individual risk output requires current model support for that group and horizon.')
    if model_info and model_info.get('format')=='report_recurrence_multihorizon_v3':
        scope=pair('全部病理类型纳入报告分析；新版风险模型基于19,540例及五折内部验证。仅在当前病理类型和时间点有足够验证支持时显示概率，其他类型仍提供报告提示。','All histologies contribute to report analysis. The updated risk model uses 19,540 patients and five-fold internal validation. Probabilities require support for this histology and horizon; report checks remain available for other types.')
    return dict(version='CF_histology_report_review_v2',histology=label or 'unmapped',note=note,prompts=prompts,highlights=highlights,missing_common_fields=missing,uncertain_fields=conflicts,risk_scope=scope,clinical_validation=False)
