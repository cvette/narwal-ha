#!/usr/bin/env bash
# Run the full test suite (protocol + Home Assistant integration) on Linux.
# Home Assistant does not run natively on Windows; from Windows use WSL:
#   wsl.exe -e bash /mnt/e/narwal-ha/scripts/test-ha.sh [pytest args]
# The venv lives on the Linux filesystem (fast) and is created on first run.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${NARWAL_HA_VENV:-$HOME/narwal-ha-venv}"
UV="${UV:-$(command -v uv || echo "$HOME/uvboot/bin/uv")}"

if [ ! -x "$VENV/bin/python" ]; then
  "$UV" venv --python 3.14 "$VENV"
  VIRTUAL_ENV="$VENV" "$UV" pip install pytest-homeassistant-custom-component
fi

cd "$REPO"
exec "$VENV/bin/python" -m pytest -p no:cacheprovider "$@"
