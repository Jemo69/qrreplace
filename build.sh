#!/bin/sh
# Build the single QRReplace binary — everything inside, no sidecars.
set -e
cd "$(dirname "$0")"
pip install -r requirements.txt pyinstaller
pyinstaller qrreplace.spec --noconfirm
echo ""
echo "DONE: dist/QRReplace  (single binary — run it, editor opens in browser)"
