/* QRReplace editor — self-contained, no CDN. What you arrange here is
   what the NDI sender renders (same scene JSON, Pillow on the server). */
"use strict";

const CW = 1920, CH = 1080;          // canvas pixels
const VW = 960, VH = 540;            // editor display pixels
const S = VW / CW;                   // display scale 0.5

const $ = (id) => document.getElementById(id);
const uid = () => Math.random().toString(36).slice(2, 10);

const state = {
  scene: null,
  sel: null,
  mode: "simple",
  showGuides: true,
  trueOut: false,
  status: null,
  imgCache: new Map(),   // src -> HTMLImageElement
  drag: null,
  saveTimer: null,
  trueTimer: null,
};

/* ═══════════════ API ═══════════════ */
async function api(path, opts = {}) {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!r.ok) throw new Error(await r.text().catch(() => r.statusText));
  const ct = r.headers.get("content-type") || "";
  return ct.includes("json") ? r.json() : r.blob();
}
const saveScene = () => api("/api/scene", { method: "POST", body: JSON.stringify(state.scene) });

function markDirty(refreshTrue = true) {
  $("sbSaved").textContent = "Saving…";
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(async () => {
    try {
      await saveScene();
      $("sbSaved").textContent = "Saved ✓";
      if (state.trueOut && refreshTrue) scheduleTrueRefresh();
    } catch (e) {
      $("sbSaved").textContent = "Save failed — retrying…";
      markDirty(false);
    }
  }, 700);
  renderAll();
}

/* ═══════════════ image URLs ═══════════════ */
function srcToUrl(src) {
  if (!src) return "";
  if (src.startsWith("upload:")) return "/uploads/" + src.slice(7);
  if (src.startsWith("asset:")) return "/assets/" + src.slice(6);
  return src;
}
function imgFor(src) {
  if (!src) return null;
  if (state.imgCache.has(src)) return state.imgCache.get(src);
  const im = new Image();
  im.src = srcToUrl(src);
  im.onload = () => renderEditor();
  state.imgCache.set(src, im);
  return im;
}

/* ═══════════════ presets ═══════════════ */
function shapeLayer(o) {
  return { id: uid(), type: "shape", name: "Bar", x: 0, y: 560, w: CW, h: 10,
    opacity: 1, visible: true, lock: false, shape: "rect", fill: "#f5b301",
    stroke: "", strokeWidth: 0, radius: 0, ...o };
}
/* NOTE: presets live server-side (presets.py) — applied via POST /api/presets/{name}
   so the web editor and the desktop app always share the same designs. */

/* ═══════════════ editor canvas ═══════════════ */
const cv = $("editor"), ctx = cv.getContext("2d");

