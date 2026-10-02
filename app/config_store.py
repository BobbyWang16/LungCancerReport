"""Local configuration; Windows credentials are protected with per-user DPAPI."""
import base64
import ctypes
from ctypes import wintypes
import json
import os
import tempfile
from pathlib import Path
from .settings import ROOT, Settings, AppError

CONFIG_PATH=ROOT/'runtime/provider_config.json'

def protect(data: bytes, decrypt=False) -> bytes:
    class Blob(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buf=ctypes.create_string_buffer(data)
    source=Blob(len(data),ctypes.cast(buf,ctypes.POINTER(ctypes.c_ubyte)));target=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree.restype=ctypes.c_void_p
    if decrypt:
        ok=crypt.CryptUnprotectData(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target))
    else:
        ok=crypt.CryptProtectData(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target))
    if not ok:raise OSError('Credential protection failed')
    try:return ctypes.string_at(target.data,target.size)
    finally:kernel.LocalFree(target.data)

def save_settings(settings: Settings):
    path=Path(CONFIG_PATH);temp=None
    try:
        data={'version':1,'base_url':settings.base_url,'model':settings.model}
        if os.name=='nt':
            data['key_encoding']='windows-dpapi'
            data['protected_key']=base64.b64encode(protect(settings.api_key.encode())).decode() if settings.api_key else ''
        else:
            # User-only file permissions on non-Windows installations.
            data['key_encoding']='private-file';data['api_key']=settings.api_key
        path.parent.mkdir(parents=True,exist_ok=True)
        fd,temp=tempfile.mkstemp(prefix='.provider-',dir=path.parent)
        with os.fdopen(fd,'w',encoding='utf8') as f:
            json.dump(data,f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
        os.chmod(temp,0o600);os.replace(temp,path);temp=None
    except (OSError,ValueError):
        raise AppError('无法保存本机接口设置，请检查配置文件写入权限。',500,'config_save') from None
    finally:
        if temp and os.path.exists(temp):os.unlink(temp)

def load_settings():
    default=Settings();path=Path(CONFIG_PATH)
    if not path.exists():return default
    try:
        data=json.loads(path.read_text(encoding='utf8'))
        if data.get('key_encoding')=='windows-dpapi':
            raw=data.get('protected_key','')
            key=protect(base64.b64decode(raw,validate=True),True).decode() if raw else ''
        elif data.get('key_encoding')=='private-file':key=data.get('api_key','')
        else:raise ValueError('Unknown encoding')
        # Do not reuse an environment key when a saved configuration exists.
        return Settings(api_key='').updated({'base_url':data['base_url'],'model':data['model'],'api_key':key})
    except (ValueError,OSError,KeyError,TypeError,AttributeError,AppError):
        # A copied/unreadable key must never silently fall back to another key.
        return Settings(api_key='')
