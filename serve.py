"""One process owns expiring sessions and cases. Never enable multiple workers."""
import os
import uvicorn

if __name__ == '__main__':
    cloud = os.getenv('APP_ENV') == 'production'
    if cloud:
        from app.auth import ACCESS
        if not ACCESS.enabled or not ACCESS.ready() or not ACCESS.secure_cookie:
            raise SystemExit('Invitation credentials and secure cookies must be configured before deployment.')
    uvicorn.run('app.main:app', host='0.0.0.0' if cloud else '127.0.0.1',
                port=int(os.getenv('PORT', '10000' if cloud else '8770')),
                workers=1, access_log=False, server_header=False)
