# StockPilot Linux 部署指南

本文档用于将 StockPilot 部署到一台 Linux 服务器，推荐架构如下：

```text
浏览器 ──HTTP/HTTPS──> Nginx（80/443）
                         ├── /       -> frontend/dist 静态文件
                         └── /api/*  -> Uvicorn 127.0.0.1:9010
                                           └── SQLite backend/data/stock_agent.db
```

> 当前版本没有用户登录、权限隔离和管理接口鉴权。不要将服务不加保护地直接暴露在公网。公网部署至少应启用 HTTPS 和 Nginx Basic Auth，或仅允许可信 IP/VPN 访问。

## 1. 部署前准备

推荐系统：Ubuntu 24.04 LTS 或 Debian 12。服务器至少准备 2 核 CPU、2 GB 内存和 10 GB 可用磁盘。

软件要求：

- Python 3.11 或更高版本
- Node.js 20.19+ 或 22.12+
- Nginx
- Git（使用 Git 拉取代码时需要）
- 可访问模型 API 和公开行情数据源的网络

本文假定：

| 项目 | 示例值 |
|---|---|
| 项目目录 | `/opt/stock-agent` |
| 运行用户 | `stockagent` |
| 后端地址 | `127.0.0.1:9010` |
| 域名 | `stock.example.com` |

请把文中的 `stock.example.com` 替换为真实域名。如果暂时只使用服务器 IP，也可以将其替换为 IP 地址，并跳过 HTTPS 步骤。

## 2. 安装系统依赖

以下命令适用于 Ubuntu/Debian：

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx git curl apache2-utils
python3 --version
node --version
npm --version
```

如果服务器还没有符合版本要求的 Node.js，请先通过 Node.js 官方发行包或服务器的软件源安装 Node.js 22 LTS，再继续部署。不要在 Node 版本不符合要求时执行前端构建。

## 3. 上传项目

### 方式 A：通过 Git 拉取

```bash
sudo mkdir -p /opt/stock-agent
sudo chown -R "$USER":"$USER" /opt/stock-agent
git clone https://github.com/boruce0622/stock-agent.git /opt/stock-agent
cd /opt/stock-agent
```

如果目标目录已经包含代码，请使用项目既有的 Git 更新流程，不要再次执行 `git clone`。

### 方式 B：从本机上传

在本机执行：

```bash
rsync -av --delete \
  --exclude '.venv' \
  --exclude 'frontend/node_modules' \
  --exclude 'frontend/dist' \
  --exclude 'backend/data' \
  ./stock-agent/ root@服务器IP:/opt/stock-agent/
```

首次部署可以排除 `backend/data`；升级已有服务器时不要覆盖或删除服务器上的 `backend/data`。

## 4. 安装后端

```bash
cd /opt/stock-agent
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install ./backend
mkdir -p backend/data
```

创建生产环境配置：

```bash
cd /opt/stock-agent/backend
APP_SECRET="$(../.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
sudo tee .env >/dev/null <<EOF
APP_ENV=production
APP_HOST=127.0.0.1
APP_PORT=9010
DATABASE_URL=sqlite+aiosqlite:///./data/stock_agent.db
CORS_ORIGINS=https://stock.example.com
LOG_LEVEL=INFO
APP_ENCRYPTION_KEY=${APP_SECRET}
LLM_TIMEOUT_SECONDS=45
LLM_MAX_RETRIES=2
LLM_TEMPERATURE=0.1
EOF
unset APP_SECRET
sudo chmod 600 .env
```

`APP_ENCRYPTION_KEY` 用于加密数据库中的模型 API Key。部署后必须备份这个值，并且升级时不得重新生成；密钥丢失后，数据库中已有的 API Key 将无法解密。

如果使用 HTTP 或 IP 访问，将 `CORS_ORIGINS` 改成浏览器实际访问的完整来源，例如 `http://192.0.2.10`。多个来源使用英文逗号分隔。

## 5. 构建前端

```bash
cd /opt/stock-agent/frontend
npm ci
npm run test
npm run build
test -f dist/index.html
```

前端通过同源相对路径 `/api` 请求后端，因此生产构建无需写入后端地址，Nginx 会负责转发。

## 6. 创建运行用户和 systemd 服务

创建不可登录的系统用户，并授予项目目录权限：

```bash
sudo useradd --system --home /opt/stock-agent --shell /usr/sbin/nologin stockagent 2>/dev/null || true
sudo chown -R stockagent:stockagent /opt/stock-agent
sudo chmod 750 /opt/stock-agent/backend
sudo chmod 750 /opt/stock-agent/backend/data
```

