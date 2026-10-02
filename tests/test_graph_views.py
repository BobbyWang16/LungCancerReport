import pytest
from app import knowledge
from app.graph_views import association_edges, atlas_metrics, atlas_projection, case_projection

def test_primary_projection_uses_adjusted_before_significance(monkeypatch):
    raw=dict(id='raw',source='CE.a',target='PATH.b',relation='associated_with',stratum='ALL',q=.001)
    adjusted=dict(id='adjusted',source='CE.a',target='PATH.b',relation='adjusted_association',stratum='ALL',q=.2)
    g={'edges':[raw,adjusted]}
    assert not association_edges(g)
    assert association_edges(g,policy='raw')==[raw]
    assert association_edges(g,significant=False)==[adjusted]
    g.update(version='synthetic',nodes=[dict(id='CE.a',kind='feature')])
    g['edges'].append(dict(id='contrib',source='PATH.b',relation='predictive_contribution',stratum='ALL',effect=.01))
    monkeypatch.setattr(knowledge,'graph',lambda:g)
    monkeypatch.setattr(knowledge,'compatible',lambda:True)
    assert not knowledge.evidence_paths('CE.a')['paths']

def test_projection_coverage_is_counted_from_actual_graph():
    g=knowledge.graph();m=atlas_metrics(g);p=atlas_projection(g)
    assert m['candidate_fields']==210 and m['priority_fields']==43 and m['joint_fields']==30
    assert len(p['nodes'])==43 and len(p['edges'])==200
    assert m['primary_significant_pairs']==len(association_edges(g))
    assert sum(x['candidate_fields'] for x in m['by_report'])==210
    assert sum(x['priority_fields'] for x in m['by_report'])==43
    assert len(atlas_projection(g,all_features=True)['nodes'])==210
    assert atlas_projection(g,stratum='UNKNOWN')['edges']==[]
    assert all(e['q']<.05 for e in p['edges'])
    assert len({(e['source'],e['target']) for e in p['edges']})==len(p['edges'])
    actual_starts=sum(bool(knowledge.evidence_paths(n['id'])['paths']) for n in g['nodes'] if n['kind']=='feature')
    assert actual_starts==m['fields_with_two_step_evidence']==39

def test_case_gap_agenda_is_limited_to_submitted_applicable_reports():
    g=knowledge.graph()
    f=[dict(key='PATH.STAS',value=0,status='reviewed',evidence='STAS explicitly absent'),dict(key='PATH.grade_upper',value=None,status='missing')]
    p=case_projection(g,f,{'PATH.STAS':f[0]},'LUSC')
    assert all(n['modality']=='PATH' for n in p['nodes'])
    assert any(n['id']=='PATH.STAS' and n['observed'] and n['value']==0 for n in p['nodes'])
    assert all(x['key'] not in g['adeno_only_keys'] for x in p['review_agenda'])
    assert all(n['value'] is None for n in p['nodes'] if n['id'] not in {x['key'] for x in f})
    assert 'recurrence_probability' not in p

def test_visual_api_has_no_case_text():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        r=c.get('/api/knowledge/visual?all_features=true');assert r.status_code==200
        assert len(r.json()['network']['nodes'])==210
        assert 'patient_id' not in r.text and 'api_key' not in r.text
        demo=c.get('/api/demo').json();assert demo['knowledge']['visual']['nodes']
