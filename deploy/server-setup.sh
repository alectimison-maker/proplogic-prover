#!/bin/bash
# 服务器端安装脚本：在服务器 SSH 会话中执行
# 假设已上传 /tmp/logic-project/ 目录

set -e
echo "=== 命题逻辑系统 服务器安装 ==="

# ── 1. 创建目录 ────────────────────────────────────────
echo "[1/7] 创建目录..."
mkdir -p /opt/logic-api /var/www/logic.jazzzy.cn

# ── 2. 安装 Python 依赖 ─────────────────────────────────
echo "[2/7] 安装 Python 虚拟环境..."
apt-get install -y python3-venv python3-pip 2>/dev/null
python3 -m venv /opt/logic-api/venv
/opt/logic-api/venv/bin/pip install --upgrade pip -q
/opt/logic-api/venv/bin/pip install -r /tmp/logic-project/backend/requirements.txt -q
echo "Python 依赖安装完成"

# ── 3. 复制后端文件 ─────────────────────────────────────
echo "[3/7] 部署后端文件..."
cp -r /tmp/logic-project/backend/* /opt/logic-api/
chown -R www-data:www-data /opt/logic-api/
echo "后端文件部署完成"

# ── 4. 复制前端文件 ─────────────────────────────────────
echo "[4/7] 部署前端文件..."
cp -r /tmp/logic-project/frontend/* /var/www/logic.jazzzy.cn/
chown -R www-data:www-data /var/www/logic.jazzzy.cn/
echo "前端文件部署完成"

# ── 5. 安装 Nginx 配置 ──────────────────────────────────
echo "[5/7] 配置 Nginx..."
cp /tmp/logic-project/deploy/nginx-logic.conf /etc/nginx/sites-available/logic.jazzzy.cn
ln -sf /etc/nginx/sites-available/logic.jazzzy.cn /etc/nginx/sites-enabled/
nginx -t && echo "Nginx 配置验证通过"

# ── 6. 申请 SSL 证书 ────────────────────────────────────
echo "[6/7] 申请 SSL 证书（需要域名已解析到服务器）..."
apt-get install -y certbot python3-certbot-nginx 2>/dev/null
certbot --nginx -d logic.jazzzy.cn --non-interactive --agree-tos \
  -m webmaster@jazzzy.cn --redirect || echo "⚠️  SSL 申请失败，请手动执行 certbot"

systemctl reload nginx

# ── 7. 安装 systemd 服务 ────────────────────────────────
echo "[7/7] 安装 systemd 服务..."
cp /tmp/logic-project/deploy/logic-api.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable logic-api
systemctl start logic-api

sleep 2
systemctl status logic-api --no-pager -l | head -20

echo ""
echo "=== 安装完成 ==="
echo "⚠️  请设置 ANTHROPIC_API_KEY:"
echo "   编辑 /etc/systemd/system/logic-api.service"
echo "   将 PLACEHOLDER_API_KEY 替换为实际 API Key"
echo "   然后执行: systemctl daemon-reload && systemctl restart logic-api"
echo ""
echo "验证:"
echo "  curl http://.../health"
echo "  curl -I https://logic.jazzzy.cn"
