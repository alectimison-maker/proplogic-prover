#!/bin/bash
# ═══════════════════════════════════════════════════════════
# 命题逻辑自然推理系统 - 服务器一键安装脚本
# 在服务器上以 root 或 sudo 权限执行
# 前置：已将 logic-project/ 上传至 /tmp/logic-project/
# ═══════════════════════════════════════════════════════════

set -e
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log() { echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err() { echo -e "${RED}[ERR]${NC} $*"; exit 1; }

BACKEND_SRC="/tmp/logic-project/backend"
FRONTEND_SRC="/tmp/logic-project/frontend"
BACKEND_DST="/opt/logic-api"
FRONTEND_DST="/var/www/logic.jazzzy.cn"
SERVICE_FILE="/etc/systemd/system/logic-api.service"
NGINX_CONF="/etc/nginx/sites-available/logic.jazzzy.cn"

# ── 1. 检查环境 ────────────────────────────────────────
log "[1/8] 检查环境..."
command -v python3 >/dev/null || err "需要 python3"
command -v nginx >/dev/null || err "需要 nginx"

# ── 2. 创建目录 ────────────────────────────────────────
log "[2/8] 创建目录..."
mkdir -p "$BACKEND_DST" "$FRONTEND_DST"

# ── 3. 部署后端 ────────────────────────────────────────
log "[3/8] 部署后端..."
cp -r "$BACKEND_SRC"/. "$BACKEND_DST/"
chown -R www-data:www-data "$BACKEND_DST"

# 虚拟环境
if [ ! -f "$BACKEND_DST/venv/bin/python" ]; then
    log "  创建虚拟环境..."
    python3 -m venv "$BACKEND_DST/venv"
fi
log "  安装 Python 依赖..."
"$BACKEND_DST/venv/bin/pip" install -q --upgrade pip
"$BACKEND_DST/venv/bin/pip" install -q -r "$BACKEND_DST/requirements.txt"
log "  后端依赖安装完成"

# ── 4. 部署前端 ────────────────────────────────────────
log "[4/8] 部署前端..."
cp -r "$FRONTEND_SRC"/. "$FRONTEND_DST/"
chown -R www-data:www-data "$FRONTEND_DST"

# ── 5. Nginx 配置 ──────────────────────────────────────
log "[5/8] 配置 Nginx..."

# 临时 HTTP-only 配置（SSL 申请前用）
cat > "$NGINX_CONF" << 'NGINX_CONF_EOF'
server {
    listen 80;
    server_name logic.jazzzy.cn;

    root /var/www/logic.jazzzy.cn;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8081/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 30s;
    }
}
NGINX_CONF_EOF

ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/logic.jazzzy.cn
nginx -t || err "Nginx 配置错误"
systemctl reload nginx
log "  Nginx 配置完成（HTTP，SSL 稍后申请）"

# ── 6. systemd 服务 ────────────────────────────────────
log "[6/8] 安装 systemd 服务..."
cat > "$SERVICE_FILE" << 'SERVICE_EOF'
[Unit]
Description=命题逻辑自然推理系统 API
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/logic-api
ExecStart=/opt/logic-api/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8081 --workers 2
Restart=on-failure
RestartSec=5s
Environment=ANTHROPIC_API_KEY=PLACEHOLDER_API_KEY
MemoryLimit=300M

StandardOutput=journal
StandardError=journal
SyslogIdentifier=logic-api

[Install]
WantedBy=multi-user.target
SERVICE_EOF

systemctl daemon-reload
systemctl enable logic-api
systemctl restart logic-api

sleep 3
if systemctl is-active logic-api >/dev/null 2>&1; then
    log "  API 服务启动成功"
else
    warn "  API 服务启动失败，查看日志："
    journalctl -u logic-api -n 20 --no-pager
fi

# ── 7. 健康检查 ────────────────────────────────────────
log "[7/8] 健康检查..."
sleep 2
HEALTH=$(curl -s http://127.0.0.1:8081/health 2>/dev/null)
if echo "$HEALTH" | grep -q "ok"; then
    log "  API 健康检查通过：$HEALTH"
else
    warn "  API 健康检查失败，响应：$HEALTH"
fi

# ── 8. SSL 证书 ────────────────────────────────────────
log "[8/8] 申请 SSL 证书..."
apt-get install -y certbot python3-certbot-nginx -q 2>/dev/null
certbot --nginx -d logic.jazzzy.cn \
    --non-interactive --agree-tos \
    -m admin@jazzzy.cn --redirect \
    2>&1 || warn "SSL 申请失败，请确认域名 logic.jazzzy.cn 已解析到服务器IP"

# ── 完成 ───────────────────────────────────────────────
echo ""
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "${GREEN} 安装完成！${NC}"
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo ""
echo "⚠️  重要：设置 ANTHROPIC_API_KEY："
echo "   sudo sed -i 's/PLACEHOLDER_API_KEY/你的实际APIKey/' $SERVICE_FILE"
echo "   sudo systemctl daemon-reload && sudo systemctl restart logic-api"
echo ""
echo "访问地址（SSL 成功后）："
echo "  https://logic.jazzzy.cn"
echo ""
echo "验证命令："
echo "  curl http://127.0.0.1:8081/health"
echo "  curl http://127.0.0.1:8081/exercises"
echo "  systemctl status logic-api"
