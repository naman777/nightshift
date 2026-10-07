#!/usr/bin/env bash
# Deploys one commit of main to the demo host. The GitHub Actions deploy key is pinned to this script in
# ~/.ssh/authorized_keys (command="/bin/bash /opt/nightshift/ops/ci-deploy.sh",restrict), so that key can do nothing
# else; the commit SHA arrives as SSH_ORIGINAL_COMMAND. By hand:  bash ops/ci-deploy.sh <sha>
set -Eeuo pipefail

repository=/opt/nightshift
revision="${SSH_ORIGINAL_COMMAND:-${1:-}}"

if [[ ! "$revision" =~ ^[0-9a-f]{40}$ ]]; then
  echo 'Expected a 40-character Git commit SHA.' >&2
  exit 2
fi

exec 9>/tmp/nightshift-deploy.lock
flock -w 900 9

cd "$repository"
if [[ ! -f .env.production ]]; then
  echo 'Production environment file is missing.' >&2
  exit 1
fi
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo 'Production checkout has local changes; deployment stopped.' >&2
  exit 1
fi

git fetch --no-tags origin main
current_main="$(git rev-parse FETCH_HEAD)"
if [[ "$current_main" != "$revision" ]]; then
  echo "Skipping superseded commit $revision; main is $current_main."
  exit 0
fi

previous="$(git rev-parse HEAD)"
compose=(docker compose -p nightshift --env-file .env.production -f docker-compose.prod.yml)

# Each step returns 1 on failure; `set -e` does not apply inside an `if` condition.
# The build is niced: this VM also serves other projects.
release() {
  git checkout --quiet --detach "$1" || return 1
  "${compose[@]}" config --quiet || return 1
  nice -n 10 "${compose[@]}" build || return 1
  "${compose[@]}" up -d --no-build --remove-orphans --wait --wait-timeout 180 || return 1
}

if ! release "$revision"; then
  echo "Deploy of $revision failed; rolling back to $previous." >&2
  # The tree was clean before the checkout, so this discards nothing of value.
  git checkout --quiet --force --detach "$previous"
  nice -n 10 "${compose[@]}" build
  "${compose[@]}" up -d --no-build --remove-orphans --wait --wait-timeout 180
  "${compose[@]}" ps
  echo "Rolled back to $previous." >&2
  exit 1
fi

"${compose[@]}" ps
docker image prune -f >/dev/null   # dangling layers from the previous build only
echo "Deployed $revision to https://nightshift.naman.sbs"
