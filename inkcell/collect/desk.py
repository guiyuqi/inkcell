# -*- coding: utf-8 -*-
"""TOOLS/writing_desk.py —— 本地"写字台"：一屏 4 个字，淡参考打底，整批入库。

    ./.venv/bin/python TOOLS/writing_desk.py --tag corpus --pass-id 1
    # Windows 浏览器打开 http://127.0.0.1:8765

快捷键：
    空格 / 回车   保存这一屏 4 个，进下一屏
    z / Ctrl+Z    撤回：先撤笔画，笔画撤完了再撤上一屏
    PageDown      跳过这一屏（不保存）
    PageUp        回到上一屏
    Backspace     清空当前格
    h             描红开关
"""
from __future__ import annotations

import argparse
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from inkcell.paths import load_project

PER_SCREEN = 4
CELL_MM = 12.0
INK_PX = 320

PAGE = r"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<meta name="mobile-web-app-capable" content="yes">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="icon" href="/icon-192.png">
<link rel="apple-touch-icon" href="/icon-192.png">
<title>写字台</title>
<style>
  :root { --ink:#14151a; --paper:#fdfdfb; }
  * { box-sizing:border-box; -webkit-user-select:none; user-select:none;
      -webkit-tap-highlight-color:transparent; }
  html,body { margin:0; background:#22252a; color:#e9eaec;
              font-family:system-ui,"Microsoft YaHei",sans-serif; }
  html { height:100%; }
  /* 正好一屏：不能滚动，避免写字时误触往下翻。
     注意别用 100dvh——这个 WebView 里不生效，flex 就分不到高度、画布会塌成 0。*/
  body { position:fixed; inset:0; height:100%; overflow:hidden;
         overscroll-behavior:none; touch-action:manipulation; }
  #primary { height:100%; display:flex; flex-direction:column; min-height:0; }
  /* "更多"不再是屏幕外的长页，改成浮层，点"更多"才弹出来 */
  #more { position:fixed; inset:auto 0 0 0; max-height:70vh; overflow-y:auto;
          background:#1b1e22; border-top:1px solid #3a3f46; padding:6px 14px 24px;
          display:none; z-index:30; }
  #more.open { display:block; }
  #quick #bMore { background:#33383f; border-color:#4a5058; }

  #meta { padding:10px 14px 6px; font-size:14px; color:#b8bcc3; line-height:1.5; }
  #quick { display:flex; align-items:center; gap:8px; padding:0 14px 6px; }
  #quick button { height:38px; padding:0 14px; border-radius:9px; font-size:14px;
                  border:1px solid #3b82c4; background:#2f6fa8; color:#eef1f4; }
  #quick #bReset { background:#4a2b2b; border-color:#6b3a3a; }
  #quick #bClear4 { background:#3a3f46; border-color:#4a5058; flex:0 0 auto; }
  #quick span { font-size:11.5px; color:#6d737a; flex:1; text-align:right; }
  #meta b { color:#fff; }
  #bar { margin:0 14px 6px; height:6px; background:#3a3f46; border-radius:4px; overflow:hidden; }
  #barIn { height:100%; width:0; background:#5aa9e6; transition:width .2s; }

  #stage { flex:1 1 0; display:flex; align-items:center; justify-content:center;
           min-height:0; overflow:hidden; padding:0; }
  #view { background:var(--paper); border-radius:12px; touch-action:none; display:block;
          box-shadow:0 8px 28px rgba(0,0,0,.4); }

  /* 两个大按钮：左保存 右撤回 */
  #big { flex:0 0 auto; display:flex; gap:10px; padding:2px 12px 6px; }
  #big button { flex:1; height:96px; border-radius:14px; font-size:24px; font-weight:600;
                border:1px solid #4a5058; background:#33383f; color:#eef1f4;
                display:flex; align-items:center; justify-content:center; }
  #big button:active { transform:scale(.985); }
  #bNext { background:#2f6fa8; border-color:#3b82c4; }
  #bUndo { background:#3a3f46; }
  #big button:disabled { opacity:.45; }
  /* 导航行：上一屏 / 重写本屏（挨着大按钮，拇指够得到） */
  #nav { flex:0 0 auto; display:flex; gap:10px; padding:0 12px 4px; }
  #nav button { flex:1; height:50px; border-radius:12px; font-size:17px;
                border:1px solid #4a5058; background:#2c3036; color:#dfe3e8; }
  #nav #bRewrite { background:#3d2f2f; border-color:#5c4040; }
  #nav button:disabled { opacity:.45; }
  #ghostTip { flex:0 0 auto; font-size:12px; color:#6d737a; text-align:center;
              padding:0 0 10px; }
  #meta, #bar, #quick { flex:0 0 auto; }

  /* 下面是"不常用"，默认在屏幕外，往下滑才看到 */
  #more { padding:6px 14px 40px; border-top:1px solid #33383f; }
  #more h4 { margin:14px 0 8px; font-size:13px; color:#8f959d; font-weight:500; }
  #ctrls { display:flex; align-items:center; gap:10px; font-size:14px; color:#c3c8cf;
           flex-wrap:wrap; }
  input[type=range] { flex:1; min-width:120px; }
  #btns { display:flex; flex-wrap:wrap; gap:10px; }
  #btns button { flex:1 1 30%; height:56px; border-radius:12px; font-size:15px;
                 border:1px solid #4a5058; background:#2c3036; color:#dfe3e8; }
  #diag { font-size:12px; color:#8f959d; font-family:ui-monospace,Consolas,monospace;
          padding:10px 0 0; line-height:1.6; }
  #toast { position:fixed; left:50%; top:46%; transform:translate(-50%,-50%);
           font-size:30px; color:#5aa9e6; pointer-events:none; opacity:0;
           transition:opacity .15s; text-shadow:0 2px 12px #000; }
  #err { position:fixed; left:0; right:0; bottom:0; background:#7a1f1f; color:#fff;
         font:12.5px/1.5 monospace; padding:8px 12px; white-space:pre-wrap; z-index:99; }
