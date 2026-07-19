#!/usr/bin/env bash
# Deploy / update the Data Gate on the target server.
#
# Idempotent and safe to run repeatedly. Runs ON the server (invoked either
# manually or piped in by the deploy workflow). It never touches the database —
# it only updates the installed tool.
#
# Usage:
#   ./scripts/deploy.sh [APP_DIR]
# APP_DIR defaults to $DATAGATE_HOME, then to the standard platform path.
set -euo pipefail

APP_DIR="${1:-${DATAGATE_HOME:-/opt/patrick-ai-factory/patrick-ai-factory-data-gate}}"

echo ">> Deploying Data Gate in ${APP_DIR}"
cd "${APP_DIR}"

# Refresh the code (repo must have been cloned once during first-time setup).
git fetch --all --prune
git reset --hard origin/main

# Ensure a Python 3.12 virtualenv exists, then install the package.
if [ ! -d .venv ]; then
    python3.12 -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -e .

# Smoke test: the console script must be runnable.
datagate --version
echo ">> Data Gate deployed successfully in ${APP_DIR}"
