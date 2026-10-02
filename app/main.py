import asyncio, copy, hmac, secrets, time, uuid, os
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from .settings import ROOT, Settings, AppError
from .schemas import AnalyzeInput, PredictInput
from .providers import Provider
from .config_store import load_settings, save_settings
from .capabilities import test_capabilities
from .documents import read_report
from .features import public_schema, normalize_extraction, merge_features, LOOKUP, validate_value, display, continuous
from .risk import score, unavailable, model_public
from .demo import demo_case
from .report_review import review_report
from .knowledge import public_graph, case_evidence, evidence_paths, visual_data
from . import auth

@asynccontextmanager
async def lifespan(app):
    async def janitor():
        while True:
            await asyncio.sleep(60)
            cleanup()
    task=asyncio.create_task(janitor())
    try:yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):await task

app = FastAPI(title='肺癌报告研究工作台', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.mount('/static', StaticFiles(directory=ROOT/'static'), name='static')
settings=Settings(api_key='') if auth.ACCESS.enabled else load_settings()
SESSIONS={}
CASES={}
SEM=asyncio.Semaphore(2)
TEST_SEM=asyncio.Semaphore(1)
TTL=3600

def current_settings(request):
    if auth.ACCESS.enabled:
        return auth.SESSION_SETTINGS.get(request.cookies.get('mvp_session', ''), settings)
    return settings

def discard_session(token):
    auth.revoke(token)
    SESSIONS.pop(token, None)
    for key, stored in list(CASES.items()):
        if stored['owner'] == token:
            CASES.pop(key, None)

def cleanup():
    now = time.time()
    auth.purge()
    for token, touched in list(SESSIONS.items()):
        if now - touched > TTL or auth.ACCESS.enabled and token not in auth.LOGINS:
            discard_session(token)
    for key, stored in list(CASES.items()):
        if now - stored['time'] > TTL:
            CASES.pop(key, None)

def secure_response(response):
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Cache-Control']='no-store'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    response.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
    if auth.ACCESS.secure_cookie:
        response.headers['Strict-Transport-Security']='max-age=31536000'
    return response

@app.middleware('http')
async def local_boundary(request: Request, call_next):
    host=request.url.hostname
    if host not in auth.ACCESS.allowed_hosts:
        return secure_response(JSONResponse({'error':'访问地址未获准。'},status_code=403))
    cleanup()
    token=request.cookies.get('mvp_session','')
    public = request.url.path in {'/login', '/auth/login', '/healthz', '/static/login.js', '/static/login.css', '/static/style.css'}
    if os.getenv('APP_ENV') == 'production' and (not auth.ACCESS.enabled or not auth.ACCESS.ready() or not auth.ACCESS.secure_cookie) and not public:
        return secure_response(JSONResponse({'error':'测试入口尚未配置，请联系管理员。'},status_code=503))
    if auth.ACCESS.enabled and not public and not auth.authenticated(token):
        discard_session(token)
        response = JSONResponse({'error':'请登录后继续。'},status_code=401) if request.url.path.startswith(('/api/', '/auth/')) else RedirectResponse('/login',status_code=303)
        response.delete_cookie('mvp_session', secure=auth.ACCESS.secure_cookie, httponly=True, samesite='strict')
        return secure_response(response)
    if request.method not in ('GET','HEAD','OPTIONS'):
        origin=request.headers.get('origin')
        if origin and origin not in (f'http://{request.headers.get("host")}',f'https://{request.headers.get("host")}'):
            return secure_response(JSONResponse({'error':'拒绝跨站请求。'},status_code=403))
        if request.url.path != '/auth/login':
            header=request.headers.get('x-mvp-token','')
            valid=SESSIONS.get(token)
            if not valid or time.time()-valid>TTL or not hmac.compare_digest(token,header):
                return secure_response(JSONResponse({'error':'会话已过期，请刷新页面。'},status_code=403))
            SESSIONS[token]=time.time()
        if not request.headers.get('content-type','').lower().startswith('application/json'):
            return secure_response(JSONResponse({'error':'仅支持JSON请求。'}, status_code=415))
        try: length=int(request.headers.get('content-length','0'))
        except ValueError:length=999999999
        if length<=0:return secure_response(JSONResponse({'error':'请求须提供内容长度。'},status_code=411))
        cap = 4096 if request.url.path == '/auth/login' else 24*1024*1024
        if length>cap:return secure_response(JSONResponse({'error':'单次提交过大，请减少文件。'},status_code=413))
        if request.headers.get('transfer-encoding'):
            return secure_response(JSONResponse({'error':'不支持分块上传。'},status_code=400))
    response=await call_next(request)
    if auth.ACCESS.enabled and token in auth.LOGINS:
        response.set_cookie('mvp_session',token,httponly=True,secure=auth.ACCESS.secure_cookie,samesite='strict',max_age=TTL)
    return secure_response(response)

@app.get('/healthz')
async def health():
    ready = (not auth.ACCESS.enabled or auth.ACCESS.ready()) and model_public()['ready']
    if os.getenv('APP_ENV') == 'production':
        ready = ready and auth.ACCESS.enabled and auth.ACCESS.secure_cookie
    return JSONResponse({'status':'ok' if ready else 'configuration_required'},status_code=200 if ready else 503)

@app.get('/login')
async def login_page(request: Request):
    if not auth.ACCESS.enabled or auth.authenticated(request.cookies.get('mvp_session', '')):
        return RedirectResponse('/', status_code=303)
    return FileResponse(ROOT/'static/login.html')

@app.post('/auth/login')
async def login(request: Request):
    if not auth.ACCESS.enabled or not auth.ACCESS.ready():
        raise AppError('测试入口尚未配置，请联系管理员。', 503)
    address=request.client.host if request.client else 'unknown'
    if auth.blocked(address):
        return JSONResponse({'error':'尝试过于频繁，请15分钟后再试。'},status_code=429,headers={'Retry-After':'900'})
    auth.attempt(address)
    try:
        data=await request.json()
        username,password=data.get('username'),data.get('password')
        if not isinstance(username,str) or not isinstance(password,str) or len(username)>80 or len(password)>200:
            raise ValueError()
    except (ValueError,AttributeError):
        raise AppError('登录信息格式错误。',422) from None
    valid_password=await asyncio.to_thread(auth.check_password,password,auth.ACCESS.encoded_password)
    if not hmac.compare_digest(username.encode(),auth.ACCESS.username.encode()) or not valid_password:
        raise AppError('账号或密码错误。',401)
    new_token=auth.create_session()
    if not new_token:raise AppError('当前测试会话较多，请稍后重试。',429)
    discard_session(request.cookies.get('mvp_session',''))
    SESSIONS[new_token]=time.time()
    response=JSONResponse({'ok':True})
    response.set_cookie('mvp_session',new_token,httponly=True,secure=auth.ACCESS.secure_cookie,samesite='strict',max_age=TTL)
    return response

@app.post('/auth/logout')
async def logout(request: Request):
    discard_session(request.cookies.get('mvp_session',''))
    response=JSONResponse({'ok':True})
    response.delete_cookie('mvp_session',secure=auth.ACCESS.secure_cookie,httponly=True,samesite='strict')
    return response

@app.exception_handler(AppError)
async def error_handler(request, exc):return JSONResponse({'error':exc.message},status_code=exc.status)

@app.exception_handler(RequestValidationError)
async def validation_handler(request, exc):
    # Never echo request input: it can contain API credentials or reports.
    return JSONResponse({'error':'输入格式不符合要求，请检查报告、文件大小及字段类型。'},status_code=422)

@app.get('/')
async def home():return FileResponse(ROOT/'static/index.html')

@app.get('/knowledge')
async def knowledge_page():return FileResponse(ROOT/'static/knowledge.html')

@app.get('/api/knowledge')
async def knowledge_data():return public_graph()

@app.get('/api/knowledge/paths')
async def knowledge_paths(feature: str, stratum: str='ALL'):
    return evidence_paths(feature,stratum)

@app.get('/api/knowledge/visual')
async def knowledge_visual(stratum: str='ALL', policy: str='best', all_features: bool=False):
    return visual_data(stratum,policy,all_features)

@app.get('/api/status')
async def status(request: Request):
    now=time.time()
    token=request.cookies.get('mvp_session','')
    if token not in SESSIONS:token=secrets.token_urlsafe(32)
    SESSIONS[token]=now
    response=JSONResponse({'app_id':'lc-report-research-mvp','token':token,'providers':current_settings(request).public(),'model':model_public(),'schema':public_schema(),
                           'limits':{'file_mb':10,'pdf_pages':15,'reports':8},'version':'2.4.0','invitation_test':auth.ACCESS.enabled})
    response.set_cookie('mvp_session',token,httponly=True,secure=auth.ACCESS.secure_cookie,samesite='strict',max_age=TTL)
    return response

@app.post('/api/config')
async def configure(request: Request):
    global settings
    try:values=await request.json()
    except ValueError:raise AppError('配置不是有效JSON。')
    if not isinstance(values,dict):raise AppError('配置格式错误。')
    candidate=current_settings(request).updated(values)
    if auth.ACCESS.enabled:
        auth.SESSION_SETTINGS[request.cookies['mvp_session']]=candidate
    else:
        save_settings(candidate)
        settings=candidate
    return {'providers':candidate.public()}

@app.post('/api/config/test')
async def check_capabilities(request: Request):
    try:values=await request.json()
    except ValueError:raise AppError('配置不是有效JSON。')
    candidate=current_settings(request).updated(values)
    if TEST_SEM.locked():raise AppError('能力测试正在进行，请稍后重试。',429)
    async with TEST_SEM:
        return await test_capabilities(candidate)

@app.post('/api/analyze')
async def analyze(data: AnalyzeInput, request: Request):
    provider_settings=current_settings(request)
    if sum(len(r.text)+len(r.file_base64) for r in data.reports)>22*1024*1024:raise AppError('单次报告内容过大，请分批输入。')
    if 'PATH' not in {r.modality for r in data.reports}:raise AppError('请至少加入一份病理报告。')
    if not provider_settings.ready():raise AppError('请先配置统一的接口地址、模型名和API密钥。')
    if SEM.locked():raise AppError('当前分析任务较多，请稍后重试。',429)
    provider=Provider(provider_settings)
    reports=[]
    async with SEM:
        for report in data.reports:
            rid=uuid.uuid4().hex[:12]
            text,routing=await read_report(report,provider)
            payload=await provider.extract(report.modality,text)
            features,warnings=normalize_extraction(report.modality,payload,text,rid)
            if '[无法辨认]' in text:warnings.append('OCR包含无法辨认内容，请对照原始报告核实。')
            reports.append({'id':rid,'name':report.name,'modality':report.modality,'text':text,'routing':routing,'features':features,'warnings':warnings})
    features=merge_features(reports)
    case={'analysis_id':uuid.uuid4().hex,'revision':1,'case_label':data.case_label,'is_demo':False,'reports':reports,'features':features,
          'warnings':[w for r in reports for w in r['warnings']],
          'risk':unavailable('请核对编码特征后再评估。' if model_public()['ready'] else '尚未接入训练完成的复发模型，暂不能输出真实概率与部位排序。')}
    case['report_review']=review_report(features,model_public())
    case['knowledge']=case_evidence(features)
    # Small local, expiring in-memory store. No patient files or report logs.
    if len(CASES)>=20:
        oldest=min(CASES,key=lambda k:CASES[k]['time']);CASES.pop(oldest,None)
    CASES[case['analysis_id']]={'case':copy.deepcopy(case),'owner':request.cookies.get('mvp_session'),'time':time.time()}
    return case

@app.post('/api/predict')
async def predict(data: PredictInput, request: Request):
    stored=CASES.get(data.analysis_id)
    if not stored or stored['owner']!=request.cookies.get('mvp_session') or time.time()-stored['time']>TTL:
        raise AppError('病例已过期或不属于当前会话，请重新提取。',404)
    case=copy.deepcopy(stored['case'])
    if data.revision!=case['revision']:raise AppError('结果版本已变化，请刷新当前病例。',409)
    if not data.review_confirmed:raise AppError('请先核对提取值并勾选确认。')
    known={f['key'] for f in case['features']}
    if set(data.edits)-known:raise AppError('修正中含有本病例不存在的字段。')
    for f in case['features']:
        if f['key'] in data.edits:
            value=validate_value(LOOKUP[f['key']],data.edits[f['key']])
            if value!=f['value']:
                f['previous_value']=f['value'];f['value']=value;f['manual_override']=True
                f['note']='人工修正；原始提取值与证据保留供追溯'
                signed=f['field'].endswith('_hu')
                f['status']='missing' if value is None or not signed and value==-9 else 'uncertain' if not signed and value<0 else 'reviewed'
                f['display']=display(LOOKUP[f['key']],value)
        f['reviewed']=True
    case['risk']=score(case['features'],data.scope_confirmed,modalities=[r['modality'] for r in case['reports']])
    case['report_review']=review_report(case['features'],model_public())
    case['knowledge']=case_evidence(case['features'])
    case['revision']+=1
    stored.update(case=copy.deepcopy(case),time=time.time())
    return case

@app.get('/api/demo')
async def demo():
    case=demo_case();case['knowledge']=case_evidence(case['features']);return case

@app.post('/api/clear')
async def clear(request: Request):
    owner=request.cookies.get('mvp_session')
    for k in list(CASES):
        if CASES[k]['owner']==owner:CASES.pop(k,None)
    return {'cleared':True}