</style></head>
<body>
<div id="primary">
  <div id="meta"></div>
  <div id="bar"><div id="barIn"></div></div>
  <div id="quick">
    <button id="bClear4">清屏</button>
    <button id="bExport">导出</button>
    <button id="bMore">更多</button>
    <span id="offlineTip">离线可用</span>
  </div>
  <div id="stage"><canvas id="view" width="470" height="470"></canvas></div>
  <div id="big">
    <button id="bNext">保存 · 下一屏</button>
    <button id="bUndo">撤回一笔</button>
  </div>
  <div id="nav">
    <button id="bPrev">上一屏</button>
    <button id="bRewrite">重写本屏</button>
  </div>
  <div id="ghostTip">灰字 = 这一格之前已经写过</div>
</div>

<div id="more">
  <h4>笔迹（点"更多"收起）</h4>
  <div id="ctrls">
    <span>粗细</span><input type="range" id="wid" min="0.4" max="2.2" step="0.1" value="1">
    <span id="widv">1.0×</span>
  </div>
  <h4>其他</h4>
  <div id="btns">
    <button id="bReset">重置本地</button>
    <button id="bClear">清空当前格</button>
    <button id="bSkip">跳过这屏</button>
    <button id="bGuide">描红开关</button>

  </div>
  <div id="diag">笔压自检：<span id="dg">把笔放到格子里按下去</span><br>
    <span id="dbg">本地库：检查中…</span></div>
</div>
<div id="toast"></div>
<canvas id="ink" width="320" height="320" style="display:none"></canvas>
<script>
window.onerror = function (m, src, line, col) {
  var d = document.createElement('div');
  d.id = 'err';
  d.textContent = 'JS 错误：' + m + '\n  at line ' + line + ':' + col;
  document.body.appendChild(d);
};
const VIEW = 470, PAD = 12, GAP = 12, INK_PX = 320;
const CELL = (VIEW - PAD * 2 - GAP) / 2;
const DPR = window.devicePixelRatio || 1;
const view = document.getElementById('view');
view.width = VIEW * DPR; view.height = VIEW * DPR;
const vctx = view.getContext('2d'); vctx.scale(DPR, DPR);

const DESK_TAG = __TAG__;          // 由服务端注入，如 "corpus-p1"
const DESK_CHARS = __CHARS__;      // [[id, char, pass], ...] 由服务端注入
let saved = new Set();             // 已完成的 id（来自本地 IndexedDB）
let cur = null, drawing = false, active = 0, showGuide = true;
let WIDTH_MUL = 1.0, FORCE_SPEED = false, maxP = 0, minP = 1, downP = null;

const cells = [];
for (let i = 0; i < 4; i++) {
  const c = document.createElement('canvas'); c.width = c.height = INK_PX;
  cells.push({ ink: c, ctx: c.getContext('2d'), strokes: [], dirty: false });
}
const cellXY = i => ({ x: PAD + (i % 2) * (CELL + GAP), y: PAD + Math.floor(i / 2) * (CELL + GAP) });

