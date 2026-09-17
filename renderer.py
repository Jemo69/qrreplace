"""Scene compositor: JSON scene -> RGBA frame (Pillow) -> BGRA bytes (NDI)."""
from __future__ import annotations

import hashlib
import io
import os
from typing import Any, Dict, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from paths import ASSET_DIR, BUNDLE_DIR, DATA_DIR, UPLOAD_DIR

CANVAS_W = 1920
CANVAS_H = 1080

_FONT_CACHE: Dict[Tuple[str, int], Any] = {}
_IMG_CACHE: Dict[str, Image.Image] = {}
_QR_CACHE: Dict[str, Image.Image] = {}


def hex_to_rgb(s: str, default=(255, 255, 255)):
    try:
        s = (s or "").strip().lstrip("#")
        if len(s) == 3:
            s = "".join(c * 2 for c in s)
        if len(s) != 6:
            return default
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except Exception:
        return default


def get_font(size: int, bold: bool = False):
    key = ("bold" if bold else "reg", int(size))
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    candidates = []
    if bold:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    font = None
    for p in candidates:
        try:
            if os.path.exists(p):
                font = ImageFont.truetype(p, int(max(8, size)))
                break
        except Exception:
            continue
    if font is None:
        try:
            font = ImageFont.load_default(size=int(max(8, size)))
        except Exception:
            font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


def resolve_src(src: str) -> str | None:
    """Map a layer src ('upload:xxx', 'asset:xxx', '/uploads/...') to a file path."""
    if not src:
        return None
    if src.startswith("upload:"):
        name = src[len("upload:"):]
        p = os.path.join(UPLOAD_DIR, os.path.basename(name))
        return p if os.path.exists(p) else None
    if src.startswith("asset:"):
        name = src[len("asset:"):]
        p = os.path.join(ASSET_DIR, os.path.basename(name))
        return p if os.path.exists(p) else None
    if src.startswith("/uploads/"):
        p = os.path.join(UPLOAD_DIR, os.path.basename(src))
        return p if os.path.exists(p) else None
    if src.startswith("/assets/"):
        p = os.path.join(ASSET_DIR, os.path.basename(src))
        return p if os.path.exists(p) else None
    # absolute or relative path fallback
    if os.path.exists(src):
        return src
    p2 = os.path.join(BUNDLE_DIR, os.path.basename(src))
    return p2 if os.path.exists(p2) else None


def load_image_cached(path: str) -> Image.Image | None:
    try:
        mtime = os.path.getmtime(path)
    except Exception:
        return None
    key = f"{path}:{mtime}"
    if key in _IMG_CACHE:
        return _IMG_CACHE[key]
    try:
        img = Image.open(path).convert("RGBA")
        # evict old entries for same path
        for k in [k for k in _IMG_CACHE if k.startswith(path + ":")]:
            _IMG_CACHE.pop(k, None)
        _IMG_CACHE[key] = img
        return img
    except Exception:
        return None


def draw_cover(base: Image.Image, img: Image.Image, box, mode: str = "cover"):
    """Paste img into base within box (x,y,w,h) using cover/contain/stretch."""
    x, y, w, h = [int(v) for v in box]
    if w <= 0 or h <= 0:
        return
    try:
        if mode == "stretch":
            fitted = img.resize((w, h), Image.LANCZOS)
            ox, oy = 0, 0
        elif mode == "contain":
            scale = min(w / img.width, h / img.height)
            nw, nh = max(1, int(img.width * scale)), max(1, int(img.height * scale))
            fitted = img.resize((nw, nh), Image.LANCZOS)
            ox, oy = (w - nw) // 2, (h - nh) // 2
        else:  # cover
            scale = max(w / img.width, h / img.height)
            nw, nh = max(1, int(img.width * scale)), max(1, int(img.height * scale))
            fitted = img.resize((nw, nh), Image.LANCZOS)
            ox, oy = (w - nw) // 2, (h - nh) // 2
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        layer.alpha_composite(fitted, (ox, oy))
        base.alpha_composite(layer, (x, y))
    except Exception:
        pass


