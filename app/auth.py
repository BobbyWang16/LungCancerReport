"""Invitation-only authentication. Credentials are provisioned outside source control."""
import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600_000).hex()
    return f'pbkdf2_sha256$600000${salt}${digest}'


def check_password(password, encoded):
    try:
        algorithm, rounds, salt, expected = encoded.split('$')
        if algorithm != 'pbkdf2_sha256' or not 100_000 <= int(rounds) <= 1_000_000:
            return False
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(rounds)).hex()
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True)
class Access:
    enabled: bool = os.getenv('REQUIRE_LOGIN', 'true').lower() != 'false'
    username: str = os.getenv('INVITE_USERNAME', 'tongji')
    encoded_password: str = os.getenv('INVITE_PASSWORD_HASH', '')
    secure_cookie: bool = os.getenv('COOKIE_SECURE', 'true').lower() != 'false'
    allowed_hosts: tuple = tuple(filter(None, (
        *os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(','),
        os.getenv('RENDER_EXTERNAL_HOSTNAME', ''),
    )))

    def ready(self):
        try:
            a, r, s, d = self.encoded_password.split('$')
            return (bool(self.username) and a == 'pbkdf2_sha256'
                    and 100_000 <= int(r) <= 1_000_000 and len(bytes.fromhex(s)) >= 16
                    and len(bytes.fromhex(d)) == 32)
        except (ValueError, TypeError):
            return False


ACCESS = Access()
LOGINS = {}
ATTEMPTS = {}
SESSION_SETTINGS = {}
IDLE_SECONDS = 3600
MAX_SECONDS = 8 * 3600
MAX_LOGINS = 100
WINDOW_SECONDS = 15 * 60
MAX_ATTEMPTS = 8
GLOBAL_ATTEMPTS = []


def authenticated(token):
    record = LOGINS.get(token)
    now = time.time()
    if not record or now - record['touched'] > IDLE_SECONDS or now - record['created'] > MAX_SECONDS:
        return False
    record['touched'] = now
    return True


def purge():
    now = time.time()
    for token, record in list(LOGINS.items()):
        if now - record['touched'] > IDLE_SECONDS or now - record['created'] > MAX_SECONDS:
            revoke(token)
    for address, times in list(ATTEMPTS.items()):
        fresh = [t for t in times if now - t < WINDOW_SECONDS]
        if fresh:
            ATTEMPTS[address] = fresh
        else:
            ATTEMPTS.pop(address, None)
    GLOBAL_ATTEMPTS[:] = [t for t in GLOBAL_ATTEMPTS if now - t < 60]


def blocked(address):
    purge()
    return len(ATTEMPTS.get(address, [])) >= MAX_ATTEMPTS or len(GLOBAL_ATTEMPTS) >= 40


def attempt(address):
    now = time.time()
    ATTEMPTS.setdefault(address, []).append(now)
    GLOBAL_ATTEMPTS.append(now)


def create_session():
    purge()
    if len(LOGINS) >= MAX_LOGINS:
        return None
    token = secrets.token_urlsafe(32)
    LOGINS[token] = dict(created=time.time(), touched=time.time())
    return token


def revoke(token):
    LOGINS.pop(token, None)
    SESSION_SETTINGS.pop(token, None)