/* ── 笔迹：压感(或速度) → 半径，起收笔按弧长渐细 ───────────────── */
// 压感→粗细：这几个常数和字库重渲参数对齐（TOOLS/glyph_from_strokes.py
// 的 --rmax 0.034 / --rmin 0.20 / --easing 0.85），屏幕上看的就是印出来的样子。
const THINNING = 0.55, EASING = 0.85, STREAMLINE = 0.45, TAPER = 0.18;
function radiusOf(p, speed, useP) {
  const rMax = CELL * 0.034 * WIDTH_MUL, rMin = rMax * 0.20;
  let t = useP ? Math.pow(Math.max(0, Math.min(1, p)), EASING) : 1 / (1 + speed * 1.6);
  let r = rMin + (rMax - rMin) * t;
  if (useP) r *= 1 / (1 + speed * 1.1);
  return Math.max(0.35, r);
}
function smooth(pts) {
  const out = [];
  for (const p of pts) {
    const q = out.length ? out[out.length - 1] : p;
    out.push({ x: q.x + (p.x - q.x) * (1 - STREAMLINE),
               y: q.y + (p.y - q.y) * (1 - STREAMLINE),
               p: q.p + (p.p - q.p) * 0.55 });
  }
  return out;
}
function paint(ctx, pts) {
  if (pts.length < 2) return;
  const sm = smooth(pts);
  const len = [0];
  for (let i = 1; i < sm.length; i++)
    len.push(len[i - 1] + Math.hypot(sm[i].x - sm[i - 1].x, sm[i].y - sm[i - 1].y));
  const total = len[len.length - 1] || 1, taper = Math.max(4, total * TAPER);
  // 这一笔内部压感有起伏才当"真压感"，否则退回速度模拟
  const ps = sm.map(o => o.p);
  const mean = ps.reduce((a, b) => a + b, 0) / ps.length;
  const sd = Math.sqrt(ps.reduce((a, b) => a + (b - mean) * (b - mean), 0) / ps.length);
  const useP = (!FORCE_SPEED) && sd > 0.035;
  const L = [], R = [];
  for (let i = 0; i < sm.length; i++) {
    const a = sm[Math.max(0, i - 1)], b = sm[Math.min(sm.length - 1, i + 1)];
    let nx = -(b.y - a.y), ny = (b.x - a.x);
    const n = Math.hypot(nx, ny) || 1; nx /= n; ny /= n;
    const d = Math.hypot(sm[i].x - a.x, sm[i].y - a.y);
    let r = radiusOf(sm[i].p, d * 0.02, useP);
    const dIn = len[i], dOut = total - len[i];
    if (dIn < taper) r *= 0.3 + 0.7 * (dIn / taper);
    if (dOut < taper) r *= 0.3 + 0.7 * (dOut / taper);
    L.push({ x: sm[i].x + nx * r, y: sm[i].y + ny * r });
    R.push({ x: sm[i].x - nx * r, y: sm[i].y - ny * r });
  }
  ctx.fillStyle = '#14151a'; ctx.beginPath();
  ctx.moveTo(L[0].x, L[0].y);
  for (let i = 1; i < L.length; i++) ctx.lineTo(L[i].x, L[i].y);
  for (let i = R.length - 1; i >= 0; i--) ctx.lineTo(R[i].x, R[i].y);
  ctx.closePath(); ctx.fill();
}
function paintAll(i) {
  const c = cells[i]; c.ctx.clearRect(0, 0, INK_PX, INK_PX);
  for (const s of c.strokes) paint(c.ctx, s);
}
function draw() {
  vctx.fillStyle = '#fdfdfb'; vctx.fillRect(0, 0, VIEW, VIEW);
  for (let i = 0; i < 4; i++) {
    const { x, y } = cellXY(i);
    if (showGuide && cur && cur.items && cur.items[i] && !cur.done) {
      vctx.save(); vctx.beginPath(); vctx.rect(x, y, CELL, CELL); vctx.clip();
      vctx.fillStyle = 'rgba(20,21,26,.085)';
      vctx.font = (CELL * 0.92) + 'px "Songti SC","SimSun",serif';
      vctx.textAlign = 'center'; vctx.textBaseline = 'middle';
      const ch = cur.items[i].char;
      vctx.fillText(ch === ' ' ? '␣' : ch, x + CELL / 2, y + CELL / 2 + CELL * 0.04);
      vctx.restore();
    }
    vctx.strokeStyle = '#ece7db'; vctx.lineWidth = 1; vctx.beginPath();
    vctx.moveTo(x + CELL / 2, y); vctx.lineTo(x + CELL / 2, y + CELL);
    vctx.moveTo(x, y + CELL / 2); vctx.lineTo(x + CELL, y + CELL / 2); vctx.stroke();
    vctx.strokeStyle = (i === active) ? '#c9c0aa' : '#ddd6c6';
    vctx.lineWidth = (i === active) ? 2 : 1.4;
    vctx.strokeRect(x, y, CELL, CELL);
    if (cells[i].ghost) {                     // 灰字：这一格之前已经写过
      vctx.save(); vctx.globalAlpha = 0.42;
      vctx.drawImage(cells[i].ghost, x, y, CELL, CELL);
      vctx.restore();
      vctx.fillStyle = 'rgba(90,169,230,.85)';
      vctx.font = (CELL * 0.14) + 'px system-ui,sans-serif';
      vctx.textAlign = 'right'; vctx.textBaseline = 'top';
      vctx.fillText('已写', x + CELL - 6, y + 4);
    }
    vctx.drawImage(cells[i].ink, 0, 0, INK_PX, INK_PX, x, y, CELL, CELL);
  }
}
function fitStage() {
  const v = document.getElementById('view'), st = document.getElementById('stage');
  const r = st.getBoundingClientRect();
  let availH = r.height - 6, availW = r.width - 20;
  if (!(availH > 120)) {                       // 万一还没布局好，自己算一遍兜底
    let used = 0;
    for (const el of document.querySelectorAll('#meta,#bar,#quick,#big,#nav,#ghostTip')) {
      const cs = getComputedStyle(el);
      used += el.getBoundingClientRect().height
            + (parseFloat(cs.marginTop) || 0) + (parseFloat(cs.marginBottom) || 0);
    }
    availH = window.innerHeight - used - 10;
    availW = window.innerWidth - 20;
  }
  const s = Math.max(140, Math.floor(Math.min(availW, availH)) - 4);
  if (v.style.width !== s + 'px') { v.style.width = s + 'px'; v.style.height = s + 'px'; }
}
window.addEventListener('resize', fitStage);
window.addEventListener('load', () => {
  fitStage();
  [60, 200, 500, 1200].forEach(t => setTimeout(fitStage, t));
});
window.addEventListener('orientationchange', () => setTimeout(fitStage, 150));

function pos(e) {
  const r = view.getBoundingClientRect();
  return { x: (e.clientX - r.left) * VIEW / r.width, y: (e.clientY - r.top) * VIEW / r.height };
}
function hit(p) {
  for (let i = 0; i < 4; i++) {
    const { x, y } = cellXY(i);
    if (p.x >= x - GAP / 2 && p.x <= x + CELL + GAP / 2 &&
        p.y >= y - GAP / 2 && p.y <= y + CELL + GAP / 2) return i;
  }
  return -1;
}
function diag(e) {
  document.getElementById('dg').textContent =
    e.pointerType + '  down=' + (downP === null ? '-' : downP.toFixed(2)) +
    '  now=' + (e.pressure || 0).toFixed(2) +
    '  min=' + minP.toFixed(2) + '  max=' + maxP.toFixed(2) + '  tilt=' + (e.tiltX || 0);
}
view.addEventListener('pointerdown', e => {
  if (e.button === 2) return;
  const p = pos(e), i = hit(p);
  if (i < 0 || !cur || cur.done || !cur.items[i]) return;
  view.setPointerCapture(e.pointerId);
  active = i; drawing = true;
  if (cells[i].ghost) { cells[i].ghost = null; }     // 动笔就把底稿收起来
  downP = e.pressure || 0;
  if (downP !== 0.5) { maxP = Math.max(maxP, downP); minP = Math.min(minP, downP); }
  const { x, y } = cellXY(i);
  cells[i].strokes.push([{ x: (p.x - x) * INK_PX / CELL, y: (p.y - y) * INK_PX / CELL,
                           p: (e.pressure > 0 ? e.pressure : 0.5) }]);
  cells[i].dirty = true; paintAll(i); draw(); diag(e); e.preventDefault();
});
view.addEventListener('pointermove', e => {
  const pr = e.pressure;
  if (pr !== undefined && pr !== null && pr !== 0.5) {
    maxP = Math.max(maxP, pr); minP = Math.min(minP, pr);
  }
  diag(e);
  if (!drawing) return;
  const p = pos(e), { x, y } = cellXY(active);
  const c = cells[active], s = c.strokes[c.strokes.length - 1];
  s.push({ x: (p.x - x) * INK_PX / CELL, y: (p.y - y) * INK_PX / CELL,
           p: (e.pressure > 0 ? e.pressure : 0.5) });
  if (s.length > 3000) s.splice(0, 800);
  paintAll(active); draw();
});
function endStroke() { if (drawing) { drawing = false; draw(); } }
view.addEventListener('pointerup', endStroke);
view.addEventListener('pointercancel', endStroke);
view.addEventListener('contextmenu', e => e.preventDefault());

