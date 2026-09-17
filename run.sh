#!/bin/sh
cd "$(dirname "$0")"
pip install -r requirements.txt
PORT=${PORT:-3200} python3 server.py
