# -*- mode: python ; coding: utf-8 -*-
"""QRReplace — ONE binary. Desktop companion + web editor + NDI sender.

Entry is app.py (cute Tk window for the local operator) which embeds the
FastAPI backend, so the web editor stays reachable over the network.

Build:  pyinstaller qrreplace.spec   (or build.ps1 / build.sh)
Output: dist/QRReplace(.exe) — double-click, desktop window opens
        (+ web editor opens in the browser, LAN-ready).
"""
import os
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None

# cyndilib ships a native NDI lib — bundle every binary it needs.
ndi_binaries = []
try:
    ndi_binaries = collect_dynamic_libs("cyndilib")
except Exception:
    pass
try:
    ndi_datas = collect_data_files("cyndilib")
except Exception:
    ndi_datas = []

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=ndi_binaries,
    datas=[
        ("public", "public"),     # editor UI (HTML/CSS/JS)
        ("assets", "assets"),     # built-in backgrounds
    ] + ndi_datas,
    hiddenimports=[
        "uvicorn", "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
        "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan", "uvicorn.lifespan.on",
        "fastapi", "starlette", "pydantic", "multipart",
        "PIL", "numpy", "qrcode", "cyndilib",
        "paths", "renderer", "ndi_sender", "presets", "server",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["pyi_rth_ndi.py"],
    excludes=["tkinter", "matplotlib", "scipy", "pandas", "pytest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="QRReplace",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # windowed app: no console popup on Windows
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
# macOS: wrap the one-file exe as QRReplace.app (no-op on Win/Linux),
# so the CI can ship a single QRReplace-mac.dmg.
app = BUNDLE(
    exe,
    name="QRReplace.app",
    icon=None,
    bundle_identifier="com.qrreplace.app",
    info_plist={"NSHighResolutionCapable": "True"},
)