/* ── 本地存储：IndexedDB（离线也能存，不依赖服务器）──────────────── */
const DB_NAME = 'desk-v2-' + (DESK_TAG || 'x');
function idb() {
  return new Promise((res, rej) => {
    const rq = indexedDB.open(DB_NAME, 1);
    rq.onupgradeneeded = () => rq.result.createObjectStore('cells');
    rq.onsuccess = () => res(rq.result);
    rq.onerror = () => rej(rq.error);
  });
}
async function idbPut(rec) {
  const db = await idb();
  return new Promise((res, rej) => {
    const tx = db.transaction('cells', 'readwrite');
    tx.objectStore('cells').put(rec, rec.id);
    tx.oncomplete = () => res(); tx.onerror = () => rej(tx.error);
  });
}
async function idbDel(id) {
  const db = await idb();
  return new Promise((res) => {
    const tx = db.transaction('cells', 'readwrite');
    tx.objectStore('cells').delete(id);
    tx.oncomplete = () => res(); tx.onerror = () => res();
  });
}
async function idbAll() {
  const db = await idb();
  return new Promise((res) => {
    const tx = db.transaction('cells', 'readonly');
    const rq = tx.objectStore('cells').getAll();
    rq.onsuccess = () => res(rq.result || []);
    rq.onerror = () => res([]);
  });
}

/* ── 导出 ZIP（纯前端，store-only，无依赖）──────────────────────── */
const CRCT = (() => { const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) { let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0; } return t; })();
function crc32(u8) { let c = 0xFFFFFFFF;
  for (let i = 0; i < u8.length; i++) c = CRCT[(c ^ u8[i]) & 0xFF] ^ (c >>> 8);
  return (c ^ 0xFFFFFFFF) >>> 0; }
function zipStore(files) {
  const enc = new TextEncoder(), parts = [], cd = [];
  let off = 0;
  for (const f of files) {
    const name = enc.encode(f.name), data = f.data;
    const crc = crc32(data);
    const lh = new DataView(new ArrayBuffer(30));
    lh.setUint32(0, 0x04034b50, true); lh.setUint16(4, 20, true); lh.setUint16(6, 0, true);
    lh.setUint16(8, 0, true); lh.setUint32(10, 0, true); lh.setUint32(14, crc, true);
    lh.setUint32(18, data.length, true); lh.setUint32(22, data.length, true);
    lh.setUint16(26, name.length, true); lh.setUint16(28, 0, true);
    parts.push(new Uint8Array(lh.buffer), name, data);
    const ch = new DataView(new ArrayBuffer(46));
    ch.setUint32(0, 0x02014b50, true); ch.setUint16(4, 20, true); ch.setUint16(6, 20, true);
    ch.setUint16(8, 0, true); ch.setUint16(10, 0, true); ch.setUint32(12, 0, true);
    ch.setUint32(16, crc, true); ch.setUint32(20, data.length, true);
    ch.setUint32(24, data.length, true); ch.setUint16(28, name.length, true);
    ch.setUint16(30, 0, true); ch.setUint16(32, 0, true); ch.setUint16(34, 0, true);
    ch.setUint16(36, 0, true); ch.setUint32(38, 0, true); ch.setUint32(42, off, true);
    cd.push(new Uint8Array(ch.buffer), name);
    off += 30 + name.length + data.length;
  }
  let cdsize = 0; for (const c of cd) cdsize += c.length;
  const eo = new DataView(new ArrayBuffer(22));
  eo.setUint32(0, 0x06054b50, true); eo.setUint16(8, files.length, true);
  eo.setUint16(10, files.length, true); eo.setUint32(12, cdsize, true);
  eo.setUint32(16, off, true);
  return new Blob([...parts, ...cd, new Uint8Array(eo.buffer)], {type: 'application/zip'});
}
function b64ToBytes(b64) {
  const bin = atob(b64), out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}
async function exportZip() {
  const recs = (await idbAll()).sort((a, b) => a.id - b.id);
  if (!recs.length) { toast('还没有存下来的字'); return; }
  const files = [];
  for (const r of recs) {
    const code = r.char === ' ' ? 'sp' : ord(r.char);
    const base = String(r.id).padStart(4, '0') + '_p' + r.pass + '_' + code;
    if (r.png) files.push({name: base + '.png', data: b64ToBytes(r.png.split(',')[1] || r.png)});
    files.push({name: base + '.json',
                data: new TextEncoder().encode(JSON.stringify(
                  {id: r.id, char: r.char, pass: r.pass, px_per_mm: r.px_per_mm,
                   max_pressure: r.pressure, strokes: r.strokes}))});
  }
  const blob = zipStore(files);
  if (window.DeskBridge) {                      // 装在手机里的 APK：写进 App 目录
    const fr = new FileReader();
    fr.onload = () => {
      try { DeskBridge.saveZip(String(fr.result).split(',')[1]); }
      catch (e) { toast('导出失败：' + e); }
    };
    fr.readAsDataURL(blob);
    toast('已导出 ' + recs.length + ' 个到 App 目录');
    return;
  }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'desk-' + DESK_TAG + '-' + Date.now() + '.zip';
  document.body.appendChild(a); a.click(); a.remove();
  toast('已导出 ' + recs.length + ' 个');
}
function ord(ch) { return ch.codePointAt(0).toString(16).padStart(5, '0'); }

