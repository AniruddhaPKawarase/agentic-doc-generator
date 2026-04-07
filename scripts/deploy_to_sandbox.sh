#!/bin/bash
set -euo pipefail
VM_IP="54.197.189.113"
VM_USER="ubuntu"
PEM_KEY="../../ai_assistant_sandbox.pem"
VM_PATH="/home/ubuntu/chatbot/aniruddha/vcsai/construction-intelligence-agent"

echo "=== Deploying to sandbox VM ==="
scp -r -i "$PEM_KEY" -o StrictHostKeyChecking=no \
    . "${VM_USER}@${VM_IP}:${VM_PATH}/"

echo "=== Installing dependencies ==="
ssh -i "$PEM_KEY" "${VM_USER}@${VM_IP}" \
    "cd ${VM_PATH} && pip install -r requirements.txt"

echo "=== Restarting service ==="
ssh -i "$PEM_KEY" "${VM_USER}@${VM_IP}" \
    "sudo systemctl restart construction-agent && sleep 3 && sudo systemctl status construction-agent --no-pager"

echo "=== Health check ==="
ssh -i "$PEM_KEY" "${VM_USER}@${VM_IP}" \
    "curl -s http://localhost:8003/health"
echo ""
echo "=== Deploy complete ==="