function hexRGB(s, fb = [255, 255, 255]) {
  s = (s || "").trim().replace("#", "");
  if (s.length === 3) s = s.split("").map((c) => c + c).join("");
  if (s.length !== 6) return fb;
  const n = parseInt(s, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function css(hex, a = 1) {
  const [r, g, b] = hexRGB(hex);
  return `rgba(${r},${g},${b},${a})`;
}

function drawChecker() {
  const n = 24, s = VW / n, m = VH / (n * 9 / 16);
  for (let y = 0; y < VH / m; y++)
    for (let x = 0; x < n; x++) {
      ctx.fillStyle = (x + y) % 2 ? "#20242e" : "#2a2f3c";
      ctx.fillRect(x * s, y * m, s + 1, m + 1);
    }
}

function rr(x, y, w, h, r) {
  r = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function drawImageFit(im, dx, dy, dw, dh, fit) {
  if (!im || !im.complete || !im.naturalWidth) return;
  const iw = im.naturalWidth, ih = im.naturalHeight;
  if (fit === "stretch") return void ctx.drawImage(im, dx, dy, dw, dh);
  const sc = fit === "cover" ? Math.max(dw / iw, dh / ih) : Math.min(dw / iw, dh / ih);
  const w = iw * sc, h = ih * sc, x = dx + (dw - w) / 2, y = dy + (dh - h) / 2;
  ctx.save();
  ctx.beginPath(); ctx.rect(dx, dy, dw, dh); ctx.clip();
  ctx.drawImage(im, x, y, w, h);
  ctx.restore();
}

function drawFinder(x, y, s) {
  ctx.fillStyle = "#0d1326";
  ctx.fillRect(x, y, s, s);
  ctx.fillStyle = "#fff";
  ctx.fillRect(x + s * 0.14, y + s * 0.14, s * 0.72, s * 0.72);
  ctx.fillStyle = "#0d1326";
  ctx.fillRect(x + s * 0.28, y + s * 0.28, s * 0.44, s * 0.44);
}

function drawQRPlaceholder(L, dx, dy, dw, dh) {
  const fg = L.fg || "#0d1326";
  if (L.showBox !== false && !L.transparentBg) {
    ctx.fillStyle = css(L.bg || "#ffffff", 1);
    rr(dx, dy, dw, dh, (L.radius || 24) * S);
    ctx.fill();
  }
  const pad = (L.pad || 20) * S;
  const qx = dx + pad, qy = dy + pad, qw = dw - pad * 2, qh = dh - pad * 2;
  if (qw < 30 || qh < 30) return;
  const fs = Math.min(qw, qh) * 0.30;
  drawFinder(qx, qy, fs);
  drawFinder(qx + qw - fs, qy, fs);
  drawFinder(qx, qy + qh - fs, fs);
  // deterministic pseudo-modules from content hash
  let hsh = 0;
  const str = L.content || "";
  for (let i = 0; i < str.length; i++) hsh = (hsh * 31 + str.charCodeAt(i)) >>> 0;
  const n = 12, cell = Math.min(qw, qh) / (n + 6);
  ctx.fillStyle = css(fg, 1);
  for (let gy = 0; gy < n; gy++)
    for (let gx = 0; gx < n; gx++) {
      const inF = (gx < 4 && gy < 4) || (gx >= n - 4 && gy < 4) || (gx < 4 && gy >= n - 4);
      if (inF) continue;
      hsh = (hsh * 1103515245 + 12345) >>> 0;
      if (hsh % 100 < 44)
        ctx.fillRect(qx + (gx + 3) * cell, qy + (gy + 3) * cell, cell * 0.92, cell * 0.92);
    }
}

function wrapLines(text, font, maxW) {
  ctx.font = font;
  const out = [];
  for (const para of String(text).split("\n")) {
    let cur = "";
    for (const wd of para.split(" ")) {
      const t = (cur + " " + wd).trim();
      if (ctx.measureText(t).width <= maxW || !cur) cur = t;
      else { out.push(cur); cur = wd; }
    }
    out.push(cur);
  }
  return out;
}

function drawLayer(L) {
  const dx = L.x * S, dy = L.y * S, dw = L.w * S, dh = L.h * S;
  if (!L.visible || L.w <= 1 || L.h <= 1) return;
  ctx.save();
  ctx.globalAlpha = L.opacity ?? 1;
  if (L.type === "shape") {
    ctx.fillStyle = css(L.fill || "#ff3366", 1);
    if (L.shape === "circle") { ctx.beginPath(); ctx.ellipse(dx + dw / 2, dy + dh / 2, dw / 2, dh / 2, 0, 0, 7); ctx.fill(); }
    else if ((L.radius || 0) > 0) { rr(dx, dy, dw, dh, L.radius * S); ctx.fill(); }
    else ctx.fillRect(dx, dy, dw, dh);
  } else if (L.type === "background") {
    ctx.fillStyle = css(L.color || "#0d1326", 1);
    ctx.fillRect(dx, dy, dw, dh);
    if (L.src) { const im = imgFor(L.src); if (im) drawImageFit(im, dx, dy, dw, dh, L.fit || "cover"); }
  } else if (L.type === "image") {
    if (L.src) {
      const im = imgFor(L.src);
      if (im && im.complete && im.naturalWidth) drawImageFit(im, dx, dy, dw, dh, L.fit || "contain");
      else { ctx.fillStyle = "#282e40"; ctx.fillRect(dx, dy, dw, dh); }
    } else {
      ctx.fillStyle = "#282e40"; ctx.fillRect(dx, dy, dw, dh);
      ctx.strokeStyle = "#78829e"; ctx.setLineDash([6, 4]); ctx.strokeRect(dx, dy, dw, dh); ctx.setLineDash([]);
      ctx.fillStyle = "#aab4cf"; ctx.font = "12px sans-serif"; ctx.textAlign = "center";
      ctx.fillText("logo / image", dx + dw / 2, dy + dh / 2);
    }
  } else if (L.type === "qr") {
    if (L.qrMode === "custom") {
      if (L.showBox !== false && !L.transparentBg) {
        ctx.fillStyle = css(L.bg || "#ffffff", 1);
        rr(dx, dy, dw, dh, (L.radius || 24) * S);
        ctx.fill();
      }
      const pad = (L.pad || 20) * S;
      const im = L.src ? imgFor(L.src) : null;
      if (im && im.complete && im.naturalWidth) {
        if (L.showBox !== false && !L.transparentBg)
          drawImageFit(im, dx + pad, dy + pad, dw - pad * 2, dh - pad * 2, "contain");
        else
          drawImageFit(im, dx, dy, dw, dh, "contain");
      } else {
        ctx.fillStyle = "#282e40"; ctx.fillRect(dx, dy, dw, dh);
        ctx.strokeStyle = "#ffb020"; ctx.setLineDash([6, 4]); ctx.strokeRect(dx, dy, dw, dh); ctx.setLineDash([]);
        ctx.fillStyle = "#aab4cf"; ctx.font = "12px sans-serif"; ctx.textAlign = "center";
        ctx.fillText("own QR image — click right to upload", dx + dw / 2, dy + dh / 2);
      }
    } else {
      drawQRPlaceholder(L, dx, dy, dw, dh);
    }
  } else if (L.type === "text") {
    const px = (L.fontSize || 64) * S;
    ctx.font = `${L.bold ? "700" : "400"} ${px}px -apple-system,"Segoe UI",Roboto,Arial,sans-serif`;
    ctx.fillStyle = css(L.color || "#ffffff", 1);
    ctx.textBaseline = "top";
    const lines = wrapLines(L.text || "", ctx.font, dw);
    const lh = px * 1.22;
    lines.forEach((ln, i) => {
      let tx = dx;
      const w = ctx.measureText(ln).width;
      if (L.align === "center") tx = dx + (dw - w) / 2;
      if (L.align === "right") tx = dx + dw - w;
      ctx.fillStyle = "rgba(0,0,0,.55)"; ctx.fillText(ln, tx + 2, dy + i * lh + 2);
      ctx.fillStyle = css(L.color || "#ffffff", 1); ctx.fillText(ln, tx, dy + i * lh);
    });
  }
  ctx.restore();
}

function renderEditor() {
  if (!state.scene) return;
  ctx.clearRect(0, 0, VW, VH);
  const alpha = state.scene.canvas?.alpha !== false;
  if (alpha) drawChecker();
  else { ctx.fillStyle = css(state.scene.canvas?.bgColor || "#000000", 1); ctx.fillRect(0, 0, VW, VH); }

  for (const L of state.scene.layers) drawLayer(L);

  if (state.showGuides) {
    ctx.save();
    ctx.strokeStyle = "rgba(245,179,1,.85)"; ctx.setLineDash([7, 5]); ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(0, VH / 2); ctx.lineTo(VW, VH / 2); ctx.stroke(); // half-screen line
    ctx.setLineDash([4, 4]); ctx.strokeStyle = "rgba(120,200,255,.5)";
    ctx.strokeRect(VW * 0.05, VH * 0.05, VW * 0.9, VH * 0.9);   // action safe
    ctx.strokeStyle = "rgba(120,200,255,.3)";
    ctx.strokeRect(VW * 0.1, VH * 0.1, VW * 0.8, VH * 0.8);     // title safe
    ctx.setLineDash([]);
    ctx.fillStyle = "rgba(245,179,1,.9)"; ctx.font = "11px sans-serif";
    ctx.fillText("half-screen line", 8, VH / 2 - 6);
    ctx.restore();
  }
  drawSelection();
  updateHealth();
}

function layerById(id) { return state.scene?.layers.find((l) => l.id === id); }

function drawSelection() {
  const L = state.sel && layerById(state.sel);
  if (!L) return;
  const dx = L.x * S, dy = L.y * S, dw = L.w * S, dh = L.h * S;
  ctx.save();
  ctx.strokeStyle = "#f5b301"; ctx.lineWidth = 2;
  ctx.strokeRect(dx, dy, dw, dh);
  ctx.fillStyle = "#f5b301";
  const pts = [[dx, dy], [dx + dw / 2, dy], [dx + dw, dy], [dx + dw, dy + dh / 2],
    [dx + dw, dy + dh], [dx + dw / 2, dy + dh], [dx, dy + dh], [dx, dy + dh / 2]];
  state._handles = pts;
  for (const [hx, hy] of pts) ctx.fillRect(hx - 5, hy - 5, 10, 10);
  ctx.restore();
}

function hitHandle(mx, my) {
  if (!state._handles) return -1;
  for (let i = 0; i < state._handles.length; i++) {
    const [hx, hy] = state._handles[i];
    if (Math.abs(mx - hx) <= 7 && Math.abs(my - hy) <= 7) return i;
  }
  return -1;
}
function hitLayer(mx, my) {
  const layers = state.scene.layers;
  for (let i = layers.length - 1; i >= 0; i--) {
    const L = layers[i];
    if (!L.visible || L.lock) continue;
    if (mx >= L.x * S && mx <= (L.x + L.w) * S && my >= L.y * S && my <= (L.y + L.h) * S) return L;
  }
  return null;
}

function evPos(e) {
  const r = cv.getBoundingClientRect();
  return [(e.clientX - r.left) * (VW / r.width), (e.clientY - r.top) * (VH / r.height)];
}

cv.addEventListener("pointerdown", (e) => {
  if (!state.scene) return;
  cv.setPointerCapture(e.pointerId);
  const [mx, my] = evPos(e);
  const hi = hitHandle(mx, my);
  const L = state.sel && layerById(state.sel);
  if (hi >= 0 && L) {
    state.drag = { kind: "resize", h: hi, L, sx: mx, sy: my,
      ox: L.x, oy: L.y, ow: L.w, oh: L.h, aspect: (hi % 2 === 0) && (L.type === "qr" || L.type === "image") };
  } else {
    const hit = hitLayer(mx, my);
    state.sel = hit ? hit.id : null;
    if (hit) state.drag = { kind: "move", L: hit, sx: mx, sy: my, ox: hit.x, oy: hit.y };
    else state.drag = null;
    renderPanels();
  }
  renderEditor();
});
cv.addEventListener("pointermove", (e) => {
  if (!state.drag) return;
  const [mx, my] = evPos(e);
  const d = state.drag, dx = (mx - d.sx) / S, dy = (my - d.sy) / S;
  if (d.kind === "move") {
    d.L.x = Math.round(snapVal(d.ox + dx, [0, CW / 2 - d.L.w / 2, CW - d.L.w]));
    d.L.y = Math.round(snapVal(d.oy + dy, [0, CH / 2 - d.L.h / 2, CH - d.L.h, 540 - d.L.h / 2]));
  } else {
    let { ow, oh, ox, oy } = d;
    const min = 20;
    const setW = (v) => { d.L.w = Math.max(min, Math.round(v)); };
    const setH = (v) => { d.L.h = Math.max(min, Math.round(v)); };
    if ([0, 1, 2].includes(d.h)) { setH(oh - 0 + (d.h === 1 ? 0 : 0)); } // top row handled below
    // corners + edges
    const left = [0, 6, 7].includes(d.h), right = [2, 3, 4].includes(d.h);
    const top = [0, 1, 2].includes(d.h), bot = [4, 5, 6].includes(d.h);
    let nw = ow, nh = oh, nx = ox, ny = oy;
    if (right) nw = ow + dx;
    if (left) { nw = ow - dx; nx = ox + dx; }
    if (bot) nh = oh + dy;
    if (top) { nh = oh - dy; ny = oy + dy; }
    if (d.aspect && nw > 0 && nh > 0) {
      const side = Math.max(nw, nh * (ow / oh));
      nh = side * (oh / ow); nw = side;
      if (left) nx = ox + (ow - nw);
      if (top) ny = oy + (oh - nh);
    }
    d.L.w = Math.max(min, Math.round(nw));
    d.L.h = Math.max(min, Math.round(nh));
    d.L.x = Math.round(nx); d.L.y = Math.round(ny);
  }
  renderEditor();
});
cv.addEventListener("pointerup", () => {
  if (state.drag) { state.drag = null; markDirty(); renderPanels(); }
});
function snapVal(v, targets) {
  for (const t of targets) if (Math.abs(v - t) * S < 9) return t;
  return v;
}

document.addEventListener("keydown", (e) => {
  if (/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || "")) return;
  const L = state.sel && layerById(state.sel);
  if (!L) return;
  const step = e.shiftKey ? 10 : 2;
  if (e.key === "Delete" || e.key === "Backspace") { deleteLayer(L.id); e.preventDefault(); }
  else if (e.key.startsWith("Arrow")) {
    if (e.key === "ArrowLeft") L.x -= step;
    if (e.key === "ArrowRight") L.x += step;
    if (e.key === "ArrowUp") L.y -= step;
    if (e.key === "ArrowDown") L.y += step;
    markDirty(); renderEditor(); syncPropInputs(); e.preventDefault();
  } else if ((e.ctrlKey || e.metaKey) && e.key === "d") { duplicateLayer(L.id); e.preventDefault(); }
  else if (e.key === "Escape") { state.sel = null; renderAll(); }
});

/* ═══════════════ QR health (rule 5: accurate judgment) ═══════════════ */
function luminance(hex) {
  const [r, g, b] = hexRGB(hex);
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255;
}
function qrHealth() {
  const qrs = (state.scene?.layers || []).filter((l) => (l.type === "qr" || l.qrImage) && l.visible);
  if (!qrs.length) return { level: "", msg: "QR: none on screen" };
  const warns = [];
  let customCount = 0;
  for (const q of qrs) {
    if (q.qrMode === "custom") {
      customCount++;
      if (!q.src) warns.push("Own QR image is missing — upload the picture");
      if (Math.min(q.w, q.h) < 220) warns.push(`QR “${q.name}” is small — phones may struggle (≥220px)`);
      if (q.x < 0 || q.y < 0 || q.x + q.w > CW || q.y + q.h > CH) warns.push("QR is partly off-screen");
      continue;
    }
    if (q.qrImage) {
      warns.push("Uploaded QR image: scan True output with your phone before going live");
    } else if (!q.content?.trim()) warns.push("QR text is empty");
    if (Math.min(q.w, q.h) < 220) warns.push(`QR “${q.name}” is small — phones may struggle (≥220px)`);
    const fgL = luminance(q.transparentBg ? q.fg : q.fg), bgL = luminance(q.showBox === false || q.transparentBg ? "#ffffff" : q.bg);
    if (!q.qrImage && Math.abs(fgL - bgL) < 0.4) warns.push("QR contrast is low — dark code on light card scans best");
    if (q.x < 0 || q.y < 0 || q.x + q.w > CW || q.y + q.h > CH) warns.push("QR is partly off-screen");
  }
  if (!warns.length) {
    if (customCount && customCount === qrs.length)
      return { level: "ok", msg: `QR: own image — check it scans ✓ (${qrs.length})` };
    return { level: "ok", msg: `QR: looks scannable ✓ (${qrs.length})` };
  }
  return { level: "warn", msg: "QR: " + warns[0], warns };
}
function updateHealth() {
  const q = qrHealth();
  const c = $("chipQR");
  c.className = "chip " + (q.level || "");
  c.textContent = q.msg;
  $("sbQr").textContent = q.msg;
  const a = $("chipAlpha");
  const alpha = state.scene?.canvas?.alpha !== false;
  a.textContent = alpha ? "Overlay: transparent top" : "Overlay: solid picture";
  a.className = "chip";
  const sc = state.status?.scale || "1080p";
  const res = { "1080p": "1920×1080", "720p": "1280×720", "540p": "960×540" }[sc];
  $("chipSize").textContent = "Output: " + res;
  $("canvasMeta").textContent = "Canvas 1920 × 1080 → NDI " + res;
  const empty = !state.scene?.layers.length;
  $("emptyHint").hidden = !empty;
  // steps indicator
  const steps = document.querySelectorAll(".step");
  steps.forEach((s) => s.classList.remove("done"));
  if ((state.scene?.layers.length || 0) > 0) steps[0].classList.add("done");
  if (q.level === "ok") steps[1].classList.add("done");
  if (state.status?.live) steps[2].classList.add("done");
}

/* ═══════════════ layers panel ═══════════════ */
const TYPE_DOT = { qr: "#35d07f", text: "#6aa8ff", image: "#c792ea", background: "#f5b301", shape: "#ff8a5c" };
const TYPE_LABEL = { qr: "QR", text: "Text", image: "Logo", background: "BG", shape: "Bar" };

function renderLayers() {
  const box = $("layerList");
  box.innerHTML = "";
  const layers = [...(state.scene?.layers || [])].reverse(); // top first
  for (const L of layers) {
    const d = document.createElement("div");
    d.className = "layer" + (L.id === state.sel ? " sel" : "");
    d.innerHTML = `<span class="dot" style="background:${TYPE_DOT[L.type] || "#888"}"></span>
      <span class="nm" title="${TYPE_LABEL[L.type] || L.type} — ${L.name || ""}">${L.name || L.type}</span>`;
    const mk = (t, title, fn, off) => {
      const b = document.createElement("button");
      b.textContent = t; b.title = title;
      if (off) b.classList.add("off");
      b.onclick = (e) => { e.stopPropagation(); fn(); };
      d.appendChild(b);
    };
    mk(L.visible ? "👁" : "🚫", "Show / hide", () => { L.visible = !L.visible; markDirty(); }, !L.visible);
    mk("🔒", "Lock / unlock", () => { L.lock = !L.lock; renderAll(); }, !L.lock);
    mk("▲", "Bring forward", () => moveLayer(L.id, 1));
    mk("▼", "Send backward", () => moveLayer(L.id, -1));
    d.onclick = () => { state.sel = L.id; renderAll(); };
    box.appendChild(d);
  }
}
function moveLayer(id, dir) {
  const ls = state.scene.layers, i = ls.findIndex((l) => l.id === id);
  const j = i + dir;
  if (i < 0 || j < 0 || j >= ls.length) return;
  [ls[i], ls[j]] = [ls[j], ls[i]];
  markDirty();
}
function deleteLayer(id) {
  state.scene.layers = state.scene.layers.filter((l) => l.id !== id);
  if (state.sel === id) state.sel = null;
  markDirty(); renderPanels();
}
function duplicateLayer(id) {
  const ls = state.scene.layers, i = ls.findIndex((l) => l.id === id);
  if (i < 0) return;
  const c = JSON.parse(JSON.stringify(ls[i]));
  c.id = uid(); c.name = (c.name || c.type) + " copy";
  c.x = Math.min(CW - c.w, c.x + 40); c.y = Math.min(CH - c.h, c.y + 40);
  ls.splice(i + 1, 0, c);
  state.sel = c.id;
  markDirty(); renderPanels();
}

/* ═══════════════ add ═══════════════ */
document.querySelectorAll(".add").forEach((b) =>
  b.onclick = () => addLayer(b.dataset.add));
document.querySelectorAll(".preset").forEach((b) =>
  b.onclick = async () => {
    if (state.scene.layers.length && !confirm("Replace the current design with the preset?")) return;
    try {
      // Shared server presets (same source the desktop app uses).
      state.scene = await api("/api/presets/" + b.dataset.preset, { method: "POST" });
      state.sel = state.scene.layers.find((l) => l.type === "qr")?.id || null;
      syncChrome(); markDirty(false); renderPanels();
    } catch (e) { alert("Couldn't apply preset: " + e.message); }
  });

function addLayer(kind) {
  const cx = CW / 2, cy = CH / 2;
  let L = null;
  if (kind === "qr") L = { id: uid(), type: "qr", name: "QR code", x: cx - 190, y: cy - 100, w: 380, h: 380,
    opacity: 1, visible: true, lock: false, qrMode: "generated", src: "", content: "https://example.com", fg: "#0d1326",
    bg: "#ffffff", transparentBg: false, showBox: true, radius: 28, pad: 22 };
  else if (kind === "text") L = { id: uid(), type: "text", name: "Heading", x: cx - 400, y: cy - 60, w: 800, h: 140,
    opacity: 1, visible: true, lock: false, text: "New heading — click to edit", fontSize: 84,
    color: "#ffffff", bold: true, align: "center" };
  else if (kind === "qr-image") { openUpload((info) => {
      insertLayer({ id: uid(), type: "image", qrImage: true, name: "Uploaded QR code",
        x: cx - 190, y: cy - 100, w: 380, h: 380,
        opacity: 1, visible: true, lock: false, src: info.src, fit: "contain" });
    }); return; }
  else if (kind === "image") { openUpload((info) => {
      const W = 420, H = Math.max(80, Math.round(420 * (info.h / Math.max(1, info.w))));
      insertLayer({ id: uid(), type: "image", name: "Logo", x: CW - W - 90, y: CH - H - 90, w: W, h: H,
        opacity: 1, visible: true, lock: false, src: info.src, fit: "contain" });
    }); return; }
  else if (kind === "background") { openUpload((info) => {
      insertLayer({ id: uid(), type: "background", name: "Background photo", x: 0, y: 570, w: 1920, h: 510,
        opacity: 0.3, visible: true, lock: false, src: info.src, fit: "cover", color: "#0d1326" });
    }); return; }
  else if (kind === "shape") L = shapeLayer({ id: uid(), name: "Bar", x: 120, y: CH - 160, w: 700, h: 26, fill: "#f5b301" });
  if (L) insertLayer(L);
}
function insertLayer(L) {
  state.scene.layers.push(L);
  state.sel = L.id;
  markDirty(); renderPanels();
}

/* uploads */
let uploadCb = null;
function openUpload(cb) {
  uploadCb = cb;
  $("fileInput").click();
}
$("fileInput").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  e.target.value = "";
  if (!f) return;
  const fd = new FormData();
  fd.append("file", f);
  try {
    const r = await fetch("/api/upload", { method: "POST", body: fd });
    if (!r.ok) throw new Error(await r.text());
    const info = await r.json();
    uploadCb && uploadCb(info);
  } catch (err) { alert("Couldn't use that image: " + err.message); }
});