/* ── 进度：游标 + 本地已存。严格按字表顺序，绝不跳格 ──────────────── */
const SKIP_KEY = 'wd_skips_' + (DESK_TAG || 'x');
let skips = new Set((() => { try {
  return JSON.parse(localStorage.getItem(SKIP_KEY) || '[]'); } catch (e) { return []; } })());
let curPos = 0;                 // 当前屏第一格在 DESK_CHARS 里的下标
let busy = false, lastSaveAt = 0;

function persistSkips() {
  try { localStorage.setItem(SKIP_KEY, JSON.stringify([...skips])); } catch (e) {}
}
function firstUnwritten() {
  for (let k = 0; k < DESK_CHARS.length; k++) {
    const id = DESK_CHARS[k][0];
    if (!saved.has(id) && !skips.has(id)) return k;
  }
  return DESK_CHARS.length;
}
function recomputeCur() {        // 按游标刷一屏，不自己找"第一个没写的"乱跳
  const n = DESK_CHARS.length, items = [];
  for (let k = curPos; k < Math.min(curPos + 4, n); k++)
    items.push({ id: DESK_CHARS[k][0], char: DESK_CHARS[k][1], pass: DESK_CHARS[k][2] });
  cur = { done: curPos >= n || !items.length, n: curPos + 1, total: n, saved: saved.size,
          pass: items.length ? items[0].pass : 0, items };
  render();
}

async function dbgInfo() {
  try {
    const recs = await idbAll();
    let extra = '';
    if (window.DeskBridge) {
      try { extra = '　App 目录 ' + DeskBridge.countGlyphs() + ' 格'; } catch (e) {}
    }
    document.getElementById('dbg').textContent =
      '本地库 ' + DB_NAME + '：' + recs.length + ' 条　跳过 ' + skips.size + extra;
  } catch (e) {
    document.getElementById('dbg').textContent = '本地库读取失败：' + e;
  }
}

async function load() {
  const recs = await idbAll();
  saved = new Set(recs.map(r => r.id));
  if (window.DeskBridge) {
    // App 里以 App 目录里的文件为准：删掉某个文件 = 这一格重新变成"没写"
    try {
      const ids = JSON.parse(DeskBridge.savedIds() || '[]');
      if (ids.length || recs.length === 0) saved = new Set(ids);
    } catch (e) { /* 桥坏了就退回 IndexedDB */ }
  }
  curPos = firstUnwritten();        // 接着上次没写完的地方
  recomputeCur();
  dbgInfo();
  requestAnimationFrame(fitStage);
  [80, 300, 900].forEach(t => setTimeout(fitStage, t));
  if ('serviceWorker' in navigator && !window.DeskBridge) {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  }
}
function toast(t) {
  const el = document.getElementById('toast');
  el.textContent = t; el.style.opacity = 1;
  setTimeout(() => { el.style.opacity = 0; }, 420);
}

/* 把这一格之前写过的读出来当底稿（灰字）：翻回去能看见自己写过什么 */
async function loadGhosts() {
  for (let i = 0; i < 4; i++) { cells[i].ghost = null; cells[i].hasSaved = false; }
  if (!window.DeskBridge || !cur || cur.done) { draw(); return; }
  for (let i = 0; i < 4; i++) {
    const it = cur.items[i];
    if (!it || skips.has(it.id)) continue;
    try {
      const b64 = DeskBridge.readGlyph(it.id);
      if (b64 && b64.length > 100) {
        const img = new Image();
        img.onload = draw;
        img.src = 'data:image/png;base64,' + b64;
        cells[i].ghost = img; cells[i].hasSaved = true;
      }
    } catch (e) { /* 读不出来就只当没写过 */ }
  }
  draw();
}

function render() {
  if (!cur) return;
  for (let i = 0; i < 4; i++) {
    cells[i].strokes = []; cells[i].dirty = false; cells[i].ghost = null;
    cells[i].hasSaved = false; paintAll(i);
  }
  maxP = 0; minP = 1; downP = null;
  if (cur.done) {
    document.getElementById('meta').innerHTML = '<b>全部写完了</b>，叫我入库。';
    document.getElementById('barIn').style.width = '100%';
    draw(); return;
  }
  const chars = cur.items.map(x => x.char === ' ' ? '␣' : x.char);
  const same = chars.every(c => c === chars[0]);
  document.getElementById('meta').innerHTML =
    '第 <b>' + cur.n + '</b>–<b>' + (cur.n + cur.items.length - 1) + '</b> / ' + cur.total +
    ' 格　第 <b>' + cur.pass + '</b> 遍　已存 <b>' + cur.saved + '</b><br>本屏：<b>' +
    (same ? chars[0] + ' × ' + chars.length : chars.join(' ')) + '</b>';
  document.getElementById('barIn').style.width = (100 * cur.saved / cur.total) + '%';
  draw();
  loadGhosts();
  dbgInfo();
  fitStage();
}

function setBusy(v) {
  busy = v;
  for (const id of ['bNext', 'bUndo', 'bPrev', 'bRewrite']) {
    const el = document.getElementById(id); if (el) el.disabled = v;
  }
}

