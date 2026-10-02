"""Small synthetic probes, never patient reports or cached provider assertions."""
import base64
import io
import re
import secrets
import time
from PIL import Image,ImageDraw,ImageFont
from .providers import Provider,decode_json
from .settings import AppError

def vision_probe():
    code=''.join(secrets.choice('23456789') for _ in range(6))
    image=Image.new('RGB',(512,160),'white');draw=ImageDraw.Draw(image)
    try:font=ImageFont.truetype('arial.ttf',64)
    except OSError:font=ImageFont.load_default(size=64)
    draw.text((256,80),code,font=font,fill='black',anchor='mm')
    data=io.BytesIO();image.save(data,format='PNG')
    return code,base64.b64encode(data.getvalue()).decode()

async def test_capabilities(settings):
    if not settings.ready():raise AppError('请先配置统一的接口地址、模型名和API密钥。')
    provider=Provider(settings);checks=[];blocked=False
    code,image=vision_probe();text_code='TEST-'+secrets.token_hex(4)
    probes=[
      ('text','text',[{'role':'user','content':'Reply with this exact text only: '+text_code}],False,text_code),
      ('json','text',[{'role':'user','content':'Return only a JSON object matching this example: '+
                     '{"probe":"'+text_code+'"}'}],True,text_code),
      ('vision','vision',[{'role':'user','content':[
          {'type':'text','text':'Read the six-digit code in this image. Reply with those digits only.'},
          {'type':'image_url','image_url':{'url':'data:image/png;base64,'+image}}]}],False,code)]
    for name,kind,messages,json_output,expected in probes:
        if blocked:
            checks.append({'capability':name,'status':'skipped','code':'blocked'});continue
        started=time.monotonic()
        try:
            content=await provider.chat(kind,messages,json_output,max_tokens=256,timeout=min(settings.timeout,20))
            if name=='json':
                try:value=decode_json(content)
                except AppError:raise AppError('JSON测试未通过。',502,'json_invalid') from None
                valid=isinstance(value,dict) and value.get('probe')==expected
            elif name=='vision':valid=re.sub(r'\s','',content.strip())==expected
            else:valid=content.strip()==expected
            checks.append({'capability':name,'status':'passed' if valid else 'failed',
                           'code':'ok' if valid else 'output_mismatch',
                           'latency_ms':round((time.monotonic()-started)*1000)})
        except AppError as exc:
            checks.append({'capability':name,'status':'failed','code':exc.code,
                           'http_status':getattr(exc,'http_status',None),
                           'latency_ms':round((time.monotonic()-started)*1000)})
            blocked=exc.code in {'auth','balance','rate_limit','connection','timeout','redirect'}
    passed=sum(c['status']=='passed' for c in checks)
    return {'status':'passed' if passed==3 else 'partial' if passed else 'failed',
            'checks':checks,'model':settings.model,'synthetic_only':True}