/* ═══════════════ props panel ═══════════════ */
const SWATCHES = ["#ffffff", "#0d1326", "#f5b301", "#35d07f", "#ff5d5d", "#6aa8ff", "#c792ea", "#101a33", "#c9d2ea"];

function swatchRow(cur, onPick) {
  const d = document.createElement("div");
  d.className = "swatches";
  for (const c of SWATCHES) {
    const b = document.createElement("button");
    b.className = "sw" + (c.toLowerCase() === (cur || "").toLowerCase() ? " on" : "");
    b.style.background = c; b.title = c;
    b.onclick = () => onPick(c);
    d.appendChild(b);
  }
  const custom = document.createElement("input");
  custom.type = "color"; custom.value = /^#[0-9a-f]{6}$/i.test(cur || "") ? cur : "#ffffff";
  custom.title = "Custom color";
  custom.oninput = () => onPick(custom.value);
  d.appendChild(custom);
  return d;
}
function numRow(label, val, min, max, step, onV) {
  const d = document.createElement("div");
  d.className = "row";
  d.innerHTML = `<label class="lbl" style="width:64px">${label}</label>`;
  const r = document.createElement("input");
  r.type = "range"; r.min = min; r.max = max; r.step = step; r.value = val; r.style.flex = "1";
  const n = document.createElement("input");
  n.type = "number"; n.min = min; n.max = max; n.step = step; n.value = val; n.style.width = "76px";
  r.oninput = () => { n.value = r.value; onV(+r.value); };
  n.onchange = () => { r.value = n.value; onV(+n.value); };
  d.append(r, n);
  return d;
}
function segRow(options, cur, onPick) {
  const d = document.createElement("div");
  d.className = "seg";
  for (const [v, label] of options) {
    const b = document.createElement("button");
    b.textContent = label;
    if (v === cur) b.classList.add("on");
    b.onclick = () => onPick(v);
    d.appendChild(b);
  }
  return d;
}