def make_qr_image(content: str, fg: str, bg: str, transparent_bg: bool) -> Image.Image:
    import qrcode

    key_src = f"{content}|{fg}|{bg}|{transparent_bg}"
    key = hashlib.md5(key_src.encode("utf-8")).hexdigest()
    if key in _QR_CACHE:
        return _QR_CACHE[key]
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(content or " ")
    qr.make(fit=True)
    fg_rgb = hex_to_rgb(fg, (0, 0, 0))
    if transparent_bg:
        img = qr.make_image(fill_color=fg_rgb, back_color=(255, 255, 255)).convert("RGBA")
        # make white transparent
        data = img.getdata()
        new = []
        for px in data:
            if px[0] > 220 and px[1] > 220 and px[2] > 220:
                new.append((255, 255, 255, 0))
            else:
                new.append((fg_rgb[0], fg_rgb[1], fg_rgb[2], 255))
        img.putdata(new)
    else:
        bg_rgb = hex_to_rgb(bg, (255, 255, 255))
        img = qr.make_image(fill_color=fg_rgb, back_color=bg_rgb).convert("RGBA")
    _QR_CACHE[key] = img
    if len(_QR_CACHE) > 30:
        _QR_CACHE.pop(next(iter(_QR_CACHE)))
    return img


def apply_opacity(img: Image.Image, opacity: float) -> Image.Image:
    if opacity >= 0.999:
        return img
    if opacity <= 0.001:
        img = img.copy()
        img.putalpha(0)
        return img
    img = img.copy()
    a = img.getchannel("A").point(lambda v: int(v * opacity))
    img.putalpha(a)
    return img


