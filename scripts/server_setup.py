"""Initialize private server settings. Do not overwrite an existing configuration."""
import argparse
import getpass
import os
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.auth import password_hash

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--domain',required=True)
    parser.add_argument('--port',default=10000,type=int)
    args=parser.parse_args()
    domain=args.domain.strip().lower()
    if not re.fullmatch(r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}',domain):
        parser.error('Provide a domain name without protocol, port, path or wildcard.')
    if not 1024<=args.port<=65535:parser.error('Port must be between 1024 and 65535.')
    path=Path(__file__).resolve().parents[1]/'.env.production'
    if path.exists():raise SystemExit('Existing .env.production preserved. Review it before deploying.')
    password=getpass.getpass('Invitation password: ')
    if not password:raise SystemExit('A password is required.')
    content=(f'PUBLIC_DOMAIN={domain}\nAPP_PORT={args.port}\nALLOWED_HOSTS={domain},localhost,127.0.0.1\n'
             f"INVITE_USERNAME=tongji\nINVITE_PASSWORD_HASH='{password_hash(password)}'\n"
             'PROVIDER_ALLOWED_HOSTS=api.deepseek.com\nAPI_TIMEOUT_SECONDS=120\n')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w',encoding='utf8') as f:f.write(content)
    print('Private server configuration created; password was not echoed or stored in plaintext.')