function renderProps() {
  const box = $("props");
  box.innerHTML = "";
  const L = state.sel && layerById(state.sel);
  if (!L) {
    $("propsTitle").textContent = "Nothing selected";
    box.innerHTML = `<p class="muted">Click anything on the screen to edit its text, colors and size here.</p>`;
    return;
  }
  $("propsTitle").textContent = `${TYPE_LABEL[L.type] || L.type} — ${L.name || ""}`;

  const nameRow = document.createElement("div");
  nameRow.className = "row";
  nameRow.innerHTML = `<label class="lbl" style="width:64px">Label</label>`;
  const nm = document.createElement("input");
  nm.value = L.name || "";
  nm.oninput = () => { L.name = nm.value; markDirty(false); renderLayers(); };
  nameRow.appendChild(nm);
  box.appendChild(nameRow);

  if (L.type === "qr") {
    box.appendChild(group("QR source", (g) => {
      g.appendChild(segRow([["generated", "Auto QR"], ["custom", "My own QR image"]], L.qrMode || "generated",
        (v) => {
          L.qrMode = v;
          if (v === "custom" && !L.src) {
            renderProps();
            openUpload((info) => { L.src = info.src; markDirty(); renderPanels(); });
          } else {
            markDirty(); renderProps();
          }
        }));
      if ((L.qrMode || "generated") === "custom") {
        if (L.src) {
          const im = document.createElement("img");
          im.className = "thumb"; im.src = srcToUrl(L.src);
          g.appendChild(im);
        }
        const row = document.createElement("div");
        row.className = "row";
        const ch = document.createElement("button");
        ch.className = "btn small"; ch.textContent = L.src ? "Replace image…" : "Upload QR image…";
        ch.onclick = () => openUpload((info) => { L.src = info.src; markDirty(); renderPanels(); });
        row.appendChild(ch);
        g.appendChild(row);
        const hint = document.createElement("p");
        hint.className = "muted small";
        hint.textContent = "Your picture is shown as-is on air. Make sure it scans before going live.";
        g.appendChild(hint);
      }
    }));
    if ((L.qrMode || "generated") === "generated") {
    box.appendChild(group("Where should it go?", (g) => {
      const t = document.createElement("textarea");
      t.value = L.content || ""; t.placeholder = "https://…  or  WIFI:T:WPA;S:Name;P:pass;;  or plain text";
      t.oninput = () => { L.content = t.value; markDirty(); };
      g.appendChild(t);
      const hint = document.createElement("p");
      hint.className = "muted small";
      hint.innerHTML = `For Wi-Fi use: <code>WIFI:T:WPA;S:YourName;P:password;;</code>`;
      g.appendChild(hint);
    }));
    }
    box.appendChild(group("Look", (g) => {
      if ((L.qrMode || "generated") === "generated") {
      g.appendChild(lbl("Code color"));
      g.appendChild(swatchRow(L.fg, (c) => { L.fg = c; markDirty(); renderProps(); }));
      }
      const chk = document.createElement("label");
      chk.className = "chk";
      chk.innerHTML = `<input type="checkbox" ${L.showBox === false || L.transparentBg ? "" : "checked"}> White card behind the code <span class="hint">scans best</span>`;
      chk.querySelector("input").onchange = (e) => {
        const on = e.target.checked;
        L.showBox = on; L.transparentBg = !on;
        markDirty(); renderProps();
      };
      g.appendChild(chk);
      if (L.showBox !== false) {
        g.appendChild(lbl("Card color"));
        g.appendChild(swatchRow(L.bg, (c) => { L.bg = c; markDirty(); renderProps(); }));
        g.appendChild(numRow("Corners", L.radius ?? 28, 0, 80, 1, (v) => { L.radius = v; markDirty(); }));
      }
    }));
  }

  if (L.type === "text") {
    box.appendChild(group("Words", (g) => {
      const t = document.createElement("textarea");
      t.value = L.text || "";
      t.oninput = () => { L.text = t.value; markDirty(); };
      g.appendChild(t);
      g.appendChild(segRow([["left", "Left"], ["center", "Center"], ["right", "Right"]], L.align || "left",
        (v) => { L.align = v; markDirty(); renderProps(); }));
      const b = document.createElement("label");
      b.className = "chk";
      b.innerHTML = `<input type="checkbox" ${L.bold ? "checked" : ""}> Bold`;
      b.querySelector("input").onchange = (e) => { L.bold = e.target.checked; markDirty(); };
      g.appendChild(b);
      g.appendChild(numRow("Size", L.fontSize || 64, 20, 180, 1, (v) => { L.fontSize = v; markDirty(); }));
    }));
    box.appendChild(group("Color", (g) => {
      g.appendChild(swatchRow(L.color, (c) => { L.color = c; markDirty(); renderProps(); }));
    }));
  }

  if (L.type === "image") {
    box.appendChild(group("Picture", (g) => {
      if (L.src) {
        const im = document.createElement("img");
        im.className = "thumb"; im.src = srcToUrl(L.src);
        g.appendChild(im);
      }
      const row = document.createElement("div");
      row.className = "row";
      const ch = document.createElement("button");
      ch.className = "btn small"; ch.textContent = L.src ? "Replace…" : "Choose…";
      ch.onclick = () => openUpload((info) => {
        const ratio = info.h / Math.max(1, info.w);
        L.src = info.src;
        L.h = Math.round(L.w * ratio);
        markDirty(); renderPanels();
      });
      row.appendChild(ch);
      g.appendChild(row);
      g.appendChild(lbl("Place in a corner"));
      const cor = document.createElement("div");
      cor.className = "corners";
      [["↖ Top left", 60, 60], ["↗ Top right", CW - L.w - 60, 60],
       ["↙ Bottom left", 60, CH - L.h - 60], ["↘ Bottom right", CW - L.w - 60, CH - L.h - 60]
      ].forEach(([t, x, y]) => {
        const b = document.createElement("button");
        b.textContent = t;
        b.onclick = () => { L.x = Math.round(x); L.y = Math.round(y); markDirty(); renderEditor(); syncPropInputs(); };
        cor.appendChild(b);
      });
      g.appendChild(cor);
      g.appendChild(segRow([["contain", "Fit inside"], ["cover", "Fill box"], ["stretch", "Stretch"]], L.fit || "contain",
        (v) => { L.fit = v; markDirty(); renderProps(); }));
    }));
  }

  if (L.type === "background") {
    box.appendChild(group("Picture", (g) => {
      if (L.src) {
        const im = document.createElement("img");
        im.className = "thumb"; im.src = srcToUrl(L.src);
        g.appendChild(im);
      }
      const row = document.createElement("div");
      row.className = "row";
      const ch = document.createElement("button");
      ch.className = "btn small"; ch.textContent = "Change…";
      ch.onclick = () => openUpload((info) => { L.src = info.src; markDirty(); renderPanels(); });
      const rm = document.createElement("button");
      rm.className = "btn small ghost"; rm.textContent = "Remove";
      rm.onclick = () => { L.src = ""; markDirty(); renderPanels(); };
      row.append(ch, rm);
      g.appendChild(row);
      g.appendChild(numRow("Dim (see-through)", Math.round((L.opacity ?? 1) * 100), 0, 100, 1,
        (v) => { L.opacity = v / 100; markDirty(); }));
      g.appendChild(lbl("Tint color (behind photo)"));
      g.appendChild(swatchRow(L.color, (c) => { L.color = c; markDirty(); renderProps(); }));
    }));
  }

  if (L.type === "shape") {
    box.appendChild(group("Look", (g) => {
      g.appendChild(swatchRow(L.fill, (c) => { L.fill = c; markDirty(); renderProps(); }));
      g.appendChild(numRow("Corners", L.radius || 0, 0, 120, 1, (v) => { L.radius = v; markDirty(); }));
    }));
  }

  // common geometry
  box.appendChild(group("Position & size", (g) => {
    g.appendChild(numRow("Width", Math.round(L.w), 20, CW, 1, (v) => { L.w = v; markDirty(); renderEditor(); }));
    g.appendChild(numRow("Height", Math.round(L.h), 20, CH, 1, (v) => { L.h = v; markDirty(); renderEditor(); }));
    if (L.type !== "background")
      g.appendChild(numRow("Fade", Math.round((L.opacity ?? 1) * 100), 10, 100, 1,
        (v) => { L.opacity = v / 100; markDirty(); }));
    const row = document.createElement("div");
    row.className = "row";
    const up = btn("▲ Forward", () => moveLayer(L.id, 1));
    const dn = btn("▼ Backward", () => moveLayer(L.id, -1));
    const du = btn("⧉ Duplicate", () => duplicateLayer(L.id));
    const del = btn("🗑 Delete", () => { if (confirm(`Remove “${L.name || L.type}”?`)) deleteLayer(L.id); });
    del.classList.add("danger");
    row.append(up, dn);
    g.appendChild(row);
    const row2 = document.createElement("div");
    row2.className = "row";
    row2.append(du, del);
    g.appendChild(row2);
  }));
}
function group(title, build) {
  const d = document.createElement("div");
  d.className = "pgroup";
  d.innerHTML = `<h4>${title}</h4>`;
  build(d);
  return d;
}
function lbl(t) { const p = document.createElement("p"); p.className = "lbl"; p.style.margin = "8px 0 2px"; p.textContent = t; return p; }
function btn(t, fn) { const b = document.createElement("button"); b.className = "btn small ghost"; b.textContent = t; b.onclick = fn; return b; }
function syncPropInputs() { renderProps(); }

