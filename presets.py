"""Shared design presets — single source of truth.

Both the web editor (`POST /api/presets/{name}`) and the desktop companion
use these, so "Giving" looks identical everywhere. Each returns a full scene
dict for the 1920x1080 canvas (see renderer.py).
"""
from __future__ import annotations

import uuid
from typing import Any, Dict

CW, CH = 1920, 1080


def _id() -> str:
    return uuid.uuid4().hex[:8]


def _bar(**kw: Any) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "id": _id(), "type": "shape", "name": "Bar",
        "x": 0, "y": 560, "w": CW, "h": 10,
        "opacity": 1, "visible": True, "lock": False,
        "shape": "rect", "fill": "#f5b301",
        "stroke": "", "strokeWidth": 0, "radius": 0,
    }
    d.update(kw)
    return d


def _bg(y: int, h: int, color: str = "#0d1326", opacity: float = 0.28) -> Dict[str, Any]:
    return {
        "id": "bg-photo", "type": "background", "name": "Background photo",
        "x": 0, "y": y, "w": CW, "h": h,
        "opacity": opacity, "visible": True, "lock": False,
        "src": "asset:default-bg.png", "fit": "cover", "color": color,
    }


def _text(name: str, x: int, y: int, w: int, h: int, text: str,
          size: int, color: str, bold: bool = True, align: str = "left") -> Dict[str, Any]:
    return {
        "id": _id(), "type": "text", "name": name,
        "x": x, "y": y, "w": w, "h": h,
        "opacity": 1, "visible": True, "lock": False,
        "text": text, "fontSize": size, "color": color,
        "bold": bold, "align": align,
    }


def _qr(x: int, y: int, s: int, content: str, fg: str = "#0d1326", pad: int = 22) -> Dict[str, Any]:
    return {
        "id": _id(), "type": "qr", "name": "QR code",
        "x": x, "y": y, "w": s, "h": s,
        "opacity": 1, "visible": True, "lock": False,
        "content": content, "fg": fg, "bg": "#ffffff",
        "transparentBg": False, "showBox": True, "radius": 28, "pad": pad,
    }


def giving() -> Dict[str, Any]:
    return {
        "name": "Sunday Service — Give QR",
        "canvas": {"width": CW, "height": CH, "alpha": True, "bgColor": "#000000"},
        "layers": [
            _bar(id="bg-panel", name="Bottom panel", y=560, h=520, fill="#0d1326"),
            _bar(id="accent", name="Accent bar", y=560, h=10, fill="#f5b301"),
            _bg(570, 510),
            _text("Title", 120, 640, 1050, 160, "Scan to Give", 110, "#ffffff"),
            _text("Subtitle", 120, 800, 1050, 200,
                  "Point your phone camera at the code\nThank you for your generosity!",
                  46, "#c9d2ea", bold=False),
            _qr(1400, 630, 400, "https://example.com/give"),
        ],
    }


def wifi() -> Dict[str, Any]:
    return {
        "name": "Guest Wi-Fi — Scan to Connect",
        "canvas": {"width": CW, "height": CH, "alpha": True, "bgColor": "#000000"},
        "layers": [
            _bar(id="bg-panel", name="Side panel", x=960, y=0, w=960, h=1080, fill="#0d1326"),
            _bar(id="accent", name="Accent bar", x=960, y=0, w=10, h=1080, fill="#35d07f"),
            {**_bg(0, 1080, opacity=0.22), "x": 970, "w": 950},
            _text("Title", 1070, 120, 750, 140, "Free Guest Wi-Fi", 84, "#ffffff"),
            _text("Subtitle", 1070, 260, 750, 140,
                  "Scan with your phone camera\nto join automatically.",
                  40, "#c9d2ea", bold=False),
            _qr(1130, 450, 480, "WIFI:T:WPA;S:ChurchGuest;P:welcome123;;", pad=24),
        ],
    }


def announce() -> Dict[str, Any]:
    return {
        "name": "Announcement Banner",
        "canvas": {"width": CW, "height": CH, "alpha": True, "bgColor": "#000000"},
        "layers": [
            _bar(id="bg-panel", name="Banner", y=770, h=310, fill="#101a33"),
            _bar(id="accent", name="Accent bar", y=770, h=10, fill="#ff5d5d"),
            _bg(780, 300, color="#101a33", opacity=0.25),
            _text("Title", 120, 810, 1250, 130,
                  "Volunteers meeting — Wednesday 7pm", 72, "#ffffff"),
            _text("Subtitle", 120, 935, 1250, 100,
                  "Fellowship hall · scan to sign up", 42, "#c9d2ea", bold=False),
            _qr(1560, 790, 270, "https://example.com/signup", fg="#101a33", pad=18),
        ],
    }


PRESETS: Dict[str, Any] = {"giving": giving, "wifi": wifi, "announce": announce}

#: Human labels for pickers (desktop + web).
PRESET_LABELS = {
    "giving": ("⛪ Giving", "Lower-third + QR"),
    "wifi": ("📶 Wi-Fi / Check-in", "Half panel + big QR"),
    "announce": ("📣 Announcement", "Full-width banner"),
}
