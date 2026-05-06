#!/usr/bin/env bash
# Run ON the VM after rsync from your laptop copied code to ~/mls-automation-deploy/
# Usage: ssh mlsops@YOUR_DROPLET_IP   then:   sudo bash ~/mls-automation-deploy/infra/vm_merge_deploy.sh
#
# When you use `sudo`, HOME becomes /root — we resolve the real user's home via SUDO_USER
# so DEPLOY stays /home/mlsops/mls-automation-deploy (see MLS_DEPLOY_DIR override below).
set -euo pipefail

if [[ -n "${MLS_DEPLOY_DIR:-}" ]]; then
  DEPLOY="${MLS_DEPLOY_DIR}"
elif [[ -n "${SUDO_USER:-}" ]]; then
  DEPLOY="$(getent passwd "${SUDO_USER}" | cut -d: -f6)/mls-automation-deploy"
else
  DEPLOY="${HOME}/mls-automation-deploy"
fi

DEST="/opt/mls-automation"
if [[ ! -d "${DEPLOY}" ]]; then
  echo "Missing ${DEPLOY}. From your computer run rsync to this folder first." >&2
  exit 1
fi
# Never sync a laptop/deploy `.venv` over `/opt`: production keeps its own venv + pip upgrades below.
# (A symlink like `.venv -> /opt/.../venv` from tests causes "could not make way for new symlink".)
sudo rsync -a \
  --exclude '.venv' \
  --exclude '.env' \
  "${DEPLOY}/" "${DEST}/"
sudo chown -R mlsops:mlsops "${DEST}"
cd "${DEST}"
./.venv/bin/pip install -r requirements.txt -q
# Headless cron jobs run as `mlsops`; browsers must live under /home/mlsops/.cache/ms-playwright/
# (running install as root only populated /root/.cache and broke scrapes).
sudo -u mlsops -H bash -c 'cd /opt/mls-automation && ./.venv/bin/python -m playwright install chromium'
sudo systemctl restart mls-api.service
echo "---"
# Uvicorn needs a moment to bind; an immediate curl often fails even when the service is fine.
health_ok=0
for i in $(seq 1 30); do
  if out=$(curl -sfS --max-time 2 "http://127.0.0.1:8000/health" 2>/dev/null); then
    echo "$out"
    echo "Health check OK (~$((i - 1))s after restart)."
    health_ok=1
    break
  fi
  sleep 1
done
if [[ "${health_ok}" -ne 1 ]]; then
  echo "Health check did not succeed within 30s." >&2
  curl -sS --max-time 2 "http://127.0.0.1:8000/health" || echo "(curl still failing — see logs below)"
  echo "---"
  systemctl status mls-api.service --no-pager -l || true
fi
echo ""
echo "Deploy merge finished. If health failed, check logs: journalctl -u mls-api.service -n 50 --no-pager"
