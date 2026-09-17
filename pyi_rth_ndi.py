"""PyInstaller runtime hook: make the bundled NDI native libs loadable.

cyndilib needs, at import time:
  * cyndilib.libs/*          (hashed libndi + avahi/dbus/... deps, found via
                              the extensions' $ORIGIN/../cyndilib.libs RPATH)
  * cyndilib/wrapper/bin/*   (dynloaded libndi copy)

Both are collected by the spec, but OS library search doesn't know about
sys._MEIPASS on its own. Belt-and-braces: pre-load every bundled NDI shared
library process-global, so extension imports resolve even if an RPATH or
resource-path lookup is imperfect inside the one-file bundle.

Everything is best-effort: if NDI can't load, the app still runs — the
backend reports preview-only mode instead of crashing (see ndi_sender.py).
"""
import os
import sys

try:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        os.environ.setdefault("NDI_RUNTIME_DIR", meipass)
        for sub in ("", "ndi", "lib"):
            p = os.path.join(meipass, sub) if sub else meipass
            if os.path.isdir(p):
                if hasattr(os, "add_dll_directory"):
                    try:
                        os.add_dll_directory(p)
                    except Exception:
                        pass
                if p not in sys.path:
                    sys.path.insert(0, p)
        # Pre-load bundled NDI shared libraries (two passes: deps first).
        try:
            import ctypes
            import glob
            cands = []
            for pat in ("cyndilib.libs/*", "cyndilib/wrapper/bin/*/*",
                        "cyndilib/wrapper/bin/*"):
                cands.extend(glob.glob(os.path.join(meipass, pat)))
            cands = sorted({c for c in cands if os.path.isfile(c)})
            mode = getattr(ctypes, "RTLD_GLOBAL", 0)
            for _ in range(2):
                for lib in cands:
                    try:
                        ctypes.CDLL(lib, mode=mode)
                    except Exception:
                        pass
        except Exception:
            pass
except Exception:
    pass
