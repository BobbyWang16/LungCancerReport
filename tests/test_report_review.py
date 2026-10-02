import pytest
from app.report_review import review_report
from app.features import CATEGORIES

def feature(field,value,status='reviewed'):
    return dict(key='PATH.'+field,field=field,value=value,status=status,reviewed=True,evidence='Synthetic report evidence',label=field,report_ids=['synthetic'])

@pytest.mark.parametrize('label',['LUAD','LUSC','SCLC','PSC','NET','ASC','MIX','LELC','ORC','SGC','MESC','HEME'])
def test_all_histologies_have_review_without_predictions(label):
    code=next(k for k,v in CATEGORIES['histology_code'].items() if v==label)
    r=review_report([feature('histology_code',code)])
    assert r['histology']==label and r['prompts'] and r['risk_scope']['en']
    assert r['highlights'][0]['evidence']=='Synthetic report evidence'
    assert 'recurrence_probability' not in r and 'top_sites' not in r
    assert 'current' in r['risk_scope']['en']

@pytest.mark.parametrize('value,status',[(-9,'missing'),(-6,'conflict'),(7,'uncertain'),(999,'reviewed')])
def test_unknown_or_uncertain_diagnosis_is_not_forced_to_luad(value,status):
    r=review_report([feature('histology_code',value,status)])
    assert r['histology']=='unmapped'

def test_evidence_and_conflicts_preserved():
    fs=[feature('nodes_examined',5),feature('nodes_positive',9),feature('margin_positive',1),feature('residual_R_code',0),feature('STAS',-6,'conflict')]
    r=review_report(fs)
    assert any('exceeds' in p['en'] for p in r['prompts'])
    assert any('disagree' in p['en'] for p in r['prompts'])
    assert r['uncertain_fields']==['PATH.STAS']
    assert all(f['key']!='PATH.STAS' for f in r['highlights'])

def test_predict_api_returns_review_when_risk_is_unavailable():
    import time
    from fastapi.testclient import TestClient
    from app import main
    with TestClient(main.app) as client:
        status=client.get('/api/status').json()
        code=next(k for k,v in CATEGORIES['histology_code'].items() if v=='SCLC')
        case=dict(analysis_id='all-histology-test',revision=1,features=[feature('histology_code',code)],reports=[dict(modality='PATH')])
        main.CASES[case['analysis_id']]=dict(case=case,owner=client.cookies.get('mvp_session'),time=time.time())
        try:
            response=client.post('/api/predict',headers={'X-MVP-Token':status['token']},json=dict(analysis_id=case['analysis_id'],revision=1,edits={},review_confirmed=True,scope_confirmed=False))
            assert response.status_code==200
            data=response.json()
            assert data['report_review']['histology']=='SCLC'
            assert data['risk']['status']=='unavailable' and data['risk']['top_sites']==[]
        finally:main.CASES.pop(case['analysis_id'],None)