创建服务文件：

```bash
sudo tee /etc/systemd/system/stock-agent.service >/dev/null <<'EOF'
[Unit]
Description=StockPilot FastAPI Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=stockagent
Group=stockagent
WorkingDirectory=/opt/stock-agent/backend
EnvironmentFile=/opt/stock-agent/backend/.env
ExecStart=/opt/stock-agent/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 9010 --workers 1 --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
KillSignal=SIGINT
NoNewPrivileges=true
PrivateTmp=true
UMask=0077

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now stock-agent
sudo systemctl status stock-agent --no-pager
curl --fail http://127.0.0.1:9010/api/v1/health/live
curl --fail http://127.0.0.1:9010/api/v1/health/ready
```

必须保持 `--workers 1`。当前 SQLite、后台任务恢复和进程内 SSE Broker 都按单进程设计，多 Worker 会导致事件流和任务状态不一致。

## 7. 配置 Nginx

```bash
sudo tee /etc/nginx/sites-available/stock-agent >/dev/null <<'EOF'
server {
    listen 80;
    listen [::]:80;
    server_name stock.example.com;

    root /opt/stock-agent/frontend/dist;
    index index.html;

    client_max_body_size 2m;

    location /api/ {
        proxy_pass http://127.0.0.1:9010;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE 流式响应需要关闭缓冲并延长读取超时。
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        add_header X-Accel-Buffering no;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }

    location ~ /\. {
        deny all;
    }
}
EOF

sudo ln -sfn /etc/nginx/sites-available/stock-agent /etc/nginx/sites-enabled/stock-agent
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

访问 `http://stock.example.com` 验证页面和流式对话是否正常。

### 使用服务器 IP

没有域名时，可将配置中的：

```nginx
server_name stock.example.com;
```

改成：

```nginx
server_name _;
```

同时把 `backend/.env` 中的 `CORS_ORIGINS` 改成实际访问地址，然后重启后端：

```bash
sudo systemctl restart stock-agent
```

## 8. 公网访问保护

### 启用 Basic Auth

当前应用自身没有登录功能。创建 Nginx 访问账号：

```bash
sudo htpasswd -c /etc/nginx/.stock-agent.htpasswd admin
```

在 Nginx `server { ... }` 内加入：

```nginx
auth_basic "StockPilot";
auth_basic_user_file /etc/nginx/.stock-agent.htpasswd;
```

然后检查并重载：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Basic Auth 只适合小规模受信任用户。正式多用户环境应在应用或统一身份网关中实现认证、授权、审计和速率限制。

### 启用 HTTPS

先将域名 A/AAAA 记录指向服务器，并确认 HTTP 可以访问。然后安装 Certbot 并签发证书：

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d stock.example.com
sudo certbot renew --dry-run
```

如果此前使用 HTTP，请确认 `backend/.env` 中已经改为：

```dotenv
CORS_ORIGINS=https://stock.example.com
```

修改后执行：

```bash
sudo systemctl restart stock-agent
```

防火墙只需对外开放 SSH、HTTP 和 HTTPS，不要开放 9010 端口：

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
sudo ufw status
```

启用防火墙前，应确认当前 SSH 端口和管理来源已经正确放行，以免失去服务器连接。

## 9. 部署后配置

首次访问页面后：

1. 打开右上角“AI 设置”，填写模型供应商、模型 ID、Base URL 和 API Key。
2. 测试模型连接，通过后保存并启用。
3. 打开“行情设置”，测试实时行情，通过后保存并启用公网行情。
4. 新建会话，验证普通回答、实时行情、K 线、新闻和 SSE 流式输出。

模型配置和加密后的 API Key 保存在 `backend/data/stock_agent.db` 中。

## 10. 日常运维

查看状态和日志：

```bash
sudo systemctl status stock-agent --no-pager
sudo journalctl -u stock-agent -n 200 --no-pager
sudo journalctl -u stock-agent -f
sudo tail -f /var/log/nginx/access.log /var/log/nginx/error.log
```

重启服务：

```bash
sudo systemctl restart stock-agent
sudo systemctl reload nginx
```

健康检查：

```bash
curl --fail http://127.0.0.1:9010/api/v1/health/live
curl --fail http://127.0.0.1:9010/api/v1/health/ready
curl --fail https://stock.example.com/api/v1/health/live
```

如果启用了 Basic Auth，公网健康检查需要增加 `-u 用户名`，然后按提示输入密码。

## 11. 备份与恢复

至少备份以下内容：

