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
sudo rsync -a "${DEPLOY}/" "${DEST}/"
sudo chown -R mlsops:mlsops "${DEST}"
cd "${DEST}"
./.venv/bin/pip install -r requirements.txt -q
# Headless scrape jobs need Chromium on this Playwright version (paths under ~/.cache/ms-playwright/).
./.venv/bin/python -m playwright install chromium
sudo systemctl restart mls-api.service
echo "---"
curl -s -S http://127.0.0.1:8000/health || true
echo ""
echo "Deploy merge finished. If curl failed, check: sudo systemctl status mls-api.service"
