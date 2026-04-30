#!/usr/bin/env bash
# Run ON the VM after rsync from your laptop copied code to ~/mls-automation-deploy/
# Usage: ssh mlsops@YOUR_DROPLET_IP   then:   bash ~/mls-automation-deploy/infra/vm_merge_deploy.sh
set -euo pipefail
DEPLOY="${HOME}/mls-automation-deploy"
DEST="/opt/mls-automation"
if [[ ! -d "${DEPLOY}" ]]; then
  echo "Missing ${DEPLOY}. From your computer run rsync to this folder first." >&2
  exit 1
fi
sudo rsync -a "${DEPLOY}/" "${DEST}/"
sudo chown -R mlsops:mlsops "${DEST}"
cd "${DEST}"
./.venv/bin/pip install -r requirements.txt -q
sudo systemctl restart mls-api.service
echo "---"
curl -s -S http://127.0.0.1:8000/health || true
echo ""
echo "Deploy merge finished. If curl failed, check: sudo systemctl status mls-api.service"
