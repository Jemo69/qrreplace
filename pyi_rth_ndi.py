"""PyInstaller runtime hook: make the bundled NDI native lib findable.

cyndilib loads libndi via cython; when frozen into one file, the DLL/.so
sits in sys._MEIPASS. Adding it to the search path here keeps the single
binary working with zero sidecar files.
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
                if hasattr(os, "add_dll_directory") and os.path.isdir(p):
                    try:
                        os.add_dll_directory(p)
                    except Exception:
                        pass
                if p not in sys.path:
                    sys.path.insert(0, p)
except Exception:
    pass
