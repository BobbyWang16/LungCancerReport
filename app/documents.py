import base64, io, warnings
from pathlib import Path
import fitz
from PIL import Image, ImageOps, UnidentifiedImageError
from .schemas import ReportInput
from .settings import AppError

MAX_PAGES = 15
MAX_PIXELS = 25_000_000

def png_bytes(data):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            im = Image.open(io.BytesIO(data))
            if im.width * im.height > MAX_PIXELS: raise AppError('图片像素过大，请缩小至2500万像素以内。')
            im = ImageOps.exif_transpose(im)
            if im.mode in ('RGBA', 'LA') or 'transparency' in im.info:
                rgba = im.convert('RGBA'); bg = Image.new('RGBA', rgba.size, 'white'); bg.alpha_composite(rgba); im = bg.convert('RGB')
            else: im = im.convert('RGB')
            im.thumbnail((2400, 3400))
            out = io.BytesIO(); im.save(out, 'PNG')
            return out.getvalue()
    except AppError: raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise AppError('图片损坏、格式不支持或像素过大。')

def prepare_report(report: ReportInput):
    if report.text.strip(): return [{'page': 1, 'route': 'text', 'text': report.text.strip()}]
    try: data = report.bytes()
    except ValueError as e: raise AppError(str(e))
    ext = Path(report.name).suffix.lower()
    if ext == '.txt':
        for encoding in ('utf-8-sig', 'gb18030'):
            try:
                text = data.decode(encoding).strip()
                if not text: raise AppError('文本文件为空。')
                return [{'page': 1, 'route': 'text', 'text': text}]
            except UnicodeDecodeError: pass
        raise AppError('文本编码无法识别，请保存为UTF-8。')
    if ext in ('.png', '.jpg', '.jpeg'):
        return [{'page': 1, 'route': 'vision', 'image_base64': base64.b64encode(png_bytes(data)).decode()}]
    if ext != '.pdf': raise AppError('支持文本、TXT、PDF、PNG、JPG/JPEG。')
    if not data.lstrip().startswith(b'%PDF-'): raise AppError('文件内容不是有效PDF。')
    try:
        with fitz.open(stream=data, filetype='pdf') as doc:
            if doc.needs_pass: raise AppError('PDF已加密，请先解密后上传。')
            if not 1 <= len(doc) <= MAX_PAGES: raise AppError('PDF须为1—15页，请拆分较长文件。')
            pages = []
            for i, page in enumerate(doc):
                text = page.get_text('text', sort=True).strip()
                # Any embedded image may carry unrepresented clinical content;
                # use vision for that page rather than silently losing it.
                use_vision = report.force_ocr or len(''.join(text.split())) < 30 or bool(page.get_images())
                if use_vision:
                    scale = min(2.0, 2400 / max(page.rect.width, 1), 3400 / max(page.rect.height, 1))
                    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                    pages.append({'page': i+1, 'route': 'vision', 'image_base64': base64.b64encode(pix.tobytes('png')).decode()})
                else: pages.append({'page': i+1, 'route': 'text', 'text': text})
            return pages
    except AppError: raise
    except Exception: raise AppError('PDF损坏或无法解析，请重新导出。')

async def read_report(report, provider):
    pages = prepare_report(report)
    output, routing = [], []
    for page in pages:
        text = page.get('text') if page['route'] == 'text' else await provider.ocr(page['image_base64'])
        if not text or not text.strip(): raise AppError(f'第{page["page"]}页未识别到文字。')
        if len(text) > 30000: raise AppError('单页识别文本过长，请拆分报告。')
        output.append(f'【第{page["page"]}页】\n{text}')
        routing.append({'page': page['page'], 'route': 'DeepSeek 图片识别 → 结构化' if page['route']=='vision' else '本地文本 → DeepSeek'})
    text = '\n\n'.join(output)
    if len(text) > 60000: raise AppError('报告超过60000字符，请拆分后输入。')
    return text, routing
