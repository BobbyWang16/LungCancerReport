import os
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')

class AppError(Exception):
    def __init__(self, message: str, status: int = 422, code: str = 'configuration'):
        self.message, self.status, self.code = message, status, code
        super().__init__(message)

def check_url(url: str):
    if not url:
        return
    if any(c.isspace() or ord(c)<32 for c in url):
        raise AppError('接口地址不能包含空格或控制字符。')
    try:
        p = urlparse(url)
        p.port  # Validate malformed or out-of-range ports before making a request.
    except ValueError:
        raise AppError('接口地址格式错误，请检查Base URL与端口。') from None
    if p.scheme not in ('https', 'http') or not p.hostname or p.username or p.password or p.query or p.fragment:
        raise AppError('接口地址须为不含密钥、查询参数或账号密码的HTTP(S) Base URL。')
    if p.scheme == 'http' and p.hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise AppError('远程接口须使用HTTPS；本机服务可使用HTTP。')
    if p.path.rstrip('/').endswith('/chat/completions'):
        raise AppError('请填写Base URL（可含/v1），不要包含/chat/completions。')
    if os.getenv('APP_ENV') == 'production':
        allowed = {s.strip().lower() for s in os.getenv('PROVIDER_ALLOWED_HOSTS', 'api.deepseek.com').split(',') if s.strip()}
        if p.scheme != 'https' or p.hostname.lower() not in allowed or p.port not in (None, 443):
            raise AppError('该接口域名尚未获准用于在线测试，请联系管理员加入允许列表。', 422, 'provider_host')

@dataclass(frozen=True)
class Settings:
    base_url: str = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
    model: str = os.getenv('DEEPSEEK_MODEL', 'deepseek-flash')
    api_key: str = os.getenv('DEEPSEEK_API_KEY', '')
    timeout: float = float(os.getenv('API_TIMEOUT_SECONDS', '120'))

    def public(self):
        return {'base_url': self.base_url, 'model': self.model,
                'key_set': bool(self.api_key), 'ready': self.ready()}

    def ready(self, kind=None):
        return bool(self.base_url and self.model and (self.api_key or urlparse(self.base_url).hostname in ('127.0.0.1', 'localhost', '::1')))

    def updated(self, values):
        allowed = {'base_url', 'model', 'api_key'}
        if not isinstance(values, dict) or set(values)-allowed or any(not isinstance(v,str) for v in values.values()):
            raise AppError('配置格式错误，请刷新页面后重试。')
        clean = {k:v.strip() for k,v in values.items()}
        if any(len(v) > (4096 if k=='api_key' else 2048 if k=='base_url' else 200) or any(ord(c)<32 for c in v) for k,v in clean.items()):
            raise AppError('接口配置过长或含有非法字符。')
        url=clean.get('base_url',self.base_url).rstrip('/')
        check_url(url)
        if not url or not clean.get('model',self.model):
            raise AppError('请填写接口地址和模型名。')
        if url!=self.base_url.rstrip('/') and self.api_key and not clean.get('api_key'):
            raise AppError('接口地址已改变，请重新填写API密钥，避免将原密钥发送到其他服务。')
        clean['base_url']=url
        if not clean.get('api_key'):clean.pop('api_key',None)
        return replace(self, **clean)
