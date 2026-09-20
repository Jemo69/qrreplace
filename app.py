"""QRReplace desktop companion — cute Tk UI for the local operator.

Runs the SAME backend as the web editor (uvicorn in a background thread),
so the web UI stays reachable over the network while this window gives the
person sitting at the machine:

  * live on-air preview (same pixels as the NDI feed)
  * big GO LIVE / STOP button + source name
  * design picker (saved templates) + 3 ready-made looks
  * quick-edit of the 2-3 things operators change most (QR link, title,
    subtitle) — applied live, even mid-broadcast
  * one click to open the full web editor locally or share its LAN address

Everything still ships in ONE binary (Tkinter is stdlib — zero new deps).
Run:  python3 app.py        (dev)
      dist/QRReplace(.exe)  (packaged — opens this window AND the web editor)
"""
from __future__ import annotations

import io
import json
import os
import queue
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

# In windowed mode (e.g. PyInstaller console=False or pythonw), sys.stdout
# and sys.stderr are None. Provide dummy streams so libraries (uvicorn,
# logging, etc.) that inspect stdout (e.g. .isatty()) or write to it do not crash.
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

PORT = int(os.environ.get("PORT", "3200"))
BASE = f"http://127.0.0.1:{PORT}"

# ---------------------------------------------------------------- API client
# stdlib only (urllib) so the frozen binary needs nothing extra.


class QrApi:
    def __init__(self, base: str = BASE, timeout: float = 6.0):
        self.base = base.rstrip("/")
        self.timeout = timeout

    def _req(self, method: str, path: str, body=None, raw: bool = False):
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                payload = r.read()
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8", "replace")[:200]
            except Exception:
                detail = str(e)
            raise RuntimeError(f"{method} {path}: HTTP {e.code} {detail}")
        except Exception as e:
            raise RuntimeError(f"{method} {path}: {e}")
        if raw:
            return payload
        try:
            return json.loads(payload.decode("utf-8"))
        except Exception:
            raise RuntimeError(f"{method} {path}: bad JSON response")

    # convenience wrappers -------------------------------------------------
    def status(self): return self._req("GET", "/api/status")
    def quick(self): return self._req("GET", "/api/quick")
    def set_quick(self, **kw): return self._req("POST", "/api/quick", kw)
    def set_live(self, **kw): return self._req("POST", "/api/live", kw)
    def templates(self): return self._req("GET", "/api/templates").get("templates", [])
    def load_template(self, name): return self._req("GET", "/api/templates/" + name)
    def apply_preset(self, name): return self._req("POST", "/api/presets/" + name)
    def network(self): return self._req("GET", "/api/system/network")
    def preview_png(self, w=480, h=270): return self._req("GET", f"/api/preview.png?w={w}&h={h}", raw=True)

    def wait_ready(self, tries: int = 60, delay: float = 0.5) -> bool:
        for _ in range(tries):
            try:
                self._req("GET", "/api/status")
                return True
            except Exception:
                time.sleep(delay)
        return False


# ---------------------------------------------------------------- backend
_uvicorn_server = None


def start_backend(port: int = PORT):
    """Run the FastAPI backend (web editor + NDI sender) in a daemon thread."""
    global _uvicorn_server
    import uvicorn
    import server as backend

    config = uvicorn.Config(
        backend.app,
        host="0.0.0.0",
        port=port,
        log_level="warning",
        use_colors=False,
    )
    _uvicorn_server = uvicorn.Server(config)
    t = threading.Thread(target=_uvicorn_server.run, daemon=True, name="uvicorn")
    t.start()
    return _uvicorn_server


def stop_backend():
    global _uvicorn_server
    try:
        if _uvicorn_server is not None:
            _uvicorn_server.should_exit = True
    except Exception:
        pass


# ---------------------------------------------------------------- Tk app

BG = "#0c0f16"
PANEL = "#141926"
PANEL2 = "#1a2133"
LINE = "#263049"
TXT = "#eef2fb"
MUT = "#9aa6c2"
ACC = "#f5b301"
OK = "#35d07f"
BAD = "#ff5d5d"
LIVE_RED = "#ff3b30"