/* ═══════════════ chrome (canvas/ndi/templates/mode) ═══════════════ */
function syncChrome() {
  $("tplName").value = state.scene.name || "";
  $("chkAlpha").checked = state.scene.canvas?.alpha !== false;
  $("bgColor").value = state.scene.canvas?.bgColor || "#000000";
  document.body.classList.toggle("simple", state.mode === "simple");
  document.body.classList.toggle("pro", state.mode === "pro");
  $("modeSimple").classList.toggle("on", state.mode === "simple");
  $("modePro").classList.toggle("on", state.mode === "pro");
}
$("tplName").addEventListener("input", (e) => { state.scene.name = e.target.value; markDirty(false); });
$("chkAlpha").addEventListener("change", (e) => {
  state.scene.canvas.alpha = e.target.checked;
  markDirty();
});
$("bgColor").addEventListener("input", (e) => { state.scene.canvas.bgColor = e.target.value; markDirty(); });
$("modeSimple").onclick = () => { state.mode = "simple"; syncChrome(); };
$("modePro").onclick = () => { state.mode = "pro"; syncChrome(); };
$("chkGuides").onchange = (e) => { state.showGuides = e.target.checked; renderEditor(); };
$("chkTrue").onchange = (e) => {
  state.trueOut = e.target.checked;
  $("trueImg").hidden = !state.trueOut;
  if (state.trueOut) refreshTrue();
};
$("btnTrueRefresh").onclick = () => refreshTrue();
function scheduleTrueRefresh() {
  clearTimeout(state.trueTimer);
  state.trueTimer = setTimeout(refreshTrue, 1500);
}
function refreshTrue() {
  if (!state.trueOut) return;
  $("trueImg").src = "/api/preview.png?w=960&h=540&ts=" + Date.now();
}
$("trueImg").addEventListener("load", () => { /* pixel-exact server render ready */ });

