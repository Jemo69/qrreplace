#!/bin/sh
cd "$(dirname "$0")"
if command -v uv >/dev/null 2>&1; then
  PORT=${PORT:-3200} uv run server.py
else
  pip install -r requirements.txt
  PORT=${PORT:-3200} python3 server.py
fi