def render_scene(scene: Dict[str, Any], out_w: int = CANVAS_W, out_h: int = CANVAS_H) -> Image.Image:
    """Render scene dict to a PIL RGBA image of out_w x out_h."""
    canvas = scene.get("canvas", {}) if isinstance(scene, dict) else {}
    opaque = not canvas.get("alpha", True)
    bg_color = hex_to_rgb(canvas.get("bgColor", "#000000"), (0, 0, 0))

    # Full-res working surface
    surf = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    if opaque:
        surf = Image.new("RGBA", (CANVAS_W, CANVAS_H), (*bg_color, 255))

    layers = scene.get("layers", []) if isinstance(scene, dict) else []
    for L in layers:
        try:
            if not isinstance(L, dict) or not L.get("visible", True):
                continue
            t = L.get("type", "shape")
            x, y, w, h = float(L.get("x", 0)), float(L.get("y", 0)), float(L.get("w", 200)), float(L.get("h", 200))
            opacity = float(L.get("opacity", 1.0))
            if w <= 1 or h <= 1:
                continue

            if t == "background":
                mode = L.get("fit", "cover")
                color = hex_to_rgb(L.get("color", "#0b1020"), (11, 16, 32))
                # paint color full-canvas first for this layer's box
                box_img = Image.new("RGBA", (int(w), int(h)), (*color, 255))
                box_img = apply_opacity(box_img, opacity)
                surf.alpha_composite(box_img, (int(x), int(y)))
                src = L.get("src", "")
                if src:
                    path = resolve_src(src)
                    if path:
                        img = load_image_cached(path)
                        if img is not None:
                            # draw image over the color box (same box)
                            tmp = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
                            img2 = apply_opacity(img, opacity)
                            draw_cover(tmp, img2, (int(x), int(y), int(w), int(h)), mode)
                            surf.alpha_composite(tmp)

            elif t == "image":
                src = L.get("src", "")
                if not src:
                    continue
                path = resolve_src(src)
                if not path:
                    # draw placeholder
                    ph = Image.new("RGBA", (int(w), int(h)), (40, 44, 60, 255))
                    d = ImageDraw.Draw(ph)
                    d.rectangle([0, 0, int(w) - 1, int(h) - 1], outline=(120, 130, 160, 255), width=3)
                    ph = apply_opacity(ph, opacity)
                    surf.alpha_composite(ph, (int(x), int(y)))
                    continue
                img = load_image_cached(path)
                if img is None:
                    continue
                fit = L.get("fit", "contain")
                tmp = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
                img2 = apply_opacity(img, opacity)
                # default images: contain inside box preserving aspect on transparent pad
                if fit == "stretch":
                    fitted = img2.resize((int(w), int(h)), Image.LANCZOS)
                    tmp.alpha_composite(fitted, (int(x), int(y)))
                elif fit == "cover":
                    draw_cover(tmp, img2, (int(x), int(y), int(w), int(h)), "cover")
                else:
                    draw_cover(tmp, img2, (int(x), int(y), int(w), int(h)), "contain")
                surf.alpha_composite(tmp)

            elif t == "qr":
                show_box = bool(L.get("showBox", True))
                radius = int(L.get("radius", 24))
                pad = int(L.get("pad", 18))
                # Custom QR image mode: user uploaded their own QR picture.
                # Render it as-is (inside the card when show_box is on).
                if L.get("qrMode") == "custom":
                    src = L.get("src", "")
                    path = resolve_src(src) if src else None
                    img = load_image_cached(path) if path else None
                    if img is None:
                        ph = Image.new("RGBA", (int(w), int(h)), (40, 44, 60, 255))
                        d = ImageDraw.Draw(ph)
                        d.rectangle([0, 0, int(w) - 1, int(h) - 1], outline=(255, 176, 32, 255), width=3)
                        ph = apply_opacity(ph, opacity)
                        surf.alpha_composite(ph, (int(x), int(y)))
                        continue
                    if show_box and not bool(L.get("transparentBg", False)):
                        card = Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0))
                        d = ImageDraw.Draw(card)
                        bg_rgb = hex_to_rgb(L.get("bg", "#ffffff"), (255, 255, 255))
                        d.rounded_rectangle([0, 0, int(w) - 1, int(h) - 1], radius=radius, fill=(*bg_rgb, 255))
                        iw, ih = int(w) - pad * 2, int(h) - pad * 2
                        if iw > 10 and ih > 10:
                            scale = min(iw / img.width, ih / img.height)
                            nw, nh = max(1, int(img.width * scale)), max(1, int(img.height * scale))
                            qf = img.resize((nw, nh), Image.LANCZOS)
                            card.alpha_composite(qf, (pad + (iw - nw) // 2, pad + (ih - nh) // 2))
                        card = apply_opacity(card, opacity)
                        surf.alpha_composite(card, (int(x), int(y)))
                    else:
                        qf = img.resize((int(w), int(h)), Image.LANCZOS)
                        qf = apply_opacity(qf, opacity)
                        surf.alpha_composite(qf, (int(x), int(y)))
                    continue
                content = L.get("content", "https://example.com")
                fg = L.get("fg", "#000000")
                bgc = L.get("bg", "#ffffff")
                tbg = bool(L.get("transparentBg", False))
                qimg = make_qr_image(content, fg, bgc, transparent_bg=(tbg and not show_box))
                if show_box and not tbg:
                    # white rounded card behind QR
                    card = Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0))
                    d = ImageDraw.Draw(card)
                    bg_rgb = hex_to_rgb(bgc, (255, 255, 255))
                    d.rounded_rectangle([0, 0, int(w) - 1, int(h) - 1], radius=radius, fill=(*bg_rgb, 255))
                    # fit qr inside with padding
                    iw, ih = int(w) - pad * 2, int(h) - pad * 2
                    if iw > 10 and ih > 10:
                        qf = qimg.resize((iw, ih), Image.NEAREST)
                        card.alpha_composite(qf, (pad, pad))
                    card = apply_opacity(card, opacity)
                    surf.alpha_composite(card, (int(x), int(y)))
                else:
                    qf = qimg.resize((int(w), int(h)), Image.NEAREST)
                    qf = apply_opacity(qf, opacity)
                    surf.alpha_composite(qf, (int(x), int(y)))

            elif t == "text":
                txt = str(L.get("text", "Text"))
                size = int(L.get("fontSize", 64))
                color = hex_to_rgb(L.get("color", "#ffffff"), (255, 255, 255))
                bold = bool(L.get("bold", False))
                align = L.get("align", "left")
                # scale font: box height hint — font size is in canvas px
                font = get_font(size, bold)
                # render text block inside box with wrapping
                box_w, box_h = int(w), int(h)
                txt_img = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
                d = ImageDraw.Draw(txt_img)
                # simple word wrap
                lines: list[str] = []
                for para in txt.split("\n"):
                    words = para.split(" ")
                    cur = ""
                    for wd in words:
                        trial = (cur + " " + wd).strip()
                        try:
                            bb = d.textbbox((0, 0), trial, font=font)
                            tw = bb[2] - bb[0]
                        except Exception:
                            tw = len(trial) * size * 0.6
                        if tw <= box_w or not cur:
                            cur = trial
                        else:
                            lines.append(cur)
                            cur = wd
                    lines.append(cur)
                # vertical: top
                try:
                    ascent, descent = font.getmetrics()
                    lh = ascent + descent + 6
                except Exception:
                    lh = int(size * 1.25)
                cy = 0
                for ln in lines:
                    if cy + lh > box_h + lh:
                        break
                    try:
                        bb = d.textbbox((0, 0), ln, font=font)
                        tw = bb[2] - bb[0]
                    except Exception:
                        tw = len(ln) * size * 0.55
                    if align == "center":
                        tx = (box_w - tw) // 2
                    elif align == "right":
                        tx = box_w - tw
                    else:
                        tx = 0
                    # subtle shadow for readability
                    try:
                        d.text((tx + 2, cy + 2), ln, font=font, fill=(0, 0, 0, 160))
                    except Exception:
                        pass
                    d.text((tx, cy), ln, font=font, fill=(*color, 255))
                    cy += lh
                txt_img = apply_opacity(txt_img, opacity)
                surf.alpha_composite(txt_img, (int(x), int(y)))

            elif t == "shape":
                shape = L.get("shape", "rect")
                fill = hex_to_rgb(L.get("fill", "#ff3366"), (255, 51, 102))
                stroke = L.get("stroke", "")
                sw = int(L.get("strokeWidth", 0))
                radius = int(L.get("radius", 0))
                box_w, box_h = int(w), int(h)
                sh = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
                d = ImageDraw.Draw(sh)
                if shape == "circle":
                    d.ellipse([0, 0, box_w - 1, box_h - 1], fill=(*fill, 255),
                              outline=hex_to_rgb(stroke, fill) + (255,) if stroke else None,
                              width=sw if stroke else 1)
                else:
                    if radius > 0:
                        d.rounded_rectangle([0, 0, box_w - 1, box_h - 1], radius=radius, fill=(*fill, 255),
                                            outline=hex_to_rgb(stroke, fill) + (255,) if stroke else None,
                                            width=sw if stroke else 1)
                    else:
                        d.rectangle([0, 0, box_w - 1, box_h - 1], fill=(*fill, 255),
                                    outline=hex_to_rgb(stroke, fill) + (255,) if stroke else None,
                                    width=sw if stroke else 1)
                sh = apply_opacity(sh, opacity)
                surf.alpha_composite(sh, (int(x), int(y)))
        except Exception:
            continue

    if out_w != CANVAS_W or out_h != CANVAS_H:
        surf = surf.resize((out_w, out_h), Image.BILINEAR)
    return surf


def rgba_to_bgra_bytes(img: Image.Image) -> bytes:
    """PIL RGBA -> contiguous BGRA bytes for NDI."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    arr = np.asarray(img)  # H x W x 4, RGBA
    bgra = np.empty_like(arr)
    bgra[:, :, 0] = arr[:, :, 2]
    bgra[:, :, 1] = arr[:, :, 1]
    bgra[:, :, 2] = arr[:, :, 0]
    bgra[:, :, 3] = arr[:, :, 3]
    return bgra.tobytes()


def render_png_bytes(scene: Dict[str, Any], out_w: int = 960, out_h: int = 540) -> bytes:
    img = render_scene(scene, out_w, out_h)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
