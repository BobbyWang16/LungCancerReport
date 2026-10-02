import time
from dataclasses import replace
import pytest
from fastapi.testclient import TestClient
from app import auth, main
from app.settings import Settings, AppError, check_url

TEST_PASSWORD='synthetic-invitation-passphrase'
TEST_HASH=auth.password_hash(TEST_PASSWORD)

@pytest.fixture
def access(monkeypatch):
    monkeypatch.setattr(auth,'ACCESS',replace(auth.ACCESS,enabled=True,secure_cookie=True,
                                             username='synthetic-tester',encoded_password=TEST_HASH))
    monkeypatch.setattr(main,'settings',Settings(api_key=''))

def login(client):
    r=client.post('/auth/login',json={'username':'synthetic-tester','password':TEST_PASSWORD})
    assert r.status_code==200
    return client.get('/api/status').json()['token']

def test_protected_application_and_model(access):
    with TestClient(main.app,base_url='https://testserver') as c:
        for path in ['/api/status','/api/demo','/api/knowledge','/api/knowledge/visual','/api/knowledge/paths?feature=PATH.STAS']:
            assert c.get(path).status_code==401
        for path in ['/','/knowledge','/static/index.html','/static/knowledge.html','/static/app.js']:
            assert c.get(path,follow_redirects=False).headers['location']=='/login'
        assert c.get('/login').status_code==200
        token=login(c)
        assert c.get('/api/knowledge').json()['ready']
        assert c.get('/api/status').json()['model']['ready']
        assert c.get('/api/demo').json()['is_demo']
        assert token in auth.LOGINS

def test_credentials_cookie_and_logout(access):
    with TestClient(main.app,base_url='https://testserver') as c:
        for name in ['wrong','错误账号']:
            assert c.post('/auth/login',json={'username':name,'password':'wrong'}).status_code==401
        assert c.post('/auth/login',json={'username':'synthetic-tester','password':TEST_PASSWORD},headers={'origin':'https://evil.example'}).status_code==403
        r=c.post('/auth/login',json={'username':'synthetic-tester','password':TEST_PASSWORD})
        cookie=r.headers['set-cookie'].lower()
        assert all(x in cookie for x in ['httponly','secure','samesite=strict'])
        token=c.get('/api/status').json()['token']
        assert c.post('/auth/logout',json={}).status_code==403
        assert c.post('/auth/logout',json={},headers={'X-MVP-Token':token}).status_code==200
        assert c.get('/api/status').status_code==401
        assert token not in auth.LOGINS

def test_session_config_and_case_isolation(access):
    with TestClient(main.app,base_url='https://testserver') as a, TestClient(main.app,base_url='https://testserver') as b:
        ta,tb=login(a),login(b)
        key='synthetic-key-not-a-real-secret'
        r=a.post('/api/config',json={'api_key':key},headers={'X-MVP-Token':ta})
        assert r.status_code==200 and key not in r.text
        assert a.get('/api/status').json()['providers']['key_set']
        assert not b.get('/api/status').json()['providers']['key_set']
        main.CASES['synthetic-case']={'owner':ta,'time':time.time(),'case':{'revision':1}}
        r=b.post('/api/predict',json={'analysis_id':'synthetic-case','revision':1,'review_confirmed':True,'scope_confirmed':True},headers={'X-MVP-Token':tb})
        assert r.status_code==404
        a.post('/auth/logout',json={},headers={'X-MVP-Token':ta})
        assert 'synthetic-case' not in main.CASES
        assert ta not in auth.SESSION_SETTINGS

def test_expiry_removes_cases_and_provider_settings(access):
    with TestClient(main.app,base_url='https://testserver') as c:
        token=login(c)
        auth.SESSION_SETTINGS[token]=Settings(api_key='synthetic')
        main.CASES['synthetic-expiry']={'owner':token,'time':time.time(),'case':{}}
        auth.LOGINS[token]['created']=time.time()-auth.MAX_SECONDS-1
        assert c.get('/api/status').status_code==401
        assert token not in auth.SESSION_SETTINGS
        assert 'synthetic-expiry' not in main.CASES

def test_rate_limit_and_invalid_host(access):
    with TestClient(main.app,base_url='https://testserver') as c:
        for _ in range(auth.MAX_ATTEMPTS):
            assert c.post('/auth/login',json={'username':'wrong','password':'wrong'}).status_code==401
        r=c.post('/auth/login',json={'username':'synthetic-tester','password':TEST_PASSWORD})
        assert r.status_code==429 and r.headers['retry-after']=='900'
        assert c.get('/login',headers={'host':'evil.example'}).status_code==403

def test_fail_closed_without_hash(access,monkeypatch):
    monkeypatch.setattr(auth,'ACCESS',replace(auth.ACCESS,encoded_password=''))
    with TestClient(main.app,base_url='https://testserver') as c:
        assert c.get('/healthz').status_code==503
        assert c.post('/auth/login',json={'username':'synthetic-tester','password':TEST_PASSWORD}).status_code==503
        assert c.get('/api/status').status_code==401

def test_production_rejects_disabled_auth(access,monkeypatch):
    monkeypatch.setenv('APP_ENV','production')
    monkeypatch.setattr(auth,'ACCESS',replace(auth.ACCESS,enabled=False))
    with TestClient(main.app,base_url='https://testserver') as c:
        assert c.get('/healthz').status_code==503
        assert c.get('/api/status').status_code==503

@pytest.mark.parametrize('url',['http://localhost:1','https://127.0.0.1','https://169.254.169.254','https://api.deepseek.com.evil.example','https://evil.example','https://api.deepseek.com:444'])
def test_production_provider_allowlist(access,monkeypatch,url):
    monkeypatch.setenv('APP_ENV','production')
    with pytest.raises(AppError):check_url(url)

def test_password_hash_algorithm():
    assert auth.check_password(TEST_PASSWORD,TEST_HASH)
    assert not auth.check_password('wrong',TEST_HASH)
    assert not auth.check_password(TEST_PASSWORD,'bad')
    assert auth.password_hash(TEST_PASSWORD)!=TEST_HASH
