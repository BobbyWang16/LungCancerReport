# LungCancerReport

肺癌报告分析与证据图谱工作台 / Lung cancer report analysis and evidence atlas.

保留文本、PDF、PNG/JPG输入、CE/NCE/PET-CT与病理特征编码、人工核对、中英文切换、自动研究模型选择，以及支持人群内的1/3/5年风险和三个复发部位排序。复发部位是探索性排序；研究风险与验证边界在界面中显示，未获得支持的人群或时间点不生成概率。

## 邀请测试

整个应用和API均需服务器端登录，未开放注册。测试账号由`INVITE_USERNAME`配置，口令只以PBKDF2哈希保存在托管平台Secret中。源码没有测试密码、患者记录或API密钥。

每个登录会话独立配置DeepSeek兼容API。密钥与病例仅存于服务器内存，退出、空闲1小时或最长8小时后清除；服务重启也会清除。报告解析会向用户选定的模型接口发送内容，请仅输入去标识化测试报告。在线接口域名由管理员的`PROVIDER_ALLOWED_HOSTS`允许列表控制。

## 从GitHub部署

GitHub管理源码、自动测试和Docker镜像；Python后端可以部署到已有服务器或Render。GitHub Pages不支持此后端。当前采用阿里云ECS与Nginx HTTPS。

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/BobbyWang16/LungCancerReport)

1. 登录Render，点击上面的部署按钮，选择这个仓库的`main`分支。
2. 在`INVITE_PASSWORD_HASH`填入管理员生成的哈希，其他配置由`render.yaml`提供。
3. 部署成功后，以平台实际显示的HTTPS地址访问。`RENDER_EXTERNAL_HOSTNAME`自动加入服务允许地址。

使用免费单实例方案。空闲后可能休眠，首次打开需等待；服务器重启会结束当前测试会话。不要增加实例或Uvicorn worker；内存会话需要单进程。若采用自有域名，在`ALLOWED_HOSTS`中加入该域名。不要在GitHub Actions日志或源码中粘贴Secret。

## 已有服务器部署

需要Docker Compose、已指向服务器的域名，以及可用的HTTPS入口。先检查服务器现有服务；已有Nginx或其他反向代理时，沿用它们。

```bash
git clone https://github.com/BobbyWang16/LungCancerReport.git
cd LungCancerReport
python3 scripts/server_setup.py --domain reports.your-domain.org
```

按提示输入内部测试密码，配置文件`.env.production`权限为600，禁止提交到GitHub。

若服务器80/443端口空闲，可以启用内置Caddy自动申请HTTPS证书：

```bash
docker compose --env-file .env.production --profile https up -d --build
```

若已有HTTPS反向代理，仅启动后端，再将对应域名代理到`http://127.0.0.1:10000`：

```bash
docker compose --env-file .env.production up -d --build
```

后端端口仅绑定本机，单实例运行；病例和API密钥没有持久化卷。证书卷仅用于HTTPS证书。更新时先通过GitHub检查，再执行`git pull --ff-only`并重新运行相同的Compose命令。在线接口代理域名需要管理员加入`PROVIDER_ALLOWED_HOSTS`。

若服务器无法连接Docker Hub，可以使用GitHub Actions已验证并发布的GHCR镜像。将`COMMIT`替换为对应成功构建的完整提交SHA，固定部署版本：

```bash
docker pull ghcr.io/bobbywang16/lungcancerreport:COMMIT
docker tag ghcr.io/bobbywang16/lungcancerreport:COMMIT lungcancerreport:local
docker compose --env-file .env.production up -d --no-build app
```

已有Nginx时，为工具新增独立的域名配置，保留其他网站；HTTP仅用于证书验证和跳转HTTPS。证书更新后应配置`nginx -t && systemctl reload nginx`续期钩子。上线后检查`/healthz`、未登录API的401响应、邀请登录与退出，以及示例的风险和证据图显示。

也可使用Python 3.11及以上的独立虚拟环境运行，保留系统原有Python版本。将仓库放在`/opt/lungcancerreport`，安装依赖到`.venv`，创建不允许登录的`lungreport`系统用户后，将`deploy/lungcancerreport.service`安装到`/etc/systemd/system/`并启用。该服务仅监听`127.0.0.1:10000`，使用生产邀请配置，限制512 MiB内存并禁止写入应用目录。它与Compose后端是两种可选启动方式，同一端口只启动其中一种。

## 本机验证

```powershell
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
python scripts/password_hash.py
# 将输出哈希填入本地 .env 的 INVITE_PASSWORD_HASH；密码输入不会回显。
python serve.py
```

打开`http://127.0.0.1:8770`。开发环境关闭Secure Cookie仅用于本机HTTP；生产环境强制启用。

```powershell
python -m pytest -q
node tests/test_evidence_matrix.cjs
node tests/test_result_presentation.cjs
python scripts/check_publish.py
```

## 研究资源

`models/active_model.json`是冻结的汇总模型参数，版本`2026-09-30.CF.5fold`。`resources/evidence_graph.json`是汇总统计证据图，按模型SHA256检查兼容性。未重新训练或改变支持边界。本仓库不包含用于重新训练的个体数据。

This is an invitation-only research prototype. It is not intended for clinical decision-making. The published bundle contains software and aggregate fitted parameters only; individual patient records are not included.
