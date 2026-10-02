import hashlib,json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app import knowledge,main
from app.features import normalize_extraction
ROOT=Path(__file__).resolve().parents[1]

def test_graph_counts_and_endpoints():
    g=knowledge.public_graph();assert g['ready']
    ids={n['id'] for n in g['nodes']}
    assert len(ids)==len(g['nodes'])
    assert len({e['id'] for e in g['edges']})==len(g['edges'])
    assert all(e['source'] in ids and e['target'] in ids for e in g['edges'])
    assert sum(n['kind']=='feature' for n in g['nodes'])==210
    assert sum(n['kind']=='histology' for n in g['nodes'])==13
    assert g['summary']['external_curated_claims']==0
    assert g['summary']['patient_records_persisted']==0


def test_support_equals_model_gates():
    g=knowledge.graph();m=json.loads((ROOT/'models/active_model.json').read_text(encoding='utf8'))
    assert g['model_sha256']==hashlib.sha256((ROOT/'models/active_model.json').read_bytes()).hexdigest()
    enabled=[]
    for e in g['edges']:
        if e['relation']!='prediction_support':continue
        mod=e['target'].split(':',1)[1];h=e['stratum'];y=str(e['year']);part=m['models'][mod]
        assert e['enabled']==bool(part['histology_support'][h][y]['enabled'] and part['horizons'][y]['research_enabled'] and part['research_enabled'])
        if e['enabled']:enabled.append((mod,h,y))
    assert ('PATH','LUAD','3') in enabled
    assert ('PATH','LUSC','3') not in enabled
    assert ('PATH_NCE','LUSC','3') in enabled


def rows(mod,text,values):
    return normalize_extraction(mod,{'features':[{'field':k,'value':v,'evidence':ev} for k,v,ev in values]},text,'synthetic')[0]


def test_case_evidence_preserves_proof_and_missingness():
    f=rows('PATH','气腔播散可见，腺癌。',[('STAS',1,'气腔播散可见'),('histology_code',1,'腺癌')])
    f+=rows('CE','实性结节。',[('density_code',3,'实性结节')])
    r=knowledge.case_evidence(f)
    assert r['ready'] and r['histology']=='LUAD'
    assert r['matched_edge_count']>0
    assert {x['key'] for x in r['priorities']}<={'PATH.STAS','PATH.histology_code','CE.density_code'}
    assert next(x for x in r['priorities'] if x['key']=='PATH.STAS')['evidence']=='气腔播散可见'
    assert 'prediction' not in r and 'recurrence_probability' not in r
    assert all(e['stratum'] in ('ALL','LUAD') for e in knowledge.graph()['edges'] if e['id'] in r['matched_edge_ids'])


def test_conflicts_do_not_enter_fact_matches():
    f=rows('PATH','气腔播散可见。',[('STAS',1,'气腔播散可见')])
    next(x for x in f if x['key']=='PATH.STAS').update(status='conflict')
    r=knowledge.case_evidence(f);assert not r['priorities'];assert 'PATH.STAS' in r['unresolved_keys']


def test_non_luad_no_adeno_fact_inference():
    g=knowledge.graph();k=g['adeno_only_keys'][0]
    f=[{'key':'PATH.histology_code','value':2,'status':'reviewed'}, {'key':k,'value':1,'status':'extracted'}]
    r=knowledge.case_evidence(f);assert r['observed_features']==1


def test_version_mismatch_fails_closed(monkeypatch):
    monkeypatch.setattr(knowledge,'compatible',lambda:False)
    assert not knowledge.public_graph()['ready']
    assert not knowledge.case_evidence([])['ready']


def test_api_graph_is_aggregate_only():
    with TestClient(main.app) as c:
        r=c.get('/api/knowledge');assert r.status_code==200 and r.json()['ready']
        assert 'patient_id' not in r.text and 'api_key' not in r.text
        assert c.get('/knowledge').status_code==200
        demo=c.get('/api/demo').json();assert demo['knowledge']['ready']


def test_phi_does_not_enter_public_graph():
    marker='SYNTHETIC-PATIENT-SECRET'
    knowledge.case_evidence([{'key':'PATH.STAS','value':1,'status':'extracted','evidence':marker}])
    assert marker not in json.dumps(knowledge.public_graph())


def test_paths_are_actual_evidence_without_composed_effect():
    r=knowledge.evidence_paths('CE.long_diameter_mm');assert r['paths']
    es={e['id']:e for e in knowledge.graph()['edges']}
    for p in r['paths']:
        a,b=[es[x] for x in p['edge_ids']]
        assert a['q']<.05 and b['relation']=='predictive_contribution'
        assert p['nodes'][1] in (a['source'],a['target']) and b['source']==p['nodes'][1]
        assert not p['causal_inference'] and not p['same_patient_sample_established']
        assert 'score' not in p and 'probability' not in p
    assert not knowledge.evidence_paths('not_a_feature')['paths']
    assert not knowledge.evidence_paths('CE.long_diameter_mm','invented_population')['paths']


def test_unresolved_facts_preserved_without_entering_paths():
    f=[{'key':'PATH.STAS','value':-6,'status':'conflict','evidence':'synthetic conflicting text'}]
    r=knowledge.case_evidence(f);assert r['facts'][0]['status']=='conflict'
    assert not r['matched_edge_ids'] and not r['priorities']


