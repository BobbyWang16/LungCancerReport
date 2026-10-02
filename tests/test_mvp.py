import base64, io, json, math
from pathlib import Path
import fitz, httpx, pytest
from PIL import Image
from fastapi.testclient import TestClient
from app import main, risk
from app.schemas import ReportInput
from app.settings import AppError, Settings, check_url
from app.documents import prepare_report
from app.features import LOOKUP, normalize_extraction, merge_features, validate_value
from app.providers import Provider, decode_json

@pytest.fixture
def client(monkeypatch,tmp_path):
    from app import config_store
    monkeypatch.setattr(config_store,'CONFIG_PATH',tmp_path/'provider.json')
    main.SESSIONS.clear();main.CASES.clear()
    monkeypatch.setattr(main,'settings',Settings(api_key='test-only-key'))
    with TestClient(main.app) as c:yield c

def auth(c):return {'X-MVP-Token':c.get('/api/status').json()['token']}
def report(data,name='test.png',**kwargs):return ReportInput(modality='PATH',name=name,file_base64=base64.b64encode(data).decode(),**kwargs)
def png():
    b=io.BytesIO();Image.new('RGB',(60,60),'white').save(b,'PNG');return b.getvalue()
def toy_model():
    return {'format':'fixed_horizon_multinomial_v1','is_demo':False,'model_id':'TEST_ONLY','version':'0',
            'scope':'test only','time_origin':'test origin','training_data_reference':'unit-test fixture, NOT patient model',
            'validation_status':'research','validation_summary':'unit-test fixture','horizon_months':36,
            'inputs':[{'key':'PATH.STAS','transform':'identity'}],
            'outcomes':{k:{'intercept':0,'coefficients':[0]} for k in ('no_event','death_without_recurrence','brain','bone','liver')}}

def test_text_route():
    p=prepare_report(ReportInput(modality='CE',text='右肺上叶结节'));assert p[0]['route']=='text'
def test_png_route():assert prepare_report(report(png()))[0]['route']=='vision'
def test_text_pdf_route():
    doc=fitz.open();page=doc.new_page();page.insert_text((30,50),'Synthetic pathology report with enough text: STAS positive; margins negative.')
    data=doc.tobytes();doc.close();assert prepare_report(report(data,'case.pdf'))[0]['route']=='text'
def test_mixed_pdf_route():
    doc=fitz.open();p=doc.new_page();p.insert_text((30,50),'Synthetic text layer with sufficiently many words for a normal text PDF.');p.insert_image(fitz.Rect(30,80,90,140),stream=png())
    data=doc.tobytes();doc.close();assert prepare_report(report(data,'mixed.pdf'))[0]['route']=='vision'
def test_force_ocr():
    doc=fitz.open();p=doc.new_page();p.insert_text((30,50),'Synthetic report with enough text to be extracted without OCR by default.')
    data=doc.tobytes();doc.close();assert prepare_report(report(data,'forced.pdf',force_ocr=True))[0]['route']=='vision'
def test_encrypted_pdf_rejected():
    doc=fitz.open();doc.new_page();data=doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256,owner_pw='owner',user_pw='user');doc.close()
    with pytest.raises(AppError,match='加密'):prepare_report(report(data,'encrypted.pdf'))
def test_too_many_pages():
    doc=fitz.open()
    for _ in range(16):doc.new_page()
    data=doc.tobytes();doc.close()
    with pytest.raises(AppError,match='15'):prepare_report(report(data,'long.pdf'))
@pytest.mark.parametrize('content,name',[(b'bad','.pdf'),(b'bad','.png'),(b'bad','.exe')])
def test_invalid_files(content,name):
    with pytest.raises(AppError):prepare_report(report(content,'test'+name))
def test_missing_is_not_negative():
    rows,_=normalize_extraction('PATH',{'features':[]},'report','r');assert next(x for x in rows if x['field']=='STAS')['value']==-9
def test_evidence_and_negation():
    rows,_=normalize_extraction('PATH',{'features':[{'field':'STAS','value':0,'evidence':'气腔播散：未见'}]},'气腔播散：未见','r')
    assert next(x for x in rows if x['field']=='STAS')['value']==0
def test_no_invented_evidence():
    rows,w=normalize_extraction('PATH',{'features':[{'field':'STAS','value':1,'evidence':'气腔播散：可见'}]},'气腔播散：未见','r')
    assert next(x for x in rows if x['field']=='STAS')['value']==-9 and w
@pytest.mark.parametrize('value',[float('nan'),float('inf'),101,'20',True])
def test_invalid_numeric(value):
    with pytest.raises(AppError):validate_value(LOOKUP['PATH.ki67_upper_pct'],value)
def test_illegal_enum():
    with pytest.raises(AppError):validate_value(LOOKUP['PATH.STAS'],5)
def test_modalities_isolated():
    a,_=normalize_extraction('CE',{'features':[{'field':'density_code','value':2,'evidence':'部分实性'}]},'部分实性','a')
    b,_=normalize_extraction('NCE',{'features':[{'field':'density_code','value':3,'evidence':'实性'}]},'实性','b')
    out=merge_features([{'features':a},{'features':b}]);assert next(x for x in out if x['key']=='CE.density_code')['value']==2;assert next(x for x in out if x['key']=='NCE.density_code')['value']==3
def test_same_modality_conflict():
    r=[]
    for v,e in [(0,'未见'),(1,'可见')]:
        a,_=normalize_extraction('PATH',{'features':[{'field':'STAS','value':v,'evidence':e}]},e,str(v));r.append({'features':a})
    f=next(x for x in merge_features(r) if x['key']=='PATH.STAS');assert f['value']==-6 and f['status']=='conflict'
