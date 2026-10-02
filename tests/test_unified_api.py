import asyncio
import base64
import io
import json
import os

import httpx
import pytest
from PIL import Image
from fastapi.testclient import TestClient

from app import capabilities, config_store, main
from app.settings import Settings, AppError


def mock_transport(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))


def reply(content):
    return httpx.Response(200, json={'choices': [{'message': {'content': content}, 'finish_reason': 'stop'}]})


@pytest.mark.parametrize('image_ok,json_ok', [(True, True), (False, True), (True, False)])
def test_capability_contract(monkeypatch, image_ok, json_ok):
    code, image = capabilities.vision_probe()
    assert Image.open(io.BytesIO(base64.b64decode(image))).size == (512, 160)
    monkeypatch.setattr(capabilities, 'vision_probe', lambda: (code, image))
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        assert str(request.url) == 'https://provider.invalid/v1/chat/completions'
        assert request.headers['authorization'] == 'Bearer synthetic-key'
        assert body['model'] == 'deepseek-flash'
        assert body['thinking'] == {'type': 'disabled'}
        content = body['messages'][0]['content']
        if isinstance(content, list):
            assert code not in content[0]['text']
            assert content[1]['image_url']['url'] == 'data:image/png;base64,' + image
            return reply(code if image_ok else 'I cannot view images')
        if 'response_format' in body:
            assert body['response_format'] == {'type': 'json_object'}
            return reply(content.split('example: ', 1)[1] if json_ok else 'not JSON')
        return reply(content.split('only: ', 1)[1])

    mock_transport(monkeypatch, handler)
    result = asyncio.run(capabilities.test_capabilities(Settings(base_url='https://provider.invalid/v1', api_key='synthetic-key')))
    assert len(calls) == 3
    assert result['status'] == ('passed' if image_ok and json_ok else 'partial')
    assert result['checks'][2]['status'] == ('passed' if image_ok else 'failed')
    assert result['checks'][1]['status'] == ('passed' if json_ok else 'failed')
    assert 'synthetic-key' not in json.dumps(result)


@pytest.mark.parametrize('status,code', [(401, 'auth'), (403, 'auth'), (402, 'balance'), (429, 'rate_limit'), (302, 'redirect'), (500, 'http')])
def test_failed_probes_sanitized(monkeypatch, status, code):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, text='private-key-and-provider-details')
    mock_transport(monkeypatch, handler)
    result = asyncio.run(capabilities.test_capabilities(Settings(api_key='synthetic-key')))
    assert result['status'] == 'failed'
    assert result['checks'][0]['code'] == code
    assert len(calls) == (3 if status == 500 else 1)
    assert result['checks'][1]['status'] == ('failed' if status == 500 else 'skipped')
    assert 'private-key' not in json.dumps(result)


def test_timeout_skips_remaining(monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout('synthetic secret detail', request=request)
    mock_transport(monkeypatch, handler)
    result = asyncio.run(capabilities.test_capabilities(Settings(api_key='synthetic-key')))
    assert [c['code'] for c in result['checks']] == ['timeout', 'blocked', 'blocked']


def test_persist_roundtrip(monkeypatch, tmp_path):
    path = tmp_path / 'provider.json'
    monkeypatch.setattr(config_store, 'CONFIG_PATH', path)
    settings = Settings(api_key='test-only-persistent-key', model='deepseek-flash')
    config_store.save_settings(settings)
    assert config_store.load_settings() == settings
    if os.name == 'nt':
        assert 'test-only-persistent-key' not in path.read_text()
        assert json.loads(path.read_text())['key_encoding'] == 'windows-dpapi'
    config_store.save_settings(Settings(api_key=''))
    assert config_store.load_settings().api_key == ''


def test_corrupt_saved_config_does_not_reuse_key(monkeypatch, tmp_path):
    path = tmp_path / 'provider.json'
    path.write_text('{corrupted')
    monkeypatch.setattr(config_store, 'CONFIG_PATH', path)
    assert config_store.load_settings().api_key == ''


def test_retained_key_bound_to_endpoint():
    s = Settings(api_key='test-secret')
    assert s.updated({'api_key': ''}).api_key == 'test-secret'
    with pytest.raises(AppError, match='地址已改变'):
        s.updated({'base_url': 'https://another.invalid', 'api_key': ''})
    assert s.updated({'base_url': 'https://another.invalid', 'api_key': 'replacement'}).api_key == 'replacement'


@pytest.mark.parametrize('values', [[], {'model': None}, {'vision_key': 'old'}, {'base_url': 'http://remote.invalid'}, {'base_url': 'https://user:pass@example.com'}, {'base_url': 'https://example.com?key=secret'}, {'base_url': 'https://example.com:99999'}, {'base_url': 'https://[oops'}, {'base_url': 'https://example.com/chat/completions'}, {'model': ''}])
def test_invalid_settings(values):
    with pytest.raises(AppError):
        Settings(api_key='').updated(values)


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(config_store, 'CONFIG_PATH', tmp_path / 'provider.json')
    monkeypatch.setattr(main, 'settings', Settings(api_key='original-test-key'))
    monkeypatch.setattr(main, 'TEST_SEM', asyncio.Semaphore(1))
    with TestClient(main.app) as c:
        yield c


def auth(client):
    return {'X-MVP-Token': client.get('/api/status').json()['token']}


def test_candidate_test_does_not_save(client, monkeypatch):
    seen = []
    async def probe(settings):
        seen.append(settings)
        return {'status': 'passed', 'checks': [], 'synthetic_only': True}
    monkeypatch.setattr(main, 'test_capabilities', probe)
    r = client.post('/api/config/test', json={'api_key': 'draft-test-key'}, headers=auth(client))
    assert r.status_code == 200 and seen[0].api_key == 'draft-test-key'
    assert main.settings.api_key == 'original-test-key'
    assert not config_store.CONFIG_PATH.exists()
    assert 'draft-test-key' not in r.text


def test_config_save_failure_preserves_active_settings(client, monkeypatch):
    def fail(settings):
        raise AppError('无法保存本机接口设置，请检查配置文件写入权限。', 500)
    monkeypatch.setattr(main, 'save_settings', fail)
    r = client.post('/api/config', json={'api_key': 'draft-test-key'}, headers=auth(client))
    assert r.status_code == 500
    assert main.settings.api_key == 'original-test-key'


def test_probe_csrf_and_busy(client, monkeypatch):
    assert client.post('/api/config/test', json={}).status_code == 403
    class Busy:
        def locked(self):
            return True
    monkeypatch.setattr(main, 'TEST_SEM', Busy())
    assert client.post('/api/config/test', json={}, headers=auth(client)).status_code == 429


def test_probe_requires_key(client, monkeypatch):
    monkeypatch.setattr(main, 'settings', Settings(api_key=''))
    assert client.post('/api/config/test', json={}, headers=auth(client)).status_code == 422
