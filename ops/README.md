# Demo deployment

The public demo (https://nightshift.naman.sbs, https://nightshift.namankundra.com) is `docker-compose.prod.yml`: the
gateway on simulated backends plus the dashboard, i.e. what `python start.py` runs locally.

It lives in `/opt/nightshift` on a VM shared with other projects:

* Nothing is published on the host. The VM's Caddy belongs to the Foreman stack; the Nightshift site block is in
  Foreman's `deploy/Caddyfile` and proxies to `nightshift-dashboard:3000` over the `foreman-production_default` network.
* The gateway is reachable only from the dashboard container, which adds the bearer token server-side.
* Incident history is SQLite in the `nightshift_gateway_data` volume.

## Deploys

Every push to `main` runs `.github/workflows/deploy.yml`, which SSHes to the host with a key that can only run
`ops/ci-deploy.sh <sha>`: fetch, build, `up --wait` on the health checks, roll back to the previous commit on failure.

## Host setup (once)

```bash
sudo install -d -o "$USER" -g "$USER" /opt/nightshift
git clone https://github.com/naman777/nightshift.git /opt/nightshift
cd /opt/nightshift
(umask 077; echo "NIGHTSHIFT_API_TOKEN=$(openssl rand -hex 32)" > .env.production)
# optional, enables the "real LLM" option for every visitor (it spends your key): echo OPENAI_API_KEY=... >> .env.production
# real-model runs are capped at 5 per visitor and 200 in total per UTC day; to change:
#   echo NIGHTSHIFT_DEMO_LLM_PER_VISITOR=3 >> .env.production; echo NIGHTSHIFT_DEMO_LLM_PER_DAY=100 >> .env.production
bash ops/ci-deploy.sh "$(git rev-parse origin/main)"
```

Then add the deploy key's public half to `~/.ssh/authorized_keys` as
`command="/bin/bash /opt/nightshift/ops/ci-deploy.sh",restrict ssh-ed25519 ...` and its private half to the repository
secret `NIGHTSHIFT_DEPLOY_SSH_KEY`. `.github/demo_known_hosts` pins the host key.
