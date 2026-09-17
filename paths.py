"""Single-binary path layout.

- BUNDLE_DIR: read-only files shipped INSIDE the one binary
  (PyInstaller _MEIPASS when frozen, source dir when running from source).
- DATA_DIR: writable user folder for uploads + saved templates
  (so the .exe never needs sidecar files or admin rights).

Rule #1: one .exe / one binary ships everything. No FFmpeg, no external
DLLs beside what cyndilib already bundles, no loose asset folders.
"""
from __future__ import annotations

import os
import sys

FROZEN = bool(getattr(sys, "frozen", False))

if FROZEN and hasattr(sys, "_MEIPASS"):
    BUNDLE_DIR = str(sys._MEIPASS)  # type: ignore[attr-defined]
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))


def _user_data_dir() -> str:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "QRReplace")
    # macOS / Linux
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Application Support", "QRReplace")
    return os.path.join(home, ".qrreplace")


if FROZEN:
    DATA_DIR = _user_data_dir()
else:
    DATA_DIR = os.path.dirname(os.path.abspath(__file__))

PUBLIC_DIR = os.path.join(BUNDLE_DIR, "public")
ASSET_DIR = os.path.join(BUNDLE_DIR, "assets")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
TEMPLATE_DIR = os.path.join(DATA_DIR, "templates")
AUTOSAVE = os.path.join(TEMPLATE_DIR, "autosave.json")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(TEMPLATE_DIR, exist_ok=True)