def test_missing_model_never_fabricates(tmp_path,monkeypatch):
    monkeypatch.setattr(risk,'MODEL_PATH',tmp_path/'none.json');result=risk.score([],True);assert result['recurrence_probability'] is None and result['top_sites']==[]
def test_risk_probability_math():
    m=toy_model();r=risk.score([{'key':'PATH.STAS','value':1,'status':'reviewed','reviewed':True}],True,m)
    assert r['recurrence_probability']==pytest.approx(.6)
    assert r['recurrence_probability']+r['death_without_recurrence_probability']+r['no_event_probability']==pytest.approx(1)
    assert len(r['top_sites'])==3 and r['top_sites'][0]['conditional_probability']==pytest.approx(1/3)
@pytest.mark.parametrize('value,reviewed',[(None,True),(-9,True),(-6,True),(1,False)])
def test_risk_missing_blocks(value,reviewed):
    r=risk.score([{'key':'PATH.STAS','value':value,'status':'extracted','reviewed':reviewed}],True,toy_model());assert r['status']=='unavailable'
def test_demo_model_blocked():
    m=toy_model();m['is_demo']=True
    with pytest.raises(ValueError):risk.validate_model(m)
def test_scope_required():assert risk.score([],False,toy_model())['status']=='unavailable'
def test_csrf_required(client):assert client.post('/api/clear',json={}).status_code==403
def test_cross_origin_blocked(client):assert client.post('/api/clear',json={},headers={**auth(client),'Origin':'https://other.invalid'}).status_code==403
def test_keys_not_returned(client):
    h=auth(client);r=client.post('/api/config',headers=h,json={'api_key':'sensitive-test-key'})
    assert 'sensitive-test-key' not in r.text and 'sensitive-test-key' not in client.get('/api/status').text
def test_validation_error_no_input_echo(client):
    r=client.post('/api/analyze',headers=auth(client),json={'secret':'sensitive-test-value'})
    assert r.status_code==422 and 'sensitive-test-value' not in r.text
def test_demo_explicit_and_not_saved(client):
    r=client.get('/api/demo').json();assert r['is_demo'] and r['risk']['is_demo'];assert r['analysis_id'] not in main.CASES
def test_real_analyze_no_api_key(client,monkeypatch):
    monkeypatch.setattr(main,'settings',Settings(api_key=''))
    r=client.post('/api/analyze',headers=auth(client),json={'reports':[{'modality':'PATH','text':'病理文字'}]});assert r.status_code==422
def test_real_pipeline_review_export(client,monkeypatch,tmp_path):
    monkeypatch.setattr(risk,'MODEL_PATH',tmp_path/'none.json')
    async def extract(self,modality,text):return {'features':[{'field':'STAS','value':1,'evidence':'气腔播散：可见'}]}
    monkeypatch.setattr(Provider,'extract',extract)
    h=auth(client);r=client.post('/api/analyze',headers=h,json={'case_label':'SYNTHETIC_TEST','reports':[{'modality':'PATH','text':'气腔播散：可见'}]})
    assert r.status_code==200,r.text
    c=r.json();assert not c['is_demo'] and c['risk']['recurrence_probability'] is None
    p=client.post('/api/predict',headers=h,json={'analysis_id':c['analysis_id'],'revision':1,'edits':{'PATH.STAS':0},'review_confirmed':True})
    assert p.status_code==200,p.text
    case=p.json();f=next(x for x in case['features'] if x['key']=='PATH.STAS');assert f['value']==0 and f['previous_value']==1 and f['manual_override']
    assert case['risk']['top_sites']==[]
    assert client.post('/api/predict',headers=h,json={'analysis_id':c['analysis_id'],'revision':1,'review_confirmed':True}).status_code==409
def test_session_isolation(client,monkeypatch):
    async def extract(self,modality,text):return {'features':[]}
    monkeypatch.setattr(Provider,'extract',extract)
    c=client.post('/api/analyze',headers=auth(client),json={'reports':[{'modality':'PATH','text':'test'}]}).json()
    with TestClient(main.app) as other:
        r=other.post('/api/predict',headers=auth(other),json={'analysis_id':c['analysis_id'],'revision':1,'review_confirmed':True});assert r.status_code==404
def test_json_truncated_rejected():
    with pytest.raises(AppError):decode_json('{"features":[')
def test_remote_http_rejected():
    with pytest.raises(AppError):check_url('http://example.com/v1')
def test_provider_contract(monkeypatch):
    import asyncio
    calls=[]
    async def handler(request):
        body=json.loads(request.content);calls.append(body)
        content='synthetic OCR' if isinstance(body['messages'][0]['content'],list) else '{"features":[]}'
        return httpx.Response(200,json={'choices':[{'message':{'content':content},'finish_reason':'stop'}]})
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    p=Provider(Settings(api_key='fake',base_url='https://unified.invalid/v1',model='deepseek-flash'))
    async def run():
        assert (await p.extract('PATH','synthetic'))=={'features':[]}
        assert (await p.ocr(base64.b64encode(png()).decode()))=='synthetic OCR'
    asyncio.run(run());assert calls[0]['response_format']=={'type':'json_object'};assert calls[1]['messages'][0]['content'][1]['type']=='image_url'
def test_provider_error_sanitized(monkeypatch):
    import asyncio
    async def handler(request):return httpx.Response(401,text='secret provider echo')
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    p=Provider(Settings(api_key='fake'))
    with pytest.raises(AppError,match='鉴权') as e:asyncio.run(p.extract('PATH','synthetic'))
    assert 'secret provider echo' not in str(e.value)
