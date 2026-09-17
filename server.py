"""QRReplace server — UI side + NDI side in one process.

UI side  : serves public/ editor, scene CRUD, uploads, templates, preview PNG.
NDI side : background thread renders the scene with Pillow and sends BGRA via cyndilib.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import socket
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Set

from fastapi import FastAPI, File, Header, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import renderer
from ndi_sender import NdiSender, HAVE_NDI
from paths import ASSET_DIR, AUTOSAVE, BUNDLE_DIR, DATA_DIR, PUBLIC_DIR, TEMPLATE_DIR, UPLOAD_DIR

# ---------------------------------------------------------------- scene store

def default_scene() -> Dict[str, Any]:
    """First-run scene — the shared Giving preset (single source: presets.py)."""
    from presets import giving
    return giving()


_scene_lock = threading.Lock()
_scene: Dict[str, Any] = default_scene()
_scene_version = 0

try:
    if os.path.exists(AUTOSAVE):
        with open(AUTOSAVE, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            if isinstance(loaded, dict) and "layers" in loaded:
                _scene = loaded
except Exception:
    pass


def get_scene() -> Dict[str, Any]:
    with _scene_lock:
        return json.loads(json.dumps(_scene))


def set_scene(data: Dict[str, Any]) -> int:
    global _scene, _scene_version
    with _scene_lock:
        # light validation / normalization
        layers = data.get("layers", [])
        if not isinstance(layers, list):
            raise ValueError("layers must be a list")
        for L in layers:
            if "id" not in L or not L["id"]:
                L["id"] = uuid.uuid4().hex[:8]
            L.setdefault("opacity", 1.0)
            L.setdefault("visible", True)
        _scene = data
        _scene_version += 1
        v = _scene_version
    try:
        with open(AUTOSAVE, "w", encoding="utf-8") as f:
            json.dump(_scene, f)
    except Exception:
        pass
    return v

# ---------------------------------------------------------------- NDI state

ndi = NdiSender()
ndi_lock = threading.Lock()
ndi_thread: Optional[threading.Thread] = None
ndi_stop = threading.Event()

ndi_state: Dict[str, Any] = {
    "live": False,
    "ndiName": "QRReplace",
    "fps": 30,
    "scale": "1080p",       # 1080p | 720p | 540p
    "alpha": True,          # keep transparency (alpha channel) in NDI feed
    "actualFps": 0.0,
    "framesSent": 0,
    "connections": 0,
    "startedAt": 0.0,
    "lastError": "",
}

SCALE_MAP = {"1080p": (1920, 1080), "720p": (1280, 720), "540p": (960, 540)}


def _ndi_loop():
    global ndi_thread
    w, h = SCALE_MAP.get(ndi_state.get("scale", "1080p"), (1920, 1080))
    fps = int(ndi_state.get("fps", 30) or 30)
    fps = max(10, min(60, fps))
    interval = 1.0 / fps
    count = 0
    t0 = time.time()
    last_status = 0.0
    try:
        ndi.open(ndi_state["ndiName"] or "QRReplace", w, h, fps)
    except Exception as e:
        ndi_state["lastError"] = str(e)
        ndi_state["live"] = False
        return
    ndi_state["startedAt"] = time.time()
    while not ndi_stop.is_set():
        tick = time.time()
        try:
            snap = get_scene()
            # alpha toggle: temporarily override canvas.alpha
            if not ndi_state.get("alpha", True):
                snap = dict(snap)
                snap["canvas"] = dict(snap.get("canvas", {}))
                snap["canvas"]["alpha"] = False
            img = renderer.render_scene(snap, w, h)
            buf = renderer.rgba_to_bgra_bytes(img)
            ndi.send(buf)
            count += 1
            ndi_state["framesSent"] = ndi.frames_sent
        except Exception as e:
            ndi_state["lastError"] = str(e)
        now = time.time()
        if now - t0 >= 1.0:
            ndi_state["actualFps"] = count / (now - t0)
            count = 0
            t0 = now
        if now - last_status > 0.5:
            try:
                ndi_state["connections"] = ndi.connections()
            except Exception:
                pass
            last_status = now
        elapsed = time.time() - tick
        time.sleep(max(0.001, interval - elapsed))
    try:
        ndi.close()
    except Exception:
        pass


def set_live(live: bool, ndi_name=None, fps=None, scale=None, alpha=None) -> Dict[str, Any]:
    global ndi_thread
    with ndi_lock:
        if ndi_name is not None:
            ndi_state["ndiName"] = str(ndi_name or "QRReplace")[:64]
        if fps is not None:
            ndi_state["fps"] = max(10, min(60, int(fps)))
        if scale is not None and scale in SCALE_MAP:
            ndi_state["scale"] = scale
        if alpha is not None:
            ndi_state["alpha"] = bool(alpha)
        if live and not ndi_state["live"]:
            ndi_stop.clear()
            ndi.reset_stats()
            ndi_state["framesSent"] = 0
            ndi_state["actualFps"] = 0.0
            ndi_state["lastError"] = ""
            ndi_state["live"] = True
            ndi_thread = threading.Thread(target=_ndi_loop, daemon=True, name="ndi-send")
            ndi_thread.start()
        elif not live and ndi_state["live"]:
            ndi_state["live"] = False
            ndi_stop.set()
            th = ndi_thread
            ndi_thread = None
            # release lock while joining
            import copy
            _ = copy.copy(ndi_state)
            threading.Thread(target=_join_thread, args=(th,), daemon=True).start()
    return status_dict()


def _join_thread(th):
    try:
        if th:
            th.join(timeout=3.0)
    except Exception:
        pass


def status_dict() -> Dict[str, Any]:
    try:
        conns = ndi.connections() if ndi_state["live"] else 0
        ndi_state["connections"] = conns
    except Exception:
        pass
    return {
        "live": ndi_state["live"],
        "ndiName": ndi_state["ndiName"],
        "fps": ndi_state["fps"],
        "scale": ndi_state["scale"],
        "alpha": ndi_state["alpha"],
        "actualFps": round(float(ndi_state.get("actualFps", 0.0)), 1),
        "framesSent": int(ndi_state.get("framesSent", 0)),
        "connections": int(ndi_state.get("connections", 0)),
        "haveNdi": HAVE_NDI,
        "previewOnly": (not HAVE_NDI),
        "resolution": SCALE_MAP.get(ndi_state.get("scale", "1080p"), (1920, 1080)),
        "lastError": ndi_state.get("lastError", "") or ndi.last_send_error,
        "sceneVersion": _scene_version,
    }


def get_network_ips(port: int) -> List[str]:
    ips: List[str] = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.append(f"http://{s.getsockname()[0]}:{port}")
        s.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            ip = info[4][0]
            if ":" not in ip and not ip.startswith("127."):
                c = f"http://{ip}:{port}"
                if c not in ips:
                    ips.append(c)
    except Exception:
        pass
    return ips

# ---------------------------------------------------------------- app

app = FastAPI(title="QRReplace")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

connected_ws: Set[WebSocket] = set()


async def _ws_broadcast(obj: dict):
    dead = []
    for ws in list(connected_ws):
        try:
            await ws.send_json(obj)
        except Exception:
            dead.append(ws)
    for d in dead:
        connected_ws.discard(d)


async def _status_pusher():
    while True:
        try:
            if connected_ws:
                await _ws_broadcast({"type": "status", "data": status_dict()})
        except Exception:
            pass
        await asyncio.sleep(1.0)


@app.on_event("startup")
async def _startup():
    asyncio.create_task(_status_pusher())


class SceneBody(BaseModel):
    name: Optional[str] = None
    canvas: Optional[Dict[str, Any]] = None
    layers: List[Dict[str, Any]]


class LiveBody(BaseModel):
    live: bool
    ndiName: Optional[str] = None
    fps: Optional[int] = None
    scale: Optional[str] = None
    alpha: Optional[bool] = None


@app.get("/api/scene")
async def api_get_scene():
    return get_scene()


@app.post("/api/scene")
async def api_set_scene(body: Dict[str, Any]):
    try:
        v = set_scene(body)
        return {"success": True, "sceneVersion": v}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...)):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (25MB max)")
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"):
        # sniff via PIL
        ext = ".png"
    name = f"{uuid.uuid4().hex[:10]}{ext}"
    # validate image
    try:
        im = renderer.Image.open(io.BytesIO(data)).convert("RGBA")
        w, h = im.size
        im.save(os.path.join(UPLOAD_DIR, name))
    except Exception:
        raise HTTPException(status_code=400, detail="Not a readable image file")
    return {"success": True, "src": f"upload:{name}", "url": f"/uploads/{name}", "w": w, "h": h}


@app.get("/api/uploads")
async def api_list_uploads():
    out = []
    try:
        for fn in sorted(os.listdir(UPLOAD_DIR)):
            if fn.startswith("."):
                continue
            p = os.path.join(UPLOAD_DIR, fn)
            if os.path.isfile(p):
                out.append({"src": f"upload:{fn}", "url": f"/uploads/{fn}", "name": fn})
    except Exception:
        pass
    # assets too
    try:
        for fn in sorted(os.listdir(ASSET_DIR)):
            if fn.startswith("."):
                continue
            out.append({"src": f"asset:{fn}", "url": f"/assets/{fn}", "name": f"[built-in] {fn}"})
    except Exception:
        pass
    return {"uploads": out}


@app.get("/api/status")
async def api_status():
    return status_dict()


@app.post("/api/live")
async def api_live(body: LiveBody):
    try:
        return set_live(body.live, body.ndiName, body.fps, body.scale, body.alpha)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------- quick operator fields
# The 2-3 things a local operator changes most (QR link, title, subtitle).
# Patching the live scene: if we're on air, the NDI output updates on the
# very next frame — no restart. Powers the desktop companion + any remote.
class QuickBody(BaseModel):
    qr: Optional[str] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None


def _pick_text_layers(scene: Dict[str, Any]):
    texts = [L for L in scene.get("layers", [])
             if isinstance(L, dict) and L.get("type") == "text" and L.get("visible", True)]

    def find(key: str, fallback_idx: int):
        for L in texts:
            if key in str(L.get("name", "")).lower():
                return L
        return texts[fallback_idx] if len(texts) > fallback_idx else None

    return texts, find("title", 0), find("subtitle", 1)


def quick_current() -> Dict[str, Any]:
    sc = get_scene()
    qr = ""
    for L in sc.get("layers", []):
        if isinstance(L, dict) and L.get("type") == "qr" and L.get("visible", True):
            qr = L.get("content", "")
            break
    _, t, st = _pick_text_layers(sc)
    return {
        "qr": qr,
        "title": (t or {}).get("text", ""),
        "subtitle": (st or {}).get("text", ""),
    }


@app.get("/api/quick")
async def api_quick_get():
    return quick_current()


@app.post("/api/quick")
async def api_quick_set(body: QuickBody):
    sc = get_scene()
    if body.qr is not None:
        for L in sc.get("layers", []):
            if isinstance(L, dict) and L.get("type") == "qr" and L.get("visible", True):
                L["content"] = body.qr
                break
    _, t, st = _pick_text_layers(sc)
    if body.title is not None and t is not None:
        t["text"] = body.title
    if body.subtitle is not None and st is not None:
        st["text"] = body.subtitle
    v = set_scene(sc)
    return {"success": True, "sceneVersion": v, "quick": quick_current()}


# ------------------------------------------------- shared presets
@app.get("/api/presets")
async def api_presets():
    from presets import PRESET_LABELS
    return {"presets": [{"id": k, "title": t, "sub": s} for k, (t, s) in PRESET_LABELS.items()]}


@app.post("/api/presets/{name}")
async def api_apply_preset(name: str):
    from presets import PRESETS
    fn = PRESETS.get(name)
    if fn is None:
        raise HTTPException(status_code=404, detail="Unknown preset")
    v = set_scene(fn())
    sc = get_scene()
    sc["sceneVersion"] = v
    return sc


@app.get("/api/preview.png")
async def api_preview(w: int = Query(960, ge=160, le=1920), h: int = Query(540, ge=90, le=1080)):
    snap = get_scene()
    try:
        png = renderer.render_png_bytes(snap, w, h)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@app.get("/api/export.png")
async def api_export():
    snap = get_scene()
    w, h = 1920, 1080
    png = renderer.render_png_bytes(snap, w, h)
    return Response(content=png, media_type="image/png",
                    headers={"Content-Disposition": 'attachment; filename="qrreplace.png"'})


@app.get("/api/templates")
async def api_templates():
    names = []
    try:
        for fn in sorted(os.listdir(TEMPLATE_DIR)):
            if fn.endswith(".json"):
                names.append(fn[:-5])
    except Exception:
        pass
    return {"templates": names}


@app.post("/api/templates/{name}")
async def api_save_template(name: str):
    safe = "".join(c for c in name if c.isalnum() or c in ("-", "_", " ")).strip()[:60] or "template"
    path = os.path.join(TEMPLATE_DIR, safe + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(get_scene(), f, indent=2)
    return {"success": True, "name": safe}


@app.get("/api/templates/{name}")
async def api_load_template(name: str):
    safe = "".join(c for c in name if c.isalnum() or c in ("-", "_", " ")).strip()[:60]
    path = os.path.join(TEMPLATE_DIR, safe + ".json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Template not found")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    set_scene(data)
    return data


@app.delete("/api/templates/{name}")
async def api_delete_template(name: str):
    safe = "".join(c for c in name if c.isalnum() or c in ("-", "_", " ")).strip()[:60]
    path = os.path.join(TEMPLATE_DIR, safe + ".json")
    try:
        os.remove(path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"success": True}


@app.get("/api/system/network")
async def api_network():
    port = int(os.environ.get("PORT", "3200"))
    return {"port": port, "urls": get_network_ips(port)}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    connected_ws.add(ws)
    try:
        await ws.send_json({"type": "scene", "data": get_scene()})
        await ws.send_json({"type": "status", "data": status_dict()})
        while True:
            try:
                msg = await ws.receive_json()
            except WebSocketDisconnect:
                break
            except Exception:
                break
            if isinstance(msg, dict) and msg.get("action") == "getScene":
                await ws.send_json({"type": "scene", "data": get_scene()})
    finally:
        connected_ws.discard(ws)


# static mounts: specific paths FIRST, catch-all "/" LAST (single-binary safe).
if os.path.isdir(UPLOAD_DIR):
    app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
if os.path.isdir(ASSET_DIR):
    app.mount("/assets", StaticFiles(directory=ASSET_DIR), name="assets")
if os.path.isdir(PUBLIC_DIR):
    app.mount("/", StaticFiles(directory=PUBLIC_DIR, html=True), name="public")


if __name__ == "__main__":
    import sys
    import uvicorn
    port = int(os.environ.get("PORT", "3200"))
    # Non-technical friendliness: the packaged binary opens the editor itself.
    if bool(getattr(sys, "frozen", False)):
        try:
            import threading as _th
            import webbrowser as _wb
            _th.Timer(1.2, lambda: _wb.open(f"http://localhost:{port}")).start()
        except Exception:
            pass
    print("\n==================================================")
    print("  QRReplace — half-screen NDI template + QR")
    print("==================================================")
    print(f"  UI:  http://localhost:{port}")
    for u in get_network_ips(port):
        print(f"  LAN: {u}")
    print(f"  NDI: {'cyndilib OK' if HAVE_NDI else 'preview-only (cyndilib missing)'}")
    print("==================================================\n")
    uvicorn.run("server:app", host="0.0.0.0", port=port, log_level="warning")
