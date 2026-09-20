#!/bin/sh
# Build the single QRReplace binary — everything inside, no sidecars.
set -e
cd "$(dirname "$0")"
if command -v uv >/dev/null 2>&1; then
  uv run pyinstaller qrreplace.spec --noconfirm
else
  pip install -r requirements.txt pyinstaller
  pyinstaller qrreplace.spec --noconfirm
fi
echo ""
echo "DONE: dist/QRReplace  (single binary — run it, editor opens in browser)"