async function advance() {
  curPos = Math.min(DESK_CHARS.length, curPos + 4);
  recomputeCur();
}
function back() {
  if (curPos <= 0) { toast('已经是第一屏'); return; }
  curPos = Math.max(0, curPos - 4);
  recomputeCur();
  toast('上一屏：灰字是之前写过的');
}

async function save(skip) {
  if (busy || !cur || cur.done) return;
  const now = Date.now();
  if (now - lastSaveAt < 450) return;            // 防连点：一屏只会翻一次
  lastSaveAt = now;
  const items = cur.items;
  const dirty = items.map((it, i) => cells[i].dirty);
  const wrote = items.map((it, i) => cells[i].hasSaved);
  if (!skip) {
    const lack = items.filter((it, i) => !dirty[i] && !wrote[i]).length;
    if (lack > 0) { toast('还差 ' + lack + ' 个字'); return; }   // 严格：四格齐了才翻页
    if (!dirty.some(Boolean)) { await advance(); toast('这一屏已经写过'); return; }
  }
  setBusy(true);
  try {
    const saves = items.map((it, i) => ({
      id: it.id, char: it.char, pass: it.pass, skip: !!skip || !dirty[i],
      png: (!skip && dirty[i]) ? cells[i].ink.toDataURL('image/png').split(',')[1] : null,
      strokes: (!skip && dirty[i]) ? cells[i].strokes.map(s => s.map(pt => [
        +(pt.x / INK_PX).toFixed(4), +(pt.y / INK_PX).toFixed(4), +pt.p.toFixed(3)])) : null,
      px_per_mm: INK_PX / 12.0, pressure: maxP
    }));
    let n = 0;
    for (const sv of saves) {
      if (sv.skip || !sv.png) continue;
      await idbPut({id: sv.id, char: sv.char, pass: sv.pass, png: sv.png,
                    strokes: sv.strokes, px_per_mm: sv.px_per_mm, pressure: sv.pressure});
      saved.add(sv.id); n++;
    }
    if (skip) { for (const sv of saves) { saved.add(sv.id); skips.add(sv.id); } persistSkips(); }
    if (window.DeskBridge) {
      for (const sv of saves) {
        if (sv.skip || !sv.png) continue;
        try {
          DeskBridge.saveGlyph(JSON.stringify({id: sv.id, char: sv.char, pass: sv.pass,
            png: sv.png, strokes: sv.strokes, px_per_mm: sv.px_per_mm, pressure: sv.pressure}));
        } catch (e) { /* 落盘失败不影响本地库 */ }
      }
    }
    try {
      await fetch('/api/save_batch', { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ saves }) });
    } catch (e) { /* 离线：忽略 */ }
    await advance();
    toast(skip ? '已跳过这屏' : ('已存 ' + n + ' 个'));
  } finally {
    setBusy(false);
  }
}

async function undo() {
  if (busy) return;
  for (let n = 0; n < 4; n++) {
    const i = (active - n + 4) % 4;
    if (cells[i].strokes.length) {
      cells[i].strokes.pop(); cells[i].dirty = cells[i].strokes.length > 0;
      paintAll(i); draw(); toast('撤一笔'); return;
    }
  }
  toast('这一屏还没动笔');
}

/* 重写本屏：把这一屏已经存过的删掉重写（先问一次） */
async function rewrite() {
  if (busy || !cur || cur.done) return;
  const has = cells.some(c => c.hasSaved);
  if (!has && !cells.some(c => c.strokes.length)) { toast('本屏还没有内容'); return; }
  if (!confirm('把这一屏已经写过的删掉，重新写？')) return;
  setBusy(true);
  try {
    for (const it of cur.items) {
      try { await idbDel(it.id); } catch (e) {}
      saved.delete(it.id);
      if (window.DeskBridge) { try { DeskBridge.deleteGlyph(it.id); } catch (e) {} }
    }
    for (let i = 0; i < 4; i++) {
      cells[i].strokes = []; cells[i].dirty = false; cells[i].ghost = null;
      cells[i].hasSaved = false; paintAll(i);
    }
    recomputeCur();
    toast('已清空本屏');
  } finally {
    setBusy(false);
  }
}

