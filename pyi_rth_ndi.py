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

# Windowed / noconsole PyInstaller executables have sys.stdout / sys.stderr set to None.
# Provide dummy streams so libraries (uvicorn, logging, etc.) that inspect stdout
# (e.g. .isatty()) or write to it do not crash.
class _NullWriter:
    def write(self, *args, **kwargs):
        pass

    def flush(self, *args, **kwargs):
        pass

    def isatty(self):
        return False


if sys.stdout is None:
    try:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        sys.stdout = _NullWriter()
if sys.stderr is None:
    try:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        sys.stderr = _NullWriter()
if sys.stdin is None:
    try:
        sys.stdin = open(os.devnull, "r", encoding="utf-8")
    except Exception:
        pass

try:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        os.environ.setdefault("NDI_RUNTIME_DIR", meipass)

        # On Windows, suppress the critical-error modal popup dialog if any dynamic library fails to load.
        if sys.platform == "win32":
            try:
                import ctypes
                # SEM_FAILCRITICALERRORS (0x0001) | SEM_NOGPFAULTERRORBOX (0x0002) | SEM_NOOPENFILEERRORBOX (0x8000)
                ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
            except Exception:
                pass

        for sub in ("", "ndi", "lib", "cyndilib", "cyndilib.libs",
                    os.path.join("cyndilib", "wrapper", "bin")):
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
                for c in glob.glob(os.path.join(meipass, pat)):
                    if os.path.isfile(c):
                        fn = os.path.basename(c).lower()
                        # CRITICAL: Only load shared libraries! Never pass .txt (e.g. Processing.NDI.Lib.Licenses.txt),
                        # .py, etc. to ctypes.CDLL, which causes Windows LoadLibrary error 0xc000012f (Bad Image).
                        if fn.endswith((".dll", ".so", ".dylib")) or ".so." in fn:
                            cands.append(c)
            cands = sorted(set(cands))
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

