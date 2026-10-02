import csv, math, re, json
from collections import defaultdict
from .settings import ROOT, AppError

SPECIAL = {-9: '未记录', -8: '主灶不明', -7: '不适用', -6: '冲突', -5: '不确定'}
EXCLUDED = {'spread_description_code', 'positive_station_text_code'}
V3 = json.loads((ROOT / 'resources/feature_schema_v3.json').read_text(encoding='utf8'))
SCHEMA = defaultdict(list)
with (ROOT / 'resources/feature_dictionary.csv').open(encoding='utf-8-sig') as f:
    for row in csv.DictReader(f):
        if row['table'] in ('CE', 'NCE', 'PET_CT', 'PATH') and row['role'] == 'feature' and row['field'] not in EXCLUDED:
            row['key'] = row['table'] + '.' + row['field']
            if row['key'] in V3: row['kind'] = V3[row['key']]['kind']
            SCHEMA[row['table']].append(row)
CATEGORIES = defaultdict(dict)
with (ROOT / 'resources/category_mapping.csv').open(encoding='utf-8-sig') as f:
    for row in csv.DictReader(f):
        if row['field'] in {'histology_code', 'secondary_histology_code', 'pT_code', 'pN_code', 'pM_code', 'pStage_code'}:
            CATEGORIES[row['field']][int(row['code'])] = row['original_label']
LOOKUP = {r['key']: r for rows in SCHEMA.values() for r in rows}

def continuous(spec):
    if 'kind' in spec: return spec['kind'] == 'number'
    n = spec['field']
    return n.endswith(('_mm', '_pct', 'suvmax')) or n in ('nodes_examined', 'nodes_positive', 'grade_lower', 'grade_upper')

def options(spec):
    if continuous(spec): return None
    n = spec['field']
    if n in CATEGORIES: return {**CATEGORIES[n], **SPECIAL}
    if spec.get('key') in V3:
        return {**{int(k): v for k, v in V3[spec['key']]['options'].items()}, **SPECIAL}
    result = dict(SPECIAL)
    for match in re.finditer(r'(?:^|[；;])\s*(\d+)=([^；;]+)', spec['coding']):
        result[int(match[1])] = match[2]
    return result

def validate_value(spec, value):
    if value is None: return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise AppError('特征值须为有限数值或空值：' + spec['label'])
    if continuous(spec):
        signed = spec['field'].endswith('_hu')
        if not signed and value in SPECIAL: return None
        high = 3000 if signed else 1 if spec['field']=='node_positive_ratio' else 100 if spec['field'].endswith('_pct') or 'suvmax' in spec['field'] else 4 if spec['field'].startswith('grade_') else 300
        if not (-1000 if signed else 0) <= value <= high: raise AppError('特征值超出编码范围：' + spec['label'])
        if spec['field'].startswith('grade_') and value not in (1, 2, 3, 4): raise AppError('分化等级仅支持1—4。')
        if (spec['field'] in ('nodes_examined', 'nodes_positive') or spec['field'].endswith('_count')) and int(value) != value: raise AppError('淋巴结数量须为整数。')
        return value
    opts = options(spec)
    if value not in opts: raise AppError('分类编码不在字典中：' + spec['label'])
    return int(value)

def display(spec, value):
    if value is None: return '未记录'
    if not continuous(spec): return options(spec).get(value, str(value))
    return f'{value:g}' + (spec['unit'] or '')

def compact(s): return re.sub(r'\s+', '', str(s))

def prompt_dictionary(modality):
    result = []
    for spec in SCHEMA[modality]:
        item = {'field': spec['field'], 'label': spec['label'], 'coding': spec['coding'], 'unit': spec['unit']}
        if not continuous(spec): item['categories'] = options(spec)
        if spec['field'] in CATEGORIES: item['categories'] = CATEGORIES[spec['field']]
        if spec['field']=='histology_code':
            item['grouping_notes']='当前CF名义分类：LUAD腺癌；LUSC鳞癌；SCLC小细胞癌单列；PSC肉瘤样癌；NET为本研究其余肺神经内分泌肿瘤（如类癌/纯LCNEC），不能因为神经内分泌表达就判NET；ASC腺鳞癌独立，禁止自动并入MIX；MIX为明确混合/复合类型且不属于ASC；LELC淋巴上皮瘤样癌；ORC其他罕见肺恶性肿瘤；SGC肺涎腺型癌；MESC间叶性/肉瘤性肿瘤；HEME造血/淋巴系肿瘤。只按原始诊断归组，不能仅由免疫标志物或Ki-67推断；成分或来源不清时标记不确定并保留原文。'
        result.append(item)
    return result

def normalize_extraction(modality, payload, text, report_id):
    if not isinstance(payload, dict) or not isinstance(payload.get('features'), list):
        raise AppError('提取接口未返回约定的features数组，请检查模型对JSON输出的支持。', 502)
    proposed = defaultdict(list)
    for item in payload['features']:
        if isinstance(item, dict) and isinstance(item.get('field'), str): proposed[item['field']].append(item)
    rows, warnings = [], []
    for spec in SCHEMA[modality]:
        items = proposed.get(spec['field'], [])
        value, evidence, status, note = (None if continuous(spec) else -9), '', 'missing', ''
        accepted = []
        for item in items:
            try:
                v = validate_value(spec, item.get('value'))
            except AppError:
                note = '模型给出的编码越界，已置为未记录'; continue
            ev = str(item.get('evidence', ''))[:1800]
            if v is None or v == -9 and not spec['field'].endswith('_hu'): continue
            if not ev or compact(ev) not in compact(text):
                note = '未找到匹配的原文证据，已拒绝该值'; continue
            accepted.append((v, ev))
        if accepted:
            values = {x[0] for x in accepted}
            if len(values) > 1:
                value = None if continuous(spec) else -6
                status = 'conflict'; evidence = '；'.join(x[1] for x in accepted)[:2000]
            else:
                value, evidence = accepted[0]
                status = 'uncertain' if value in SPECIAL and not spec['field'].endswith('_hu') else 'extracted'
        if note: warnings.append(spec['label'] + '：' + note)
        rows.append({'key': spec['key'], 'modality': modality, 'field': spec['field'], 'label': spec['label'],
                     'value': value, 'display': display(spec, value), 'status': status, 'evidence': evidence,
                     'report_ids': [report_id], 'note': note, 'reviewed': False})
    return rows, warnings

def merge_features(reports):
    grouped = defaultdict(list)
    for report in reports:
        for feature in report['features']: grouped[feature['key']].append(feature)
    merged = []
    for key, items in grouped.items():
        spec = LOOKUP[key]
        present = [x for x in items if x['value'] is not None and (x['value'] != -9 or spec['field'].endswith('_hu'))]
        # Missing/ambiguous continuous values still carry a conflict status.
        conflict = any(x['status'] == 'conflict' for x in items)
        values = {x['value'] for x in present}
        row = dict(present[0] if present else items[0])
        row['report_ids'] = list(dict.fromkeys(r for x in items for r in x['report_ids']))
        if len(values) > 1 or conflict:
            row.update(value=None if continuous(spec) else -6, status='conflict', note='同模态报告值不一致，需人工核对')
            row['evidence'] = ' | '.join(x['evidence'] for x in present)[:2400]
        row['display'] = display(spec, row['value'])
        merged.append(row)
    return merged

def public_schema():
    return {t: [{**s, 'options': options(s), 'continuous': continuous(s)} for s in rows] for t, rows in SCHEMA.items()}