/* layout presets */
document.querySelectorAll("#layoutSeg button").forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll("#layoutSeg button").forEach((x) => x.classList.remove("on"));
    b.classList.add("on");
    applyLayout(b.dataset.layout);
  };
});
function ensurePanel() {
  let p = state.scene.layers.find((l) => l.id === "bg-panel");
  if (!p) {
    p = shapeLayer({ id: "bg-panel", name: "Bottom panel", fill: "#0d1326" });
    state.scene.layers.unshift(p);
  }
  let a = state.scene.layers.find((l) => l.id === "accent");
  if (!a) {
    a = shapeLayer({ id: "accent", name: "Accent bar", fill: "#f5b301" });
    state.scene.layers.splice(1, 0, a);
  }
  let ph = state.scene.layers.find((l) => l.id === "bg-photo");
  if (!ph) {
    ph = { id: "bg-photo", type: "background", name: "Background photo", x: 0, y: 570, w: 1920, h: 510,
      opacity: 0.28, visible: true, lock: false, src: "asset:default-bg.png", fit: "cover", color: "#0d1326" };
    state.scene.layers.splice(2, 0, ph);
  }
  return { p, a, ph };
}
function applyLayout(kind) {
  const { p, a, ph } = ensurePanel();
  if (kind === "lower") {
    Object.assign(p, { x: 0, y: 560, w: 1920, h: 520 });
    Object.assign(a, { x: 0, y: 560, w: 1920, h: 10, visible: true });
    Object.assign(ph, { x: 0, y: 570, w: 1920, h: 510, visible: true });
    state.scene.canvas.alpha = true;
  } else if (kind === "half") {
    Object.assign(p, { x: 0, y: 540, w: 1920, h: 540 });
    Object.assign(a, { x: 0, y: 540, w: 1920, h: 10, visible: true });
    Object.assign(ph, { x: 0, y: 550, w: 1920, h: 530, visible: true });
    state.scene.canvas.alpha = true;
  } else {
    Object.assign(p, { x: 0, y: 0, w: 1920, h: 1080 });
    Object.assign(a, { x: 0, y: 0, w: 1920, h: 10, visible: true });
    Object.assign(ph, { x: 0, y: 10, w: 1920, h: 1070, visible: true });
    state.scene.canvas.alpha = false;
  }
  syncChrome(); markDirty(); renderPanels();
}