class App:
    def __init__(self, root, api: QrApi):
        import tkinter as tk
        from tkinter import messagebox
        self.tk = tk
        self.msg = messagebox
        self.root = root
        self.api = api
        self.live = False
        self.status = {}
        self.inbox: queue.Queue = queue.Queue()

        root.title("QRReplace — NDI Lower-Third Studio")
        root.configure(bg=BG)
        root.geometry("600x860")
        root.minsize(540, 720)

        try:
            from paths import ASSET_DIR
            icon_path = os.path.join(ASSET_DIR, "icon.png")
            if os.path.exists(icon_path):
                from PIL import Image, ImageTk
                self._icon = ImageTk.PhotoImage(Image.open(icon_path).resize((32, 32)))
                root.iconphoto(True, self._icon)
        except Exception:
            pass

        self._build()
        self._refresh_all(first=True)
        self._poll()

    # -- widget helpers ----------------------------------------------------
    def _lbl(self, parent, text, fg=TXT, size=11, bold=False, **kw):
        import tkinter as tk
        return tk.Label(parent, text=text, bg=parent["bg"] if "bg" in parent.keys() else BG,
                        fg=fg, font=("Segoe UI", size, "bold" if bold else "normal"), **kw)

    def _card(self, parent, title):
        import tkinter as tk
        f = tk.Frame(parent, bg=PANEL, highlightbackground=LINE, highlightthickness=1,
                     padx=12, pady=10)
        self._lbl(f, title.upper(), fg=MUT, size=9, bold=True).pack(anchor="w", pady=(0, 8))
        f.pack(fill="x", padx=12, pady=6)
        return f

    def _btn(self, parent, text, cmd, bg=ACC, fg="#111111", size=11, **kw):
        import tkinter as tk
        return tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg,
                         activebackground=bg, activeforeground=fg,
                         font=("Segoe UI", size, "bold"), relief="flat",
                         padx=12, pady=8, cursor="hand2", **kw)

    # -- layout -------------------------------------------------------------
    def _build(self):
        import tkinter as tk
        # header
        head = tk.Frame(self.root, bg=BG, pady=10)
        head.pack(fill="x", padx=12)
        self._lbl(head, "◧ QRReplace", fg=ACC, size=16, bold=True).pack(side="left")
        self.status_lbl = self._lbl(head, "starting…", fg=MUT, size=11, bold=True)
        self.status_lbl.pack(side="right")

        # preview
        pv = self._card(self.root, "On-air preview — same pixels as NDI")
        self.preview_lbl = tk.Label(pv, bg="#07090e", width=480, height=270)
        self.preview_lbl.pack()
        self.sub_lbl = self._lbl(pv, "", fg=MUT, size=10)
        self.sub_lbl.pack(anchor="w", pady=(6, 0))

        # broadcast
        bc = self._card(self.root, "Broadcast")
        row = tk.Frame(bc, bg=PANEL)
        row.pack(fill="x")
        self._lbl(row, "Source name").pack(side="left")
        self.name_var = tk.StringVar(value="QRReplace")
        tk.Entry(row, textvariable=self.name_var, bg=PANEL2, fg=TXT,
                 insertbackground=TXT, relief="flat", width=24,
                 font=("Segoe UI", 11)).pack(side="left", padx=8, ipady=4)
        self.live_btn = self._btn(row, "●  GO LIVE", self.on_live, bg=LIVE_RED, fg="white", size=12)
        self.live_btn.pack(side="right")
        self.stats_lbl = self._lbl(bc, "", fg=MUT, size=10)
        self.stats_lbl.pack(anchor="w", pady=(8, 0))

        # quick edit — the 2-3 things operators change most
        q = self._card(self.root, "Quick change — updates live, even on air ✏️")
        self.qr_var = tk.StringVar()
        self.title_var = tk.StringVar()
        self.sub_var = tk.StringVar()
        for label, var in (("QR goes to (link)", self.qr_var),
                           ("Big title", self.title_var),
                           ("Smaller line", self.sub_var)):
            self._lbl(q, label, fg=MUT, size=10).pack(anchor="w")
            tk.Entry(q, textvariable=var, bg=PANEL2, fg=TXT, insertbackground=TXT,
                     relief="flat", font=("Segoe UI", 11)).pack(fill="x", pady=(0, 8), ipady=5)
        self._btn(q, "Apply to screen  →", self.on_quick, size=11).pack(anchor="e")

        # designs
        d = self._card(self.root, "Designs — pick a look")
        prow = tk.Frame(d, bg=PANEL)
        prow.pack(fill="x", pady=(0, 8))
        for key, emoji, label in (("giving", "⛪", "Giving"),
                                  ("wifi", "📶", "Wi-Fi"),
                                  ("announce", "📣", "News")):
            self._btn(prow, f"{emoji} {label}", lambda k=key: self.on_preset(k),
                      bg=PANEL2, fg=TXT, size=10).pack(side="left", expand=True, fill="x", padx=2)
        trow = tk.Frame(d, bg=PANEL)
        trow.pack(fill="x")
        self.tpl_list = tk.Listbox(trow, bg=PANEL2, fg=TXT, relief="flat",
                                   font=("Segoe UI", 11), height=3,
                                   selectbackground=ACC, selectforeground="#111111")
        self.tpl_list.pack(side="left", expand=True, fill="x")
        self.tpl_list.bind("<Double-Button-1>", lambda e: self.on_load_template())
        self._btn(trow, "Open", self.on_load_template, bg=PANEL2, fg=TXT, size=10).pack(side="left", padx=(8, 0))

        # web access
        w = self._card(self.root, "Full editor (this network)")
        wrow = tk.Frame(w, bg=PANEL)
        wrow.pack(fill="x")
        self._btn(wrow, "🌐 Open editor", self.on_open_web, bg=PANEL2, fg=TXT, size=10).pack(side="left")
        self._btn(wrow, "📋 Copy phone link", self.on_copy_link, bg=PANEL2, fg=TXT, size=10).pack(side="left", padx=8)
        self.lan_lbl = self._lbl(w, "", fg=MUT, size=10)
        self.lan_lbl.pack(anchor="w", pady=(8, 0))

        # footer settings
        f = tk.Frame(self.root, bg=BG)
        f.pack(fill="x", padx=12, pady=4)
        self._lbl(f, "Smoothness", fg=MUT, size=10).pack(side="left")
        self.fps_var = tk.StringVar(value="30")
        tk.OptionMenu(f, self.fps_var, "24", "30", "60").pack(side="left", padx=4)
        self._lbl(f, "Sharpness", fg=MUT, size=10).pack(side="left", padx=(10, 0))
        self.scale_var = tk.StringVar(value="1080p")
        tk.OptionMenu(f, self.scale_var, "1080p", "720p", "540p").pack(side="left", padx=4)

    # -- actions -------------------------------------------------------------
    def _work(self, fn):
        threading.Thread(target=self._guarded, args=(fn,), daemon=True).start()

    def _guarded(self, fn):
        try:
            fn()
        except Exception as e:
            self.inbox.put(("error", str(e)))

    def on_live(self):
        live = self.live
        name = self.name_var.get().strip() or "QRReplace"
        if live or self.msg.askyesno("Go live?",
                                     f"Broadcast “{name}” as NDI on this network?\n\n"
                                     "Find it in NDI Studio Monitor, OBS or vMix."):
            self._work(lambda: self._set_live(not live, name))

    def _set_live(self, live, name):
        s = self.api.set_live(live=live, ndiName=name, fps=int(self.fps_var.get()),
                              scale=self.scale_var.get(), alpha=True)
        self.inbox.put(("status", s))

    def on_quick(self):
        payload = {"qr": self.qr_var.get(), "title": self.title_var.get(),
                   "subtitle": self.sub_var.get()}
        note = "Update the screen now?" + (" (Viewers will see it instantly.)" if self.live else "")
        if self.msg.askyesno("Apply?", note):
            self._work(lambda: self._apply_quick(payload))

    def _apply_quick(self, payload):
        self.api.set_quick(**payload)
        self.inbox.put(("toast", "Screen updated ✓" + (" — on air now" if self.live else "")))

    def on_preset(self, key):
        label = {"giving": "Giving", "wifi": "Wi-Fi", "announce": "Announcement"}.get(key, key)
        if self.msg.askyesno("Change look?",
                             f"Switch the whole screen to “{label}”?" +
                             (" Viewers will see it instantly." if self.live else "")):
            self._work(lambda: (self.api.apply_preset(key), self.inbox.put(("reload", None))))

    def on_load_template(self):
        sel = self.tpl_list.curselection()
        if not sel:
            return
        name = self.tpl_list.get(sel[0])
        if name == "(no saved designs yet — use the web editor)":
            return
        if self.msg.askyesno("Open design?",
                             f"Load “{name}”?" + (" Viewers will see it instantly." if self.live else "")):
            self._work(lambda: (self.api.load_template(name), self.inbox.put(("reload", None))))

    def on_open_web(self):
        webbrowser.open(f"http://127.0.0.1:{PORT}")

    def on_copy_link(self):
        try:
            lan = self.api.network().get("urls", [""])[0]
        except Exception:
            lan = f"http://<this-pc>:{PORT}"
        self.root.clipboard_clear()
        self.root.clipboard_append(lan)
        self.inbox.put(("toast", f"Copied: {lan} — open it on any phone/laptop here"))

    # -- refresh --------------------------------------------------------------
    def _refresh_all(self, first=False):
        self._work(self._load_all)

    def _load_all(self):
        try:
            lan = self.api.network().get("urls", [])
        except Exception:
            lan = []
        try:
            tpl = self.api.templates()
        except Exception:
            tpl = []
        try:
            q = self.api.quick()
        except Exception:
            q = {}
        try:
            st = self.api.status()
        except Exception:
            st = {}
        self.inbox.put(("all", {"lan": lan, "templates": tpl, "quick": q, "status": st}))

    def _poll(self):
        # drain worker messages (Tk updates must happen in the main thread)
        try:
            while True:
                kind, payload = self.inbox.get_nowait()
                if kind == "error":
                    self.msg.showerror("QRReplace", payload)
                elif kind == "toast":
                    self.sub_lbl.config(text=payload)
                    self._toast_until = time.time() + 6
                elif kind == "status":
                    self._show_status(payload)
                elif kind == "reload":
                    self._work(self._load_all)
                    self._work(self._fetch_preview)
                elif kind == "all":
                    self._show_status(payload["status"])
                    self._show_meta(payload)
                elif kind == "preview":
                    self._show_preview(payload)
        except queue.Empty:
            pass
        self._work(self._fetch_status)
        self._work(self._fetch_preview)
        self.root.after(2000, self._poll)

    def _fetch_status(self):
        try:
            self.inbox.put(("status", self.api.status()))
        except Exception:
            pass

    def _fetch_preview(self):
        try:
            self.inbox.put(("preview", self.api.preview_png()))
        except Exception:
            pass

    def _show_preview(self, png: bytes):
        try:
            from PIL import Image, ImageTk
            img = Image.open(io.BytesIO(png)).convert("RGB").resize((480, 270))
            self._photo = ImageTk.PhotoImage(img)
            self.preview_lbl.config(image=self._photo)
        except Exception:
            pass

    def _show_status(self, s):
        if not s:
            return
        self.status = s
        self.live = bool(s.get("live"))
        if self.live:
            self.status_lbl.config(text="●  LIVE", fg=LIVE_RED)
            self.live_btn.config(text="■  STOP", bg="#2b3550", fg="white")
        else:
            self.status_lbl.config(text="○  OFF AIR", fg=MUT)
            self.live_btn.config(text="●  GO LIVE", bg=LIVE_RED, fg="white")
        if time.time() >= getattr(self, "_toast_until", 0):
            self.sub_lbl.config(
                text=(f"On air as “{s.get('ndiName')}” — this is what viewers see ↓"
                      if self.live else "Canvas preview — press GO LIVE to broadcast it ↓"))
        self.stats_lbl.config(
            text=f"Viewers: {s.get('connections', 0)}    "
                 f"Speed: {s.get('actualFps', 0) if self.live else '–'} fps    "
                 f"Frames: {s.get('framesSent', 0):,}" +
                 ("" if s.get("haveNdi") else "    (preview-only: NDI lib missing)"))

    def _show_meta(self, m):
        lan = (m.get("lan") or [""])[0]
        self.lan_lbl.config(text=f"On this PC: http://localhost:{PORT}"
                                 + (f"    •    On phones/laptops here: {lan}" if lan else ""))
        tpl = [t for t in (m.get("templates") or []) if t != "autosave"]
        self.tpl_list.delete(0, "end")
        if tpl:
            for t in tpl:
                self.tpl_list.insert("end", t)
        else:
            self.tpl_list.insert("end", "(no saved designs yet — use the web editor)")
        q = m.get("quick") or {}
        if q.get("qr") is not None:
            self.qr_var.set(q.get("qr", ""))
            self.title_var.set(q.get("title", ""))
            self.sub_var.set(q.get("subtitle", ""))


def main():
    import tkinter as tk
    from tkinter import messagebox

    api = QrApi()
    server = start_backend(PORT)
    if not api.wait_ready():
        messagebox.showerror("QRReplace",
                             f"The background service didn't start on port {PORT}.\n"
                             "Is another copy already running?")
        stop_backend()
        return 1

    root = tk.Tk()
    app = App(root, api)

    # open the web editor too (non-technical users expect *something* to appear)
    if "--no-browser" not in sys.argv:
        try:
            threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
        except Exception:
            pass

    def on_close():
        try:
            stop_backend()
        finally:
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    try:
        root.mainloop()
    finally:
        stop_backend()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
