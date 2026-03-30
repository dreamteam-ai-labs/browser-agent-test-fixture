#!/usr/bin/env bash
# validate-deploy.sh — Clean install validation (same as Dockerfile)
#
# Creates a temporary venv, installs from pyproject.toml only,
# and validates the app import. If this passes, the Docker build will pass.
#
# Called by the factory loop as a quality gate between deployment-prep
# and Coolify deploy. NOT called by agents — this is infrastructure.
#
# Exit codes:
#   0 = validation passed
#   1 = validation failed (missing dependency)

set -euo pipefail

VENV_DIR="/tmp/deploy-check-$$"
PACKAGE="fixture"

cleanup() {
    rm -rf "$VENV_DIR"
}
trap cleanup EXIT

echo "=== Clean Install Validation ==="
echo "Creating temporary venv at $VENV_DIR..."
python3 -m venv "$VENV_DIR"

echo "Installing from pyproject.toml (pip install .)..."
"$VENV_DIR/bin/pip" install --quiet . 2>&1

echo "Validating import: from $PACKAGE.main import app..."
if "$VENV_DIR/bin/python" -c "from $PACKAGE.main import app; print('Import validation passed')"; then
    echo "=== PASSED ==="
    exit 0
else
    echo ""
    echo "=== FAILED ==="
    echo "A runtime dependency is missing from [project.dependencies] in pyproject.toml."
    echo "It may be in [project.optional-dependencies] or installed separately in the codespace."
    echo "Add the missing module to [project.dependencies] and re-run this script."
    exit 1
fi
