from dataclasses import replace
import pytest
from app import auth, main

@pytest.fixture(autouse=True)
def legacy_local_boundary(monkeypatch):
    """Legacy unit tests exercise the local mode; cloud tests explicitly enable auth."""
    monkeypatch.setattr(auth, 'ACCESS', replace(auth.ACCESS, enabled=False, secure_cookie=False,
                                              allowed_hosts=('testserver','localhost','127.0.0.1')))
    monkeypatch.delenv('APP_ENV', raising=False)
    auth.LOGINS.clear();auth.ATTEMPTS.clear();auth.SESSION_SETTINGS.clear();auth.GLOBAL_ATTEMPTS.clear()
    main.SESSIONS.clear();main.CASES.clear()
    yield
    auth.LOGINS.clear();auth.ATTEMPTS.clear();auth.SESSION_SETTINGS.clear();auth.GLOBAL_ATTEMPTS.clear()
    main.SESSIONS.clear();main.CASES.clear()
