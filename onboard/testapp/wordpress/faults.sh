#!/usr/bin/env bash
# Faults for the WordPress target. Usage: faults.sh <fault> inject|revert
#   db_down       stop mariadb                              -> cause: MariaDB service down (classic WordPress "error establishing a database connection")
#   bad_db_creds  wp-config.php commit sets the wrong DB password -> cause: that config commit
#   fpm_starved   php-fpm pm.max_children cut to 1, then load -> cause: that config commit (capacity/exhaustion)
#   disk_full     fill the filesystem WordPress writes to     -> cause: disk full (uploads/cache dir)
set -uo pipefail
APP=~/wordpress
fault="${1:?fault}"; action="${2:?inject|revert}"
cd "$APP"
PHPFPM_UNIT=$(systemctl list-units --type=service --no-legend 'php*-fpm.service' | awk '{print $1}' | head -1)

case "$fault:$action" in
  db_down:inject)   sudo -n systemctl stop mariadb ;;
  db_down:revert)   sudo -n systemctl start mariadb ;;

  bad_db_creds:inject)
    sed -i "s/define('DB_PASSWORD', '.*');/define('DB_PASSWORD', 'wrong-password-typo');/" wp-config.php
    git commit -qam "chore: rotate db credential (typo in new password)" ;;
  bad_db_creds:revert) git revert --no-edit HEAD >/dev/null ;;

  fpm_starved:inject)
    # pm.max_children=1 alone leaves the default min/max_spare_servers (1/3) > max_children, which php-fpm refuses to start with
    # (status 78/CONFIG) -- pin every pm.* value together so the pool is valid but starved to a single worker. A one-off burst of
    # requests finishes in under a second (too short for the alert's `for:` window), so keep 4 concurrent clients hammering the
    # single worker in the background until revert kills them -- SUSTAINED pressure, not a quick spike.
    POOL=$(sudo -n find /etc/php -name "www.conf" | head -1)
    sudo -n sed -i -e 's/^pm.max_children = .*/pm.max_children = 1/' -e 's/^pm.start_servers = .*/pm.start_servers = 1/' \
                    -e 's/^pm.min_spare_servers = .*/pm.min_spare_servers = 1/' -e 's/^pm.max_spare_servers = .*/pm.max_spare_servers = 1/' "$POOL"
    sudo -n systemctl restart "$PHPFPM_UNIT"
    for i in $(seq 1 25); do
      nohup bash -c 'while true; do curl -s -m5 "http://127.0.0.1:8200/" >/dev/null; done' >/dev/null 2>&1 &
      echo $! >> /tmp/nightshift_fpm_load.pids
    done ;;
  fpm_starved:revert)
    xargs -r kill < /tmp/nightshift_fpm_load.pids 2>/dev/null; rm -f /tmp/nightshift_fpm_load.pids
    pkill -f 'curl -s -m5 http://127.0.0.1:8200' 2>/dev/null
    POOL=$(sudo -n find /etc/php -name "www.conf" | head -1)
    sudo -n sed -i -e 's/^pm.max_children = .*/pm.max_children = 5/' -e 's/^pm.start_servers = .*/pm.start_servers = 2/' \
                    -e 's/^pm.min_spare_servers = .*/pm.min_spare_servers = 1/' -e 's/^pm.max_spare_servers = .*/pm.max_spare_servers = 3/' "$POOL"
    sudo -n systemctl restart "$PHPFPM_UNIT" ;;

  # fills only the dedicated 200M uploads loopback volume (see setup.sh), never the host's real disk; uploads/ is owned by
  # www-data (not the ubuntu user running this script), so write as www-data
  disk_full:inject)  sudo -n -u www-data dd if=/dev/zero of="$APP/wp-content/uploads/filler" bs=1M count=165 2>&1 | tail -3 ;;
  disk_full:revert)  sudo -n -u www-data rm -f "$APP/wp-content/uploads/filler" ;;

  *) echo "unknown: $fault $action" >&2; exit 2 ;;
esac
echo "$fault $action ok"
