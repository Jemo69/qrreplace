# QRReplace — NDI Lower-Third Studio

Design a half-screen template with a QR code, your own background, logos and
graphics — arrange it visually, then broadcast it over the network as an **NDI**
source. Pick it up in NDI Studio Monitor, OBS (NDI plugin), vMix, Resolume, etc.

Three faces, one app:

| Face | What it is |
|---|---|
| **Web editor (network)** | Full visual editor (drag, resize, presets, templates) served by the app on your LAN — open it from any phone, tablet or laptop. No internet needed. |
| **Clean display (OBS / screen)** | Pure design output at `/display` (no toolbars or editor chrome, transparent background, live auto-sync). Perfect for OBS Browser Source, TV screens, or projectors. |
| **Desktop companion (local)** | Cute Tk window for the person at the machine: live on-air preview, big GO LIVE button, design picker, and quick-change fields that update the broadcast instantly. |
| **NDI sender** | Background thread re-rendering your exact scene with Pillow, pushing BGRA frames via `cyndilib` (real NDI, with alpha). |

![stack](https://img.shields.io/badge/python-3.10%2B-blue)
![ui](https://img.shields.io/badge/ui-browser%20editor-dark)
![ndi](https://img.shields.io/badge/ndi-cyndilib%20%2B%20alpha-cyan)
![dist](https://img.shields.io/badge/dist-single%20binary-green)

## The 5 rules this project follows

1. **One binary.** `pyinstaller qrreplace.spec` produces a single
   `dist/QRReplace(.exe)` containing the UI, renderer, NDI library and
   built-in assets. No FFmpeg, no sidecar folders, no installers. User files
   (uploads, saved designs) live in a per-user data folder, never next to the exe.
2. **Two audiences.** *Simple* mode: 3 steps (Design → Check → Go Live),
   plain words ("See-through top" instead of "alpha channel"). *Pro* mode
   reveals fps / resolution / transparency / network diagnostics.
3. **Customization first.** Every layer's text, colors, sizes, corners,
   dimming and position is editable. One-click presets (Giving, Wi-Fi,
   Announcement), screen layouts (lower third / half / full), unlimited saved
   designs per church, venue or event.
4. **Logos, images & more.** Layer types: **QR code** (auto-generated from any link/text/Wi-Fi string, or your own uploaded QR picture), **text**, **logo/image**
   (upload any picture, one-click corner placement), **background photo**
   (upload or solid tint + dimmer), **bars/shapes**. Reorder, duplicate, lock,
   hide, fade.
5. **Accurate judgment (WYSIWYG).** The editor, the **True output** toggle
   (pixel-exact server render = NDI bytes) and the NDI feed all render from the
   same scene JSON. Plus: half-screen guide line, action/title safe areas, live
   **QR health chip** (empty code, too small, low contrast, off-screen
   warnings) and a pre-live confirmation if the QR looks unscannable.

## Run from source

### With [uv](https://docs.astral.sh/uv/) (recommended)

```bash
uv sync              # install dependencies into virtualenv
uv run app.py        # desktop window + web editor (recommended)
uv run server.py     # web editor only (headless / dev)
```

### With pip

```bash
pip install -r requirements.txt
python3 app.py       # desktop window + web editor (recommended)
sh run.sh            # web editor only (headless / dev)
# Windows: start.bat (web only) — or: python app.py
```

- Desktop window opens on the local machine; the web editor opens in the
  browser too at http://localhost:3200.
- On other devices on the same network, open the LAN URL shown in the
  desktop window (or printed on startup) — the **full editor** works there.
  Hand a volunteer your phone: they can tweak text while you run NDI.
- To view **just the design** (clean output without editor UI, transparent background, auto-updating live in real time), open `http://localhost:3200/display` (or `http://<lan-ip>:3200/display`). Use this as an **OBS Browser Source** or on confidence monitors / projectors. Press `F` for fullscreen, `B` to toggle test background.

## The local operator flow (desktop window)

1. **See it** — the preview shows exactly what's on the canvas (same pixels
   as NDI). Green/red status tells you OFF AIR vs LIVE plus viewer count.
2. **Pick a look** — ⛪ Giving / 📶 Wi-Fi / 📣 News buttons, or open any
   saved design. If you're live, viewers see the change on the next frame.
3. **Quick change** — QR link, big title, smaller line → *Apply to screen*.
   Sunday-morning link swap without touching the design.
4. **Go live** — one big button. Copy-phone-link shares the editor on the LAN.

## The 3-step flow (web editor)

1. **Design** — pick a preset, or add QR / text / logo / background / bar.
   Drag to move, drag a corner square to resize (QR & logos keep square shape),
   arrow keys nudge, `Ctrl+D` duplicates, `Del` removes.
2. **Check** — enable **True output** above the canvas: that's exactly what the
   network sees. Green `QR: looks scannable ✓` chip = phones will read it.
   Dark QR on a light card, bigger than a playing card on screen.
3. **Go Live** — press **Go Live**. On another machine on the same network,
   choose your source name in NDI Studio Monitor / OBS / vMix.

Transparency: with **See-through top** on, the top half is alpha-0 in the NDI
signal — overlay it directly on live video in vMix/OBS. Turn it off for a solid
full picture.

## Build the single binary

```powershell
# Windows
.\build.ps1          # → dist\QRReplace.exe
```

```sh
# macOS / Linux
sh build.sh          # → dist/QRReplace
```

Double-click it: the desktop window opens (plus the web editor in a
browser). First launch may take ~10s (one-file unpack) and the firewall
will ask to allow it on **Private** networks — say yes or other PCs can't
see the stream **or** the editor.

## Releases (build script → GitHub Release)

`.github/workflows/release.yml` builds on every push; pushing a tag builds
**and publishes**:

```bash
git tag v1.0.0 && git push origin v1.0.0
# → QRReplace.exe (Windows) + QRReplace-mac.dmg (macOS) + QRReplace (Linux)
#   attached to the v1.0.0 Release automatically.
```

Check the *Actions* tab for per-commit test builds (artifacts, no release).

## Network visibility

- **Same subnet (default):** sources advertise over mDNS — receivers find them
  automatically. Sending and viewing PCs must share the LAN/subnet.
- **Other subnets/VLANs:** run NDI Discovery Server (free, in NDI Tools) and
  point both ends at it (same trade-off as all NDI apps: mDNS turns off).
- The **Network addresses** button in Pro mode shows this machine's LAN URLs.

## Project layout

| file | what |
|---|---|
| `app.py` | Desktop companion (Tk): live preview, Go Live, designs, quick-change — embeds the backend |
| `presets.py` | Shared Giving/Wi-Fi/Announcement designs (one source for web + desktop) |
| `server.py` | FastAPI app: scene API, uploads, templates, presets, quick-edit, preview PNG, NDI thread, static UI |
| `renderer.py` | Pillow compositor: scene JSON → RGBA → BGRA bytes (shared by preview + NDI) |
| `ndi_sender.py` | `cyndilib` wrapper with preview-only fallback |
| `paths.py` | Single-binary paths: read-only bundle vs writable user data dir |
| `public/` | Editor UI (`index.html`, `styles.css`, `app.js`) — zero CDN, works offline |
| `assets/` | Built-in backgrounds shipped inside the binary |
| `qrreplace.spec` / `build.sh` / `build.ps1` / `pyi_rth_ndi.py` | One-binary packaging |
| `uploads/` `templates/` | Your files (user data dir when packaged) |

## API (for integrators / Pro users)

- `GET/POST /api/scene` — full scene JSON (the single source of truth)
- `POST /api/upload` (multipart `file`) — add a logo/background image
- `GET /api/preview.png?w=&h=` — pixel-exact server render
- `GET /api/export.png` — full-res 1920×1080 snapshot download
- `POST /api/live {live,ndiName,fps,scale,alpha}` / `GET /api/status`
- `GET/POST /api/quick {qr,title,subtitle}` — live patch, no restart
- `GET /api/presets` / `POST /api/presets/{giving,wifi,announce}`
- `GET/POST/DELETE /api/templates/{name}` — saved designs
- `WS /ws` — live status push

## Notes / limits

- QR placeholder in the editor is stylized; **True output** shows the real,
  phone-scannable code (generated server-side).
- NDI send rate depends on CPU (full Pillow re-render per frame); lower-thirds
  are mostly static, so 720p/30 or 540p/30 is plenty for typical church PCs.
- Changing fps/scale/name while live restarts the sender (receivers
  re-acquire in ~1s).
