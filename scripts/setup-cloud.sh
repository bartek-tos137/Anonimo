#!/usr/bin/env bash
set -euo pipefail
cd /workspace/Anonimo
export UV_CACHE_DIR=/workspace/.cache/uv
uv sync --locked --extra proxy
mkdir -p .local
if [ ! -f .local/policy.yaml ]; then
    cp policy.yaml .local/policy.yaml
fi
.venv/bin/python -m anonimo check-policy --policy .local/policy.yaml