/* ═══════════════ NDI live ═══════════════ */
$("btnLive").onclick = async () => {
  const live = !state.status?.live;
  if (live && qrHealth().level === "warn" && !confirm(qrHealth().msg + "\n\nGo live anyway?")) return;
  try {
    const s = await api("/api/live", { method: "POST",
      body: JSON.stringify({ live, ndiName: $("ndiName").value,
        fps: +$("ndiFps").value, scale: $("ndiScale").value, alpha: $("ndiAlpha").checked }) });
    state.status = s;
    renderStatus();
  } catch (e) { alert("Broadcast problem: " + e.message); }
};
$("ndiName").addEventListener("input", (e) => { $("ndiNameEcho").textContent = e.target.value || "QRReplace"; });
$("btnDiag").onclick = async () => {
  try {
    const n = await api("/api/system/network");
    $("netList").innerHTML = "This computer: " + n.urls.map((u) => `<div><code>${u}</code></div>`).join("") +
      `<div style="margin-top:4px">Receivers must be on the same network.</div>`;
  } catch (e) { $("netList").textContent = "Couldn't list addresses."; }
};

async function pollStatus() {
  try {
    state.status = await api("/api/status");
    renderStatus();
  } catch (e) { /* server hiccup — keep editing locally */ }
}
function renderStatus() {
  const s = state.status;
  if (!s) return;
  const pill = $("livePill");
  pill.classList.toggle("on", s.live);
  pill.querySelector("span").textContent = s.live ? `● LIVE · ${s.ndiName}` : "Off air";
  const b = $("btnLive");
  b.textContent = s.live ? "■ Stop" : "● Go Live";
  b.classList.toggle("off", s.live);
  $("sbNdi").innerHTML = s.live
    ? `<i></i> NDI “${s.ndiName}” · ${s.actualFps} fps · ${s.connections} viewer(s)`
    : `<i></i> NDI off`;
  $("sbNdi").classList.toggle("on", s.live);
  $("stView").textContent = s.connections ?? 0;
  $("stFps").textContent = s.live ? `${s.actualFps} fps` : "–";
  $("stFrames").textContent = (s.framesSent || 0).toLocaleString();
  if (!document.activeElement || document.activeElement.id !== "ndiName") $("ndiName").value = s.ndiName || "QRReplace";
  updateHealth();
}