document.getElementById('bNext').onclick = () => save(false);
document.getElementById('bUndo').onclick = () => undo();
document.getElementById('bSkip').onclick = () => save(true);
document.getElementById('bPrev').onclick = () => back();
document.getElementById('bRewrite').onclick = () => rewrite();
document.getElementById('bClear4').onclick = () => {
  if (!cells.some(c => c.strokes.length)) { toast('这一屏是空的'); return; }
  for (let i = 0; i < 4; i++) {
    cells[i].strokes = []; cells[i].dirty = false; paintAll(i);
  }
  active = 0; maxP = 0; minP = 1; downP = null; draw();
  toast('已清空整屏四格');
};
document.getElementById('bClear').onclick = () => {
  cells[active].strokes = []; cells[active].dirty = false; paintAll(active); draw();
  toast('清空这一格');
};
document.getElementById('bMore').onclick = () => {
  document.getElementById('more').classList.toggle('open');
};
document.getElementById('bGuide').onclick = () => { showGuide = !showGuide; draw(); };
document.getElementById('bExport').onclick = () => exportZip();
document.getElementById('bReset').onclick = async () => {
  if (!confirm('清空手机上所有已存字迹（本地库 + App 目录里的文件）？\n已经导出/拷到电脑的不受影响。')) return;
  const db = await idb();
  await new Promise(r => { const tx = db.transaction('cells', 'readwrite');
    tx.objectStore('cells').clear(); tx.oncomplete = r; tx.onerror = r; });
  if (window.DeskBridge) { try { DeskBridge.clearGlyphs(); } catch (e) {} }
  saved = new Set(); skips = new Set(); persistSkips();
  curPos = 0; recomputeCur(); toast('已清空');
};
const wid = document.getElementById('wid'), widv = document.getElementById('widv');
WIDTH_MUL = parseFloat(localStorage.getItem('wd_wid2') || '1');
wid.value = WIDTH_MUL; widv.textContent = WIDTH_MUL.toFixed(1) + '×';
wid.oninput = () => {
  WIDTH_MUL = parseFloat(wid.value); widv.textContent = WIDTH_MUL.toFixed(1) + '×';
  localStorage.setItem('wd_wid2', WIDTH_MUL);
  for (let i = 0; i < 4; i++) paintAll(i);
  draw();
};
document.addEventListener('keydown', e => {
  if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); save(false); }
  else if (e.key === 'z' || e.key === 'Z') { e.preventDefault(); undo(); }
  else if (e.key === 'Backspace') { e.preventDefault();
    if (e.shiftKey) { document.getElementById('bClear4').click(); return; }
    cells[active].strokes = []; cells[active].dirty = false; paintAll(active); draw(); }
  else if (e.key === 'PageDown') { e.preventDefault(); save(true); }
  else if (e.key === 'PageUp') { e.preventDefault(); back(); }
  else if (e.key === 'h' || e.key === 'H') { showGuide = !showGuide; draw(); }
});
load();
</script></body></html>
"""


SW = """
const CACHE = "desk-v2";
self.addEventListener("install", e => { self.skipWaiting(); });
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(
    ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
// 页面：网络优先（在线时永远拿到最新版），离线回落到缓存
async function pageFirst(req) {
  try {
    const r = await fetch(req);
    const c = await caches.open(CACHE);
    c.put(req, r.clone()).catch(() => {});
    return r;
  } catch (err) {
    const cached = await caches.match(req) || await caches.match("/");
    if (cached) return cached;
    throw err;
  }
}
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (u.pathname.startsWith("/api/")) return;                 // 接口不碰
  if (e.request.mode === "navigate" || u.pathname === "/" || u.pathname.endsWith(".html")) {
    e.respondWith(pageFirst(e.request));
    return;
  }
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request).then(resp => {
    const copy = resp.clone();
    caches.open(CACHE).then(c => c.put(e.request, copy)).catch(() => {});
    return resp;
  })));
});
"""


def _icon_png(size: int = 192) -> bytes:
    import io
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (size, size), (34, 37, 42))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([8, 8, size - 8, size - 8], radius=28, fill=(253, 253, 251))
    try:
        from PIL import ImageFont
        f = ImageFont.truetype("/mnt/c/Windows/Fonts/simsun.ttc", int(size * 0.62))
        d.text((size / 2, size / 2), "写", font=f, fill=(20, 21, 26), anchor="mm")
    except Exception:
        d.line([(size*0.3, size*0.5), (size*0.7, size*0.5)], fill=(20,21,26), width=8)
    buf = io.BytesIO(); im.save(buf, "PNG")
    return buf.getvalue()


ICON_PNG = b""
ICON_512 = b""


class State:
    def __init__(self, cells: list[dict], outdir: Path, tag: str):
        self.cells = cells
        self.outdir = outdir
        self.tag = tag
        self.saved: list[int] = []
        self.batches: list[list[int]] = []
        self.i = 0
        self.lock = threading.Lock()
        self.outdir.mkdir(parents=True, exist_ok=True)
        self.state_file = outdir / f"state-{tag}.json"
        self.resume()

    def resume(self) -> None:
        if self.state_file.exists():
            try:
                d = json.load(open(self.state_file, encoding="utf-8"))
                self.saved = [int(x) for x in d.get("saved", [])]
                self.batches = [[int(y) for y in b] for b in d.get("batches", [])]
                self.i = int(d.get("i", len(self.saved)))
            except Exception:
                pass

    def flush(self) -> None:
        json.dump({"saved": self.saved, "i": self.i, "batches": self.batches},
                  open(self.state_file, "w"), ensure_ascii=False)

    def current(self) -> dict:
        total = len(self.cells)
        done = set(self.saved)
        while self.i < total and self.cells[self.i]["id"] in done:
            self.i += 1
        if self.i >= total:
            return {"done": True, "total": total, "saved": len(self.saved),
                    "items": [], "px_per_mm": INK_PX / CELL_MM}
        items = self.cells[self.i:self.i + PER_SCREEN]
        return {"done": False, "n": self.i + 1, "total": total,
                "saved": len(self.saved), "pass": items[0]["pass"],
                "items": [{"id": c["id"], "char": c["char"], "pass": c["pass"]} for c in items],
                "px_per_mm": INK_PX / CELL_MM}

    def save_batch(self, saves: list[dict]) -> dict:
        with self.lock:
            ids = []
            for s in saves:
                cid = int(s["id"]); ch = s["char"]; pw = int(s["pass"])
                code = "sp" if ch == " " else f"{ord(ch):05x}"
                if not s.get("skip") and s.get("png"):
                    (self.outdir / f"{cid:04d}_p{pw}_{code}.png").write_bytes(
                        base64.b64decode(s["png"]))
                    (self.outdir / f"{cid:04d}_p{pw}_{code}.json").write_text(
                        json.dumps({"id": cid, "char": ch, "pass": pw,
                                    "px_per_mm": s.get("px_per_mm"),
                                    "max_pressure": s.get("pressure"),
                                    "strokes": s.get("strokes")}, ensure_ascii=False),
                        encoding="utf-8")
                # 只有真的存了图才算完成；空着/跳过的格子保持在队列里，下次还会出现
                if not s.get("skip") and s.get("png") and cid not in self.saved:
                    self.saved.append(cid)
                ids.append(cid)
            if ids:
                self.batches.append(ids)
            self.i = 0                      # 让 current() 重新找第一个没存的格子
            self.flush()
            return self.current()

    def undo(self) -> dict:
        with self.lock:
            if self.batches:
                batch = self.batches.pop()
                for cid in batch:
                    for f in self.outdir.glob(f"{cid:04d}_p*"):
                        f.unlink()
                    if cid in self.saved:
                        self.saved.remove(cid)
                self.i = 0
                self.flush()
            return self.current()

    def prev(self) -> dict:
        """回上一屏：把上一屏从"已存"里摘掉，让 current() 重新从那里开始。"""
        with self.lock:
            if self.batches:
                batch = self.batches.pop()
                for cid in batch:
                    for f in self.outdir.glob(f"{cid:04d}_p*"):
                        f.unlink()
                    if cid in self.saved:
                        self.saved.remove(cid)
            self.i = 0
            self.flush()
            return self.current()


def load_cells(pass_id: int | None, manifest: Path) -> list[dict]:
    m = json.load(open(manifest, encoding="utf-8"))
    cells = [c for c in m["cells"] if pass_id is None or c["pass"] == pass_id]
    return sorted(cells, key=lambda c: c["id"])


def build_page(tag: str, cells: list[dict]) -> str:
    """把字表注入模板：得到一份不依赖服务器的页面（APK 里用的就是它）。"""
    chars = json.dumps([[c["id"], c["char"], c["pass"]] for c in cells],
                       ensure_ascii=False)
    return PAGE.replace("__CHARS__", chars).replace("__TAG__", json.dumps(tag))


def make_handler(state: State, html: bytes):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, obj):
            body = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path in ("/", "/index.html"):
                body = build_page(state.tag, state.cells).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif u.path == "/sw.js":
                body = SW.encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif u.path == "/manifest.webmanifest":
                body = json.dumps({
                    "name": "写字台", "short_name": "写字台", "start_url": "/",
                    "display": "standalone", "background_color": "#22252a",
                    "theme_color": "#22252a",
                    "id": "/", "scope": "/",
                    "icons": [{"src": "/icon-192.png", "sizes": "192x192", "type": "image/png",
                               "purpose": "any maskable"},
                              {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png",
                               "purpose": "any maskable"}],
                }, ensure_ascii=False).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/manifest+json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif u.path in ("/icon-192.png", "/icon.png"):
                body = ICON_PNG
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif u.path == "/icon-512.png":
                body = ICON_512
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif u.path == "/api/current":
                self._json(state.current())
            else:
                self.send_error(404)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n) if n else b"{}"
            try:
                payload = json.loads(body or b"{}")
            except Exception:
                payload = {}
            if self.path == "/api/save_batch":
                self._json(state.save_batch(payload.get("saves") or []))
            elif self.path == "/api/undo":
                self._json(state.undo())
            elif self.path == "/api/prev":
                self._json(state.prev())
            else:
                self.send_error(404)

    return H


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", type=Path, default=Path("."),
                    help="项目目录（raw/ 在它下面；可用 --out 另指）")
    ap.add_argument("--tag", default="corpus")
    ap.add_argument("--pass-id", type=int, default=None,
                    help="第几遍；不给就自动接着没写完的那一遍")
    ap.add_argument("--all-passes", action="store_true",
                    help="不按遍过滤：字表本身就是排好的顺序（同字连写几遍时用）")
    ap.add_argument("--open", action="store_true", help="启动后自动打开浏览器")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--manifest", type=Path, default=None,
                    help="字表 JSON（默认 <project>/sheets/manifest-<tag>.json）")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--offline-out", type=Path, default=None,
                    help="只生成一份自包含离线页面（写进 APK 的 assets 里），不起服务")
    args = ap.parse_args()

    proj = load_project(args.project)
    manifest = Path(args.manifest) if args.manifest else proj.manifest(args.tag)
    if not manifest.exists():
        print(f"!! 没有 {manifest}", flush=True)
        return 2
    # 没指定遍数 → 自动挑第一个没写完的
    if args.all_passes:
        args.pass_id = 0                       # 0 = 整本一次流（目录名 ...-p0）
    elif args.pass_id is None:
        pass_id = 1
        for pw in (1, 2, 3):
            cl = load_cells(pw, manifest)
            if not cl:
                continue
            st_try = proj.raw_dir(args.tag, pw) / f"state-{args.tag}-p{pw}.json"
            done = 0
            if st_try.exists():
                try:
                    done = len(json.loads(st_try.read_text())["saved"])
                except Exception:
                    done = 0
            if done < len(cl):
                pass_id = pw
                break
        args.pass_id = pass_id

    cells = load_cells(None if args.all_passes else args.pass_id, manifest)
    tag_full = f"{args.tag}-p{args.pass_id}"
    if args.offline_out:
        args.offline_out.parent.mkdir(parents=True, exist_ok=True)
        args.offline_out.write_text(build_page(tag_full, cells), encoding="utf-8")
        print(f"离线页面：{args.offline_out}（{len(cells)} 格，{tag_full}）", flush=True)
        return 0
    outdir = Path(args.out) if args.out else \
        proj.raw_dir(args.tag, args.pass_id)
    global ICON_PNG, ICON_512
    ICON_PNG = _icon_png(192)
    ICON_512 = _icon_png(512)
    st = State(cells, outdir, tag_full)
    srv = ThreadingHTTPServer(("0.0.0.0", args.port), make_handler(st, PAGE.encode()))
    print(f"写字台：http://127.0.0.1:{args.port}　（一屏 {PER_SCREEN} 字）", flush=True)
    print(f"  第 {args.pass_id} 遍，共 {len(cells)} 格；已存 {len(st.saved)} 格", flush=True)
    if args.open:
        import subprocess
        try:
            subprocess.Popen(["cmd.exe", "/c", "start", "",
                              f"http://127.0.0.1:{args.port}"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("  已在浏览器打开", flush=True)
        except Exception as e:
            print(f"  （自动开浏览器失败：{e}；请手动打开上面的地址）", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
