#!/usr/bin/env bash
# Deploys real WordPress (from wordpress.org, not a demo stub) on: nginx (new vhost :8200) -> php-fpm -> WordPress (PHP) -> MariaDB.
# wp-config.php and the nginx vhost are tracked in a git repo (~/wordpress) with commit history, matching how a real deploy is managed.
set -euo pipefail
APP=~/wordpress
PORT=8200
DB=wordpress
DBUSER=wordpress
PASS_FILE=/var/lib/nightshift-wp-db-pass   # idempotent: reuse the same password across re-runs of this script, rather than
                                            # generating a new one that no longer matches the already-created DB user
DBPASS="$(sudo -n cat "$PASS_FILE" 2>/dev/null || true)"
[ -n "$DBPASS" ] || DBPASS="wp-$(openssl rand -hex 8)"

sudo -n apt-get install -y -q mariadb-server php-fpm php-mysql php-gd php-curl php-xml php-mbstring php-zip unzip >/tmp/apt-wp.log 2>&1 || { tail -15 /tmp/apt-wp.log; exit 1; }
sudo -n systemctl enable --now mariadb
sudo -n mysql -e "CREATE DATABASE IF NOT EXISTS $DB; CREATE USER IF NOT EXISTS '$DBUSER'@'localhost' IDENTIFIED BY '$DBPASS'; ALTER USER '$DBUSER'@'localhost' IDENTIFIED BY '$DBPASS'; GRANT ALL ON $DB.* TO '$DBUSER'@'localhost'; FLUSH PRIVILEGES;"
echo "$DBPASS" | sudo -n tee "$PASS_FILE" >/dev/null && sudo -n chmod 600 "$PASS_FILE"

chmod o+x "$HOME"   # www-data needs +x (traversal only, not read) on $HOME to reach $APP; nothing else in $HOME becomes readable
mkdir -p "$APP"
if [ ! -f "$APP/wp-load.php" ]; then
  curl -sL https://wordpress.org/latest.tar.gz -o /tmp/wp.tar.gz
  tar -xzf /tmp/wp.tar.gz -C /tmp
  cp -r /tmp/wordpress/. "$APP/"
  rm -rf /tmp/wordpress /tmp/wp.tar.gz
fi
cd "$APP"
[ -d .git ] || { git init -q; git config user.name "wp-dev"; git config user.email "dev@example.invalid"; printf 'wp-content/uploads/\nwp-content/cache/\n' > .gitignore; }

PHPFPM_SOCK=$(sudo -n find /run/php -name "php*-fpm.sock" | head -1)
cat > wp-config.php <<EOF
<?php
define('DB_NAME', '$DB');
define('DB_USER', '$DBUSER');
define('DB_PASSWORD', '$DBPASS');
define('DB_HOST', 'localhost');
define('DB_CHARSET', 'utf8');
define('DB_COLLATE', '');
\$table_prefix = 'wp_';
define('WP_DEBUG', false);
define('WP_MEMORY_LIMIT', '96M');
if (!defined('ABSPATH')) define('ABSPATH', __DIR__ . '/');
require_once ABSPATH . 'wp-settings.php';
EOF

mkdir -p nginx
cat > nginx/wordpress.conf <<EOF
server {
  listen $PORT;
  root $APP;
  index index.php;
  location / { try_files \$uri \$uri/ /index.php?\$args; }
  location ~ \.php\$ {
    fastcgi_pass unix:$PHPFPM_SOCK;
    fastcgi_index index.php;
    fastcgi_param SCRIPT_FILENAME \$document_root\$fastcgi_script_name;
    include fastcgi_params;
    fastcgi_read_timeout 10s;
  }
}
EOF
sudo -n ln -sf "$APP/nginx/wordpress.conf" /etc/nginx/conf.d/wordpress.conf
sudo -n nginx -t && sudo -n systemctl reload nginx

if ! git log >/dev/null 2>&1; then
  git add -A && git commit -q -m "initial WordPress install ($(php -v | head -1 | cut -d' ' -f1-2))"
fi

# install via WP-CLI (real WordPress install flow, not fixture data)
if [ ! -f /usr/local/bin/wp ]; then
  curl -sL https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar -o /tmp/wp-cli.phar
  sudo -n install -m 0755 /tmp/wp-cli.phar /usr/local/bin/wp
fi
if ! sudo -n -u www-data /usr/local/bin/wp core is-installed --path="$APP" 2>/dev/null; then
  sudo -n chown -R www-data:www-data "$APP/wp-content"
  sudo -n -u www-data /usr/local/bin/wp core install --path="$APP" --url="http://127.0.0.1:$PORT" \
    --title="Nightshift Test Site" --admin_user=admin --admin_password="admin-$(openssl rand -hex 4)" --admin_email="admin@example.invalid" --skip-email
  sudo -n -u www-data /usr/local/bin/wp post generate --path="$APP" --count=5
fi
cd "$APP" && git add -A && git commit -qm "wp-cli: site installed, 5 sample posts" --allow-empty >/dev/null

# uploads on its own small loopback filesystem, so the disk_full fault can't touch the host's real disk (which also holds
# MariaDB, Prometheus's TSDB and the live LB) — a dedicated, easily-filled volume for user uploads is realistic on its own.
UPLOADS_IMG=/var/lib/nightshift-wp-uploads.img
if [ ! -f "$UPLOADS_IMG" ]; then
  sudo -n fallocate -l 200M "$UPLOADS_IMG"
  sudo -n mkfs.ext4 -q "$UPLOADS_IMG"
fi
sudo -n mkdir -p "$APP/wp-content/uploads"
mountpoint -q "$APP/wp-content/uploads" || sudo -n mount -o loop "$UPLOADS_IMG" "$APP/wp-content/uploads"
grep -q "$UPLOADS_IMG" /etc/fstab || echo "$UPLOADS_IMG $APP/wp-content/uploads ext4 loop,noauto,x-systemd.automount 0 0" | sudo -n tee -a /etc/fstab >/dev/null
sudo -n chown www-data:www-data "$APP/wp-content/uploads"

echo "$DBPASS" > /tmp/.wp_db_pass_do_not_commit  # local only, used by faults.sh; never put in git
curl -s -m5 -o /dev/null -w "home page: %{http_code} in %{time_total}s\n" "http://127.0.0.1:$PORT/"
git log --oneline | cat