/* ═══════════════ templates ═══════════════ */
$("btnSave").onclick = async () => {
  const name = ($("saveName").value || state.scene.name || "design").trim();
  if (!name) return;
  await api("/api/templates/" + encodeURIComponent(name), { method: "POST" });
  $("saveName").value = "";
  loadTemplates();
};
async function loadTemplates() {
  try {
    const { templates } = await api("/api/templates");
    const box = $("tplList");
    box.innerHTML = templates.length ? "" : `<p class="muted small">No saved designs yet.</p>`;
    for (const t of templates) {
      if (t === "autosave") continue;
      const d = document.createElement("div");
      d.className = "tpl-item";
      d.innerHTML = `<span></span>`;
      d.querySelector("span").textContent = t;
      const load = document.createElement("button");
      load.textContent = "Open"; load.title = "Load this design";
      load.onclick = async () => {
        if (state.scene.layers.length && !confirm(`Open “${t}”? Unsaved tweaks will be lost.`)) return;
        state.scene = await api("/api/templates/" + encodeURIComponent(t));
        state.sel = null;
        syncChrome(); markDirty(false); renderPanels();
      };
      const del = document.createElement("button");
      del.textContent = "✕"; del.title = "Delete";
      del.onclick = async () => {
        if (!confirm(`Delete “${t}”?`)) return;
        await fetch("/api/templates/" + encodeURIComponent(t), { method: "DELETE" });
        loadTemplates();
      };
      d.append(load, del);
      box.appendChild(d);
    }
  } catch (e) { /* ignore */ }
}
$("btnExport").onclick = () => { window.open("/api/export.png", "_blank"); };

/* ═══════════════ help ═══════════════ */
$("btnHelp").onclick = () => { $("helpModal").hidden = false; };
$("btnHelpClose").onclick = () => { $("helpModal").hidden = true; };
$("helpModal").addEventListener("click", (e) => { if (e.target.id === "helpModal") e.target.hidden = true; });

/* ═══════════════ boot ═══════════════ */
function renderPanels() { renderLayers(); renderProps(); }
function renderAll() { renderEditor(); renderPanels(); }

(async function boot() {
  document.body.classList.add("simple");
  state.scene = await api("/api/scene");
  state.sel = state.scene.layers.find((l) => l.type === "qr")?.id || null;
  try { state.status = await api("/api/status"); } catch (e) { state.status = null; }
  syncChrome();
  renderAll();
  renderStatus();
  loadTemplates();
  setInterval(pollStatus, 2000);
})();
