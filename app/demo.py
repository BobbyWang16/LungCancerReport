from .features import normalize_extraction, merge_features

def demo_case():
    # Entirely synthetic, deliberately isolated from user uploads and scoring.
    reports=[]
    examples=[('CE','右肺上叶部分实性结节，大小约24mm×18mm，边缘分叶、毛刺，胸膜牵拉，轻度不均匀强化。',[
        ('main_location_code',1,'右肺上叶'),('density_code',2,'部分实性结节'),('long_diameter_mm',24,'大小约24mm×18mm'),
        ('second_diameter_mm',18,'大小约24mm×18mm'),('lobulation',1,'边缘分叶'),('spiculation',1,'毛刺'),
        ('pleural_retraction',1,'胸膜牵拉'),('enhancement_degree',1,'轻度不均匀强化'),('enhancement_homogeneous',0,'轻度不均匀强化')]),
        ('PATH','右肺上叶浸润性腺癌。肿瘤最大径2.4cm，浸润灶最大径1.8cm。气腔播散：可见。胸膜侵犯：PL0。脉管侵犯：未见。切缘：阴性。淋巴结共12枚，阳性0枚。Ki-67：20%。',[
        ('invasion_status',2,'浸润性腺癌'),('path_tumor_diameter_mm',24,'肿瘤最大径2.4cm'),('path_invasive_diameter_mm',18,'浸润灶最大径1.8cm'),
        ('STAS',1,'气腔播散：可见'),('pleural_PL_code',0,'胸膜侵犯：PL0'),('lymphovascular_invasion',0,'脉管侵犯：未见'),
        ('margin_positive',0,'切缘：阴性'),('nodes_examined',12,'淋巴结共12枚'),('nodes_positive',0,'阳性0枚'),
        ('ki67_lower_pct',20,'Ki-67：20%'),('ki67_upper_pct',20,'Ki-67：20%'),('ki67_relation',0,'Ki-67：20%')])]
    for i,(mod,text,values) in enumerate(examples):
        rid='demo-'+str(i);payload={'features':[{'field':k,'value':v,'evidence':e} for k,v,e in values]}
        features,warnings=normalize_extraction(mod,payload,text,rid)
        reports.append({'id':rid,'name':'虚构'+mod+'示例','modality':mod,'text':text,'features':features,'warnings':warnings,
                        'routing':[{'page':1,'route':'内置虚构示例 / 未调用API'}]})
    return {'analysis_id':'demo','revision':1,'case_label':'虚构病例 · 仅供界面演示','is_demo':True,'reports':reports,
            'features':merge_features(reports),'warnings':['所有风险数字均为预置演示数据，与任何实际报告无关。'],
            'risk':{'status':'demo','is_demo':True,'horizon_months':36,'recurrence_probability':0.24,'risk_level':None,
                    'reason':'固定虚构数字，只用于展示界面，不是模型预测。','time_origin':'演示时间点',
                    'top_sites':[{'site':'brain','label':'脑','absolute_probability':0.08,'conditional_probability':1/3},
                                 {'site':'bone','label':'骨','absolute_probability':0.06,'conditional_probability':0.25},
                                 {'site':'lung_pleura','label':'肺 / 胸膜','absolute_probability':0.05,'conditional_probability':0.05/0.24}],
                    'model_id':'无 / 预置演示数据','model_version':'DEMO'}}
