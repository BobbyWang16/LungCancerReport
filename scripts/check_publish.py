"""Verify the exact tracked publish set. Never print matching secret content."""
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
result=subprocess.run(['git','ls-files','-z'],cwd=ROOT,capture_output=True,check=True)
files=[ROOT/name for name in result.stdout.decode().split('\0') if name]
if not files:
    raise SystemExit('No tracked publish set. Stage the intended files before checking.')
failures=[]
patterns=[re.compile(r'sk-[A-Za-z0-9_-]{24,}'),re.compile(r'gh[pousr]_[A-Za-z0-9]{30,}'),re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')]
for p in files:
    rel=p.relative_to(ROOT)
    if rel.parts[0] in {'runtime','FeatureAnalysis','outputs','examples'} or p.suffix.lower() in {'.xlsx','.xls','.sqlite','.npz','.log'} or p.name=='.env':
        failures.append(str(rel)+' forbidden file')
    content=p.read_text(encoding='utf8',errors='replace')
    if any(pattern.search(content) for pattern in patterns):failures.append(str(rel)+' possible credential')
    if re.search(r'(?<!\d)1[3-9]\d{9}(?!\d)|(?<!\d)\d{17}[0-9Xx](?!\d)',content) and p.suffix in {'.json','.csv'}:
        # Hashes/coefficients may contain long digit runs; only delimited strings are identifiers.
        if re.search(r'"(?:1[3-9]\d{9}|\d{17}[0-9Xx])"',content):failures.append(str(rel)+' possible identifier')
model=ROOT/'models/active_model.json'
graph=json.loads((ROOT/'resources/evidence_graph.json').read_text(encoding='utf8'))
if graph['model_sha256']!=hashlib.sha256(model.read_bytes()).hexdigest():failures.append('Model/graph mismatch')
if graph['summary']['patient_records_persisted']!=0:failures.append('Graph contains patient records')
for p in [model,ROOT/'resources/evidence_graph.json']:
    obj=json.loads(p.read_text(encoding='utf8'))
    def walk(x):
        if isinstance(x,dict):
            if set(x)&{'patient_id','patient_name','report_text','file_base64','api_key','protected_key'}:
                failures.append(str(p.relative_to(ROOT))+' contains forbidden record fields')
            for v in x.values():walk(v)
        elif isinstance(x,list):
            for v in x:walk(v)
    walk(obj)
if failures:raise SystemExit('\n'.join(failures))
print(f'Publish check passed: {len(files)} tracked files; compatible aggregate model/graph; no raw patient files or credential patterns.')
