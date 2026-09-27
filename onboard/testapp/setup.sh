#!/usr/bin/env bash
# Deploys the shop API on the host: nginx :80 -> gunicorn 127.0.0.1:5000 -> Flask/SQLite, config + nginx conf in a git repo (~/shop) with some history.
# Run on the EC2 host as the normal user (needs sudo). Uses no Docker.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP=~/shop
sudo -n apt-get install -y -q nginx >/tmp/apt-nginx.log 2>&1 || { tail -5 /tmp/apt-nginx.log; exit 1; }
mkdir -p "$APP/config" "$APP/nginx"
[ -d "$APP/.venv" ] || python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install -q flask gunicorn
cd "$APP"
[ -d .git ] || { git init -q; git config user.name "shop-dev"; git config user.email "dev@example.invalid"; }
if ! git log >/dev/null 2>&1; then
  cp "$HERE/app.py" app.py
  echo '{"db_timeout_ms": 2000, "slow_ms": 0}' > config/app.json
  printf 'server {\n  listen 80;\n  location / {\n    proxy_pass http://127.0.0.1:5000;\n    proxy_read_timeout 10s;\n  }\n}\n' > nginx/shop.conf
  printf '.venv/\nshop.db\n__pycache__/\n' > .gitignore
  git add -A && git commit -q -m "initial shop api"
  echo '{"db_timeout_ms": 2500, "slow_ms": 0}' > config/app.json && git commit -qam "config: raise db timeout to 2500ms"
  sed -i 's/proxy_read_timeout 10s/proxy_read_timeout 15s/' nginx/shop.conf && git commit -qam "nginx: allow slower upstream responses"
fi
sudo -n tee /etc/systemd/system/shop-api.service >/dev/null <<EOF
[Unit]
Description=Shop API (gunicorn)
After=network.target
[Service]
User=$USER
WorkingDirectory=$APP
ExecStart=$APP/.venv/bin/gunicorn --workers 2 --bind 127.0.0.1:5000 app:app
Restart=on-failure
RestartSec=45
SyslogIdentifier=shop-api
[Install]
WantedBy=multi-user.target
EOF
sudo -n ln -sf "$APP/nginx/shop.conf" /etc/nginx/conf.d/shop.conf
sudo -n rm -f /etc/nginx/sites-enabled/default
sudo -n nginx -t
sudo -n systemctl daemon-reload
sudo -n systemctl enable --now shop-api.service
sudo -n systemctl enable nginx && sudo -n systemctl restart nginx
sleep 2
for i in 1 2 3; do curl -s -X POST localhost/orders -H 'content-type: application/json' -d '{"item":"book","qty":2}' >/dev/null; done
curl -s -m3 localhost/ ; echo
git log --oneline | cat