- `/opt/stock-agent/backend/data/stock_agent.db`
- `/opt/stock-agent/backend/.env`

SQLite 运行时可能同时存在 `-wal` 和 `-shm` 文件，不建议直接复制正在写入的数据库。使用 SQLite 在线备份接口生成一致性备份：

```bash
sudo install -d -o stockagent -g stockagent -m 700 /var/backups/stock-agent
sudo -u stockagent /opt/stock-agent/.venv/bin/python - <<'PY'
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

source = sqlite3.connect('/opt/stock-agent/backend/data/stock_agent.db')
target_path = Path('/var/backups/stock-agent') / (
    'stock_agent_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.db'
)
target = sqlite3.connect(target_path)
with target:
    source.backup(target)
target.close()
source.close()
print(target_path)
PY
sudo cp --preserve=mode,timestamps /opt/stock-agent/backend/.env /var/backups/stock-agent/backend.env
sudo chmod -R go-rwx /var/backups/stock-agent
```

恢复前先停止服务，并保留当前数据库副本：

```bash
sudo systemctl stop stock-agent
sudo cp /opt/stock-agent/backend/data/stock_agent.db /opt/stock-agent/backend/data/stock_agent.db.before-restore
sudo cp /var/backups/stock-agent/stock_agent_YYYYMMDDTHHMMSSZ.db /opt/stock-agent/backend/data/stock_agent.db
sudo chown stockagent:stockagent /opt/stock-agent/backend/data/stock_agent.db
sudo systemctl start stock-agent
```

恢复 `.env` 时必须确保 `APP_ENCRYPTION_KEY` 与创建数据库中加密 API Key 时使用的密钥一致。

## 12. 升级应用

升级前先备份数据库和 `.env`。然后更新代码、依赖和前端产物：

```bash
cd /opt/stock-agent
git pull --ff-only

.venv/bin/python -m pip install --upgrade ./backend

cd frontend
npm ci
npm run test
npm run build

sudo chown -R stockagent:stockagent /opt/stock-agent
sudo systemctl restart stock-agent
sudo nginx -t && sudo systemctl reload nginx

curl --fail http://127.0.0.1:9010/api/v1/health/ready
```

不要覆盖服务器上的 `backend/.env` 和 `backend/data`。当前项目尚未集成 Alembic；应用启动时使用 SQLAlchemy `create_all` 补建缺失表，但不会自动执行复杂字段迁移。涉及数据库结构变更的版本应先阅读对应发布说明并制作可恢复备份。

## 13. 常见故障

### systemd 启动失败

```bash
sudo journalctl -u stock-agent -n 200 --no-pager
sudo -u stockagent bash -lc 'cd /opt/stock-agent/backend && /opt/stock-agent/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 9010'
```

重点检查 Python 版本、依赖安装、`.env` 权限、`APP_ENCRYPTION_KEY` 和 `backend/data` 写权限。

### Nginx 返回 502

```bash
sudo systemctl status stock-agent --no-pager
curl -v http://127.0.0.1:9010/api/v1/health/live
sudo tail -n 100 /var/log/nginx/error.log
```

### 页面能打开，但请求返回 404

确认前端请求路径以 `/api` 开头，并确认 Nginx 的 `location /api/` 中 `proxy_pass` 没有在端口后额外添加 `/`。

### 流式回答中断或长时间无输出

确认 Nginx 配置包含 `proxy_buffering off`、`proxy_read_timeout 3600s`，并且没有在 CDN 或上层反向代理中启用响应缓冲或过短的空闲超时。

### 修改 `.env` 后没有生效

生产服务不启用热重载。修改配置后执行：

```bash
sudo systemctl restart stock-agent
```

### 数据库只读或无法创建

```bash
sudo chown -R stockagent:stockagent /opt/stock-agent/backend/data
sudo chmod 750 /opt/stock-agent/backend/data
sudo systemctl restart stock-agent
```

## 14. 上线检查清单

- [ ] Python 和 Node.js 版本符合要求
- [ ] `APP_ENV=production`
- [ ] 已生成并安全备份独立的 `APP_ENCRYPTION_KEY`
- [ ] 后端仅监听 `127.0.0.1:9010`
- [ ] Uvicorn 保持单 Worker
- [ ] Nginx 已关闭 SSE 代理缓冲
- [ ] 公网部署已启用 HTTPS 和访问控制
- [ ] 防火墙未对公网开放 9010
- [ ] 模型及行情连接测试通过
- [ ] SQLite 与 `.env` 已纳入定期备份
- [ ] 已验证数据库恢复流程
