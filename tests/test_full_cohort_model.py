"""Self-contained deployment model contract, using synthetic inputs only."""
import json
from pathlib import Path
import pytest
from app import risk
from app.multihorizon_risk import score_multihorizon
BUNDLE=Path(__file__).resolve().parents[1]/"models/active_model.json"

@pytest.fixture(scope='module')
def model():
    m,error=risk.load_model(BUNDLE)
    assert m is not None,error
    return m


def synthetic(m,mod=None,hist=1):
    keys=['PATH']+(['PATH_'+mod] if mod else [])
    specs=[s for k in keys for s in m['models'][k]['inputs']]+m['site_model']['inputs']
    vals={s['key']:s['impute'] for s in specs if s['transform']!='missing'}
    vals['PATH.histology_code']=hist
    return [dict(key=k,value=v,reviewed=True,status='reviewed') for k,v in vals.items()]


@pytest.mark.parametrize('mod',[None,'CE','NCE','PET_CT'])
def test_supported_routing_and_top_three(model,mod):
    r=score_multihorizon(synthetic(model,mod),True,model)
    assert r['status']=='available' and r['selected_model']==('PATH_'+mod if mod else 'PATH')
    vals=[x['probability'] for x in r['risks_by_year'].values() if x['status']=='available']
    assert vals==sorted(vals)
    assert r['site_status']=='exploratory_ranking' and len(r['top_sites'])==3
    assert len({x['site'] for x in r['top_sites']})==3
    assert not any('absolute_probability' in x for x in r['top_sites'])


def test_lusc_rare_histology_and_review_gates(model):
    from app.features import CATEGORIES
    code=next(k for k,v in CATEGORIES['histology_code'].items() if v=='LUSC')
    for name,mo in model['models'].items():
        mod=mo['modality'];r=score_multihorizon(synthetic(model,mod,code),True,model)
        if r['status']=='available':
            chosen=model['models'][r['selected_model']]
            for year,out in r['risks_by_year'].items():
                if out['status']=='available':assert chosen['histology_support']['LUSC'][year]['enabled']
        if 'LUSC' not in model['site_model']['supported_histologies']:assert not r['top_sites']
    for label in ['HEME','MESC','UNKNOWN']:
        hist=next((k for k,v in CATEGORIES['histology_code'].items() if v==label),-9)
        assert score_multihorizon(synthetic(model,None,hist),True,model)['status']=='unavailable'
    assert score_multihorizon(synthetic(model),False,model)['status']=='unavailable'
    fs=synthetic(model);next(f for f in fs if f['key']=='PATH.histology_code')['reviewed']=False
    assert score_multihorizon(fs,True,model)['status']=='unavailable'


def test_synthetic_text_review_predict_api(model,monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    from app.features import LOOKUP
    from app.settings import Settings
    monkeypatch.setattr(risk,'MODEL_PATH',BUNDLE)
    monkeypatch.setattr(main,'settings',Settings(api_key='synthetic-test-only'))
    async def extract(self,modality,text):
        return {'features':[{'field':f['key'].split('.')[1],'value':f['value'],'evidence':text} for f in synthetic(model,'PET_CT') if f['key'].startswith(modality+'.') and f['key'] in LOOKUP]}
    monkeypatch.setattr(main.Provider,'extract',extract)
    main.SESSIONS.clear();main.CASES.clear()
    with TestClient(main.app) as c:
        st=c.get('/api/status').json();assert st['model']['format']=='report_recurrence_multihorizon_v3'
        h={'X-MVP-Token':st['token']}
        r=c.post('/api/analyze',headers=h,json={'case_label':'SYNTHETIC FULL COHORT TEST','reports':[{'modality':'PATH','text':'虚构测试病理报告'},{'modality':'PET_CT','text':'虚构测试PET-CT报告'}]})
        assert r.status_code==200,r.text
        case=r.json();p=c.post('/api/predict',headers=h,json={'analysis_id':case['analysis_id'],'revision':case['revision'],'review_confirmed':True,'scope_confirmed':True})
        assert p.status_code==200,p.text
        result=p.json()['risk'];assert result['model_version']=='2026-09-30.CF.5fold'
        assert result['selected_model']=='PATH_PET_CT'
        assert any(result['risks_by_year'][str(y)]['status']=='available' for y in (1,3,5))
        assert result['site_status']=='exploratory_ranking' and len(result['top_sites'])==3


