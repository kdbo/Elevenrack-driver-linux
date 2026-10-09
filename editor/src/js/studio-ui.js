/*
 * Eleven Edit for Mac — Studio look
 * Copyright (c) 2026 Damilola Olalere (MrDees). Original Windows editor
 * Copyright (c) 2026 Charles Wardick. SPDX-License-Identifier: MIT
 */
// ════════════════════════════════════════════════════════════════════
// STUDIO-UI.JS (2026-09-15) — builds the glass console (css/studio.css)
// out of the app's existing DOM.
//
// The rule that keeps every feature working: nothing is cloned or
// re-implemented. Every element with an id or a handler is MOVED into the
// new layout with appendChild, so ui.js, fx-panels.js, patch-nav.js and
// the inline scripts in index.html keep finding what they expect. This
// file only adds containers, decorations (the drawn amp, stompbox
// footswitches, VU meters), the knob/fader renderer and a few observers
// that mirror state into the new readouts (LCD lines, side cards, LEDs).
//
// Layout (top to bottom): top bar (LCD, bank/patch, input, tuner) ·
// signal path · focus (amp on its stage, or the open effect as a pedal,
// with side cards) · master section (gate, to amp, volumes, globals,
// meters with main/phones/tempo, rig & bank buttons) · auto advance ·
// status bar. Settings (gear) opens in the focus area.
// ════════════════════════════════════════════════════════════════════
(function () {
  'use strict';

  const CTL_KEY = 'ee-controls';   // localStorage: 'knobs' | 'sliders'
  const $ = id => document.getElementById(id);

  // ── Amp families: which drawn amp each model gets, and what it is based on ──
  const AMP_FAMILY = {
    tweed_lux: 'tweed', tweed_bass: 'tweed',
    lux_vib: 'black', lux_norm: 'black', black_vib: 'black', black_sr: 'black', black_mini: 'black', black_duo: 'black',
    ac_hi: 'ac', ms30: 'ac',
    j45: 'plexi', plexivari: 'plexi', plexi50: 'plexi', plexi100: 'plexi',
    lead800: 'lead', m2lead: 'lead', sl100drive: 'lead', sl100crunch: 'lead', sl100clean: 'lead',
    treadmod: 'tread', treadvint: 'tread',
    blueline: 'blue',
    rb01b_red: 'rb', rb01b_blue: 'rb', rb01b_green: 'rb',
    dc_mod_od: 'dc', dc_mod_sod: 'dc', dc_mod800: 'dc', dc_mod_clean: 'dc', dc_vint_crunch: 'dc', dc_vint_od: 'dc', dc_vint_clean: 'dc', dc_bass: 'dc',
  };
  const FAMILIES = [
    { key: 'tweed', name: 'Tweed' }, { key: 'black', name: 'Black panel' }, { key: 'ac', name: 'AC' },
    { key: 'plexi', name: 'Plexi' }, { key: 'lead', name: 'Lead' }, { key: 'tread', name: 'Tread plate' },
    { key: 'blue', name: 'Blue line' }, { key: 'rb', name: 'RB' }, { key: 'dc', name: 'DC' },
  ];
  // "Based on" — the amp each model emulates, as Avid's Eleven Rack guide lists them.
  const AMP_BASED_ON = {
    tweed_lux: '1959 Fender® 5E3 Tweed Deluxe', tweed_bass: '1959 Fender® 5F6-A Bassman®',
    lux_vib: '1964 Fender® Deluxe Reverb®, vibrato channel', lux_norm: '1964 Fender® Deluxe Reverb®, normal channel',
    black_vib: '1964 Fender® Vibroverb®', black_sr: '1965 Fender® Super Reverb®',
    black_mini: '1965 Fender® Vibro Champ®', black_duo: '1967 Fender® Twin Reverb®',
    j45: '1965 Marshall® JTM45', ac_hi: '1966 Vox® AC30 Top Boost',
    plexivari: '1967 Marshall® Super Lead, variac\'d', plexi50: '1968 Marshall® 1987 50 W', plexi100: '1969 Marshall® 1959 Super Lead 100 W',
    blueline: '1969 Ampeg® SVT® "blue line"', lead800: '1982 Marshall® JCM800 2203', m2lead: '1985 MESA/Boogie® Mark IIC+',
    sl100drive: '1989 Soldano SLO-100, overdrive channel', sl100crunch: '1989 Soldano SLO-100, crunch', sl100clean: '1989 Soldano SLO-100, clean',
    treadmod: '1992 MESA/Boogie® Dual Rectifier®, modern', treadvint: '1992 MESA/Boogie® Dual Rectifier®, vintage',
    ms30: '1993 Matchless DC-30', rb01b_red: '1997 Bogner Ecstasy 101B, red channel', rb01b_blue: '1997 Bogner Ecstasy 101B, blue channel',
    rb01b_green: '1997 Bogner Ecstasy 101B, green channel',
    dc_mod_od: 'Eleven Rack original design (DC Modern)', dc_mod_sod: 'Eleven Rack original design (DC Modern)', dc_mod800: 'Eleven Rack original design (DC Modern)',
    dc_mod_clean: 'Eleven Rack original design (DC Modern)', dc_vint_crunch: 'Eleven Rack original design (DC Vintage)', dc_vint_od: 'Eleven Rack original design (DC Vintage)',
    dc_vint_clean: 'Eleven Rack original design (DC Vintage)', dc_bass: 'Eleven Rack original design (DC Bass)',
  };
  // speakers per cab, by the cab-type-select index (protocol.js CAB_TYPE_LIST order)
  const CAB_SPEAKERS = [1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4, 4, 4, 4, 8];
  // stompbox colours per effect panel
  const PEDALS = { 'panel-vol': 'chrome', 'panel-wah': 'black', 'panel-dist': 'orange', 'panel-fxloop': 'grey', 'panel-delay': 'green', 'panel-reverb': 'teal', 'panel-fxhost': 'blue' };
  const PEDAL_DOM = { 'panel-vol': 'vol', 'panel-wah': 'wah', 'panel-dist': 'dist', 'panel-fxloop': 'fxloop', 'panel-delay': 'delay', 'panel-reverb': 'reverb' };
  const PANEL_IDS = ['panel-ampcab', 'panel-other', 'panel-dist', 'panel-reverb', 'panel-wah', 'panel-vol', 'panel-fxloop', 'panel-delay', 'panel-fxhost', 'panel-settings'];

  // ── Block categories: every block gets an icon and a pedal colour from its
  // model name (the rack's MODEL_NAMES table), so a compressor in FX1 looks
  // like a compressor, an EQ like an EQ, a wah like a treadle, and so on. ──
  const CAT_COLOR = { dist: 'orange', delay: 'green', reverb: 'purple', mod: 'blue', comp: 'grey', eq: 'yellow', pitch: 'pink', wah: 'black', vol: 'chrome', loop: 'grey', stomp: 'teal', amp: 'black' };
  const CAT_HEX = { dist: '#ee7a1e', delay: '#4f8b35', reverb: '#7a55b8', mod: '#3468b8', comp: '#767d87', eq: '#e6b91e', pitch: '#e0568e', wah: '#2a2d33', vol: '#b8bec6', loop: '#767d87', stomp: '#2f8a84', amp: '#2a2d33' };
  const DOM_DEFAULT_CAT = { vol: 'vol', wah: 'wah', dist: 'dist', mod: 'mod', fx1: 'stomp', fx2: 'stomp', fxloop: 'loop', delay: 'delay', reverb: 'reverb', amp: 'amp' };
  function catFor(dom, modelName) {
    const n = String(modelName || '').toLowerCase();
    if (dom === 'amp') return 'amp';
    if (dom === 'vol' || /volume/.test(n)) return 'vol';
    if (dom === 'wah' || /wah/.test(n)) return 'wah';
    if (dom === 'fxloop' || /fx loop/.test(n)) return 'loop';
    if (/comp|dyn3|limit/.test(n)) return 'comp';
    if (/\beq\b|graphic|parametric/.test(n)) return 'eq';
    if (/pitch|octav|harmon/.test(n)) return 'pitch';
    if (/chorus|flang|phas|vibe|trem|roto|vibrato/.test(n)) return 'mod';
    if (dom === 'delay' || /delay|echo/.test(n)) return 'delay';
    if (dom === 'reverb' || /reverb|spring|hall|plate|room|\bsr\b/.test(n)) return 'reverb';
    if (dom === 'dist' || /fuzz|dist|drive|boost/.test(n)) return 'dist';
    if (dom === 'mod') return 'mod';
    return 'stomp';
  }
  const G = 'stroke="#fff" stroke-width="1.4" fill="none" stroke-linecap="round" stroke-linejoin="round"';
  function iconSvg(cat) {
    const c = CAT_HEX[cat] || CAT_HEX.stomp;
    const open = '<svg class="thumb-ico" viewBox="0 0 28 28" xmlns="http://www.w3.org/2000/svg">';
    const box = glyph => open + '<rect x="6" y="2.5" width="16" height="23" rx="3" fill="' + c + '" stroke="rgba(0,0,0,.55)"/><rect x="8.5" y="5.5" width="11" height="7" rx="1.5" fill="rgba(0,0,0,.38)"/>' + glyph + '<circle cx="14" cy="15.5" r="1.1" fill="#ff5a4a"/><circle cx="14" cy="20.5" r="3" fill="#e6e9ee" stroke="#2a2e34"/></svg>';
    switch (cat) {
      case 'dist':   return box('<path d="M10 10.5 l2 -3.5 l1.5 3.5 l1.5 -3.5 l2 3.5" ' + G + '/>');
      case 'delay':  return box('<circle cx="10.5" cy="9" r="1.7" fill="#fff"/><circle cx="14" cy="9" r="1.3" fill="#fff" opacity=".8"/><circle cx="17.2" cy="9" r=".9" fill="#fff" opacity=".6"/>');
      case 'reverb': return box('<path d="M10 11 v-4.5 M12.5 11 v-3.3 M15 11 v-2.2 M17.5 11 v-1.2" ' + G + '/>');
      case 'mod':    return box('<path d="M9.5 9 c1.2 -3.2 2.3 -3.2 3.5 0 s2.3 3.2 3.5 0" ' + G + '/>');
      case 'comp':   return box('<path d="M9.5 9 h9 M11.5 7 l-2 2 l2 2 M16.5 7 l2 2 l-2 2" ' + G + '/>');
      case 'eq':     return box('<path d="M10.5 11 v-3 M14 11 v-5 M17.5 11 v-2" ' + G + ' stroke-width="1.8"/>');
      case 'pitch':  return box('<path d="M11 11 v-5 M9 8 l2 -2 l2 2 M17 6 v5 M15 9 l2 2 l2 -2" ' + G + '/>');
      case 'wah':
      case 'vol':    return open + '<rect x="3" y="18" width="22" height="6" rx="2" fill="' + c + '" stroke="rgba(0,0,0,.55)"/><path d="M5 19 L23 9 L24.5 15 L6.5 24 Z" fill="#3a3d42" stroke="#0a0a0a"/><path d="M8 20 L21 12.5" stroke="rgba(255,255,255,.35)" stroke-width="1"/></svg>';
      case 'loop':   return open + '<rect x="4" y="8" width="20" height="12" rx="3" fill="' + c + '" stroke="rgba(0,0,0,.55)"/><path d="M8 14 h11 M16.5 11 l3 3 l-3 3" ' + G + '/><circle cx="8" cy="14" r="1.6" fill="#fff"/></svg>';
      case 'amp':    return open + '<rect x="3.5" y="3" width="21" height="8" rx="2" fill="#2a2d33" stroke="rgba(0,0,0,.6)"/><rect x="6" y="5.5" width="16" height="1.6" rx=".8" fill="#c9cdd3"/><rect x="3.5" y="12" width="21" height="13" rx="2" fill="#4a4030" stroke="rgba(0,0,0,.6)"/><circle cx="10" cy="18.5" r="3.6" fill="#1a1a1a" stroke="#9aa0a8"/><circle cx="18" cy="18.5" r="3.6" fill="#1a1a1a" stroke="#9aa0a8"/></svg>';
      case 'input':  return open + '<rect x="9" y="3" width="10" height="9" rx="2" fill="#c9cdd3" stroke="rgba(0,0,0,.6)"/><rect x="12" y="12" width="4" height="8" fill="#9aa0a8"/><rect x="11" y="20" width="6" height="5" rx="1.5" fill="#e6e9ee" stroke="rgba(0,0,0,.5)"/></svg>';
      case 'stereo': return open + '<circle cx="10" cy="14" r="6.5" fill="none" stroke="#4ade80" stroke-width="1.8"/><circle cx="18" cy="14" r="6.5" fill="none" stroke="#4ade80" stroke-width="1.8"/></svg>';
      default:       return box('');
    }
  }
  function ensureTileParts(slot) {
    const ph = slot.querySelector('.chain-thumb-placeholder'); if (!ph) return null;
    let model = slot.querySelector('.thumb-model');
    if (!model) { model = mk('span', { class: 'thumb-model' }); slot.querySelector('.chain-thumb').insertAdjacentElement('afterend', model); }
    return { ph: ph, model: model };
  }
  function syncChainIcons() {
    const chain = (typeof currentChain !== 'undefined' && Array.isArray(currentChain)) ? currentChain : [];
    const byDom = {};
    chain.forEach(b => {
      const dom = (typeof SLOT_ID_TO_DOM !== 'undefined' && SLOT_ID_TO_DOM[b.slotId]) || ((typeof SLOT_AMP !== 'undefined' && b.slotId === SLOT_AMP) ? 'amp' : null);
      if (dom) byDom[dom] = (typeof MODEL_NAMES !== 'undefined' && MODEL_NAMES[b.modelId]) || '';
    });
    document.querySelectorAll('#chainstrip .chain-slot, #chainstrip .chain-slot-stack').forEach(slot => {
      const name = slot.querySelector('.chain-name[data-slot], #chain-amp');
      if (!name) return;
      const dom = name.dataset.slot || 'amp';
      const parts = ensureTileParts(slot); if (!parts) return;
      const modelName = dom === 'amp' ? ((typeof currentAmpName !== 'undefined' && currentAmpName) || '') : (byDom[dom] || '');
      const cat = (dom === 'amp' || dom in byDom) ? catFor(dom, modelName) : (DOM_DEFAULT_CAT[dom] || 'stomp');
      if (parts.ph.dataset.cat !== cat) {
        parts.ph.dataset.cat = cat;
        const old = parts.ph.querySelector('svg.thumb-ico'); if (old) old.remove();
        parts.ph.insertAdjacentHTML('beforeend', iconSvg(cat));
      }
      if (parts.model.textContent !== modelName) { parts.model.textContent = modelName; parts.model.title = modelName; }
    });
  }

  function mk(tag, attrs, html) {
    const e = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(k => { if (k === 'class') e.className = attrs[k]; else e.setAttribute(k, attrs[k]); });
    if (html !== undefined) e.innerHTML = html;
    return e;
  }
  function kv(el) { const w = mk('div', { class: 'kv' }); w.appendChild(el); return w; }
  function clamp127(v) { v = parseInt(v, 10); return Number.isNaN(v) ? 64 : Math.max(0, Math.min(127, v)); }

  // ── Retina-aware canvas prep: logical size w×h, backing store × dpr ──
  function prep(canvas, w, h) {
    const dpr = Math.min(window.devicePixelRatio || 1, 3);
    const key = w + 'x' + h + '@' + dpr;
    if (canvas.dataset.prep !== key) {
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      canvas.style.width = w + 'px'; canvas.style.height = h + 'px';
      canvas.dataset.prep = key;
    }
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    return ctx;
  }
  function rr(ctx, x, y, w, h, r) {
    ctx.beginPath(); ctx.moveTo(x + r, y); ctx.lineTo(x + w - r, y); ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r); ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h); ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r); ctx.lineTo(x, y + r); ctx.quadraticCurveTo(x, y, x + r, y); ctx.closePath();
  }

  // ── Neve cap colours: red on gain/level, blue on tone, grey on dynamics ──
  const CAP = {
    red:  { hi: '#e35a4e', mid: '#c53a2e', lo: '#5c1611' },
    blue: { hi: '#5c9be6', mid: '#3a78c8', lo: '#17325a' },
    grey: { hi: '#aab3c0', mid: '#7c8694', lo: '#2e3237' },
  };
  function hexToRgb(h) { const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(h || ''); return m ? [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)] : null; }
  function shade(hex, f) { const c = hexToRgb(hex); if (!c) return hex; return 'rgb(' + c.map(v => Math.max(0, Math.min(255, Math.round(v * f)))).join(',') + ')'; }
  function capColours(wrap) {
    if (wrap && wrap.dataset.bandColor) { const b = wrap.dataset.bandColor; return { hi: shade(b, 1.25), mid: b, lo: shade(b, 0.5) }; }
    let label = '';
    const ck = wrap && wrap.closest ? wrap.closest('.ctrl-knob') : null;
    const lab = ck ? ck.querySelector('label') : null;
    if (lab) label = (lab.textContent || '').toLowerCase();
    const id = (wrap && wrap.id ? wrap.id : '').toLowerCase();
    let col = 'blue';
    if (/gate|thresh|release|attack|ratio|comp/.test(label + ' ' + id)) col = 'grey';
    else if (/vol|gain|boost|drive|level|out|mix|amount|master|send|return|feedback|depth|intensity/.test(label + ' ' + id)) col = 'red';
    return CAP[col];
  }

  // ── Glass knob: orange value arc, dark body, Neve-coloured cap, white pointer ──
  function wrapSize(wrap, dw, dh) {
    if (!wrap) return { w: dw, h: dh };
    const cs = getComputedStyle(wrap);
    const w = parseFloat(cs.width), h = parseFloat(cs.height);
    return { w: (w > 0 ? w : dw), h: (h > 0 ? h : dh) };
  }
  function drawGlassKnob(canvas, value127, wrap) {
    const sz = wrapSize(wrap, 70, 70), w = Math.min(sz.w, sz.h), h = w, ctx = prep(canvas, w, h), cx = w / 2, cy = h / 2, R = w / 2;
    const k = R / 35;
    const a0 = Math.PI * 0.75, sweep = Math.PI * 1.5;
    const angle = v => a0 + sweep * (clamp127(v) / 127);
    const v = clamp127(value127), cap = capColours(wrap);
    ctx.lineCap = 'round';
    // track + value arc
    ctx.beginPath(); ctx.arc(cx, cy, R - 3 * k, a0, a0 + sweep); ctx.strokeStyle = 'rgba(255,255,255,0.10)'; ctx.lineWidth = 3 * k; ctx.stroke();
    if (v > 0) {
      ctx.save(); ctx.shadowColor = 'rgba(255,122,26,0.75)'; ctx.shadowBlur = 6;
      ctx.beginPath(); ctx.arc(cx, cy, R - 3 * k, a0, angle(v)); ctx.strokeStyle = '#ff7a1a'; ctx.lineWidth = 3 * k; ctx.stroke(); ctx.restore();
    }
    // baseline marker (the value the knob loaded with — double-click restores it)
    if (wrap && wrap.dataset.orig !== undefined && wrap.dataset.orig !== '') {
      const a = angle(parseInt(wrap.dataset.orig, 10));
      ctx.save(); ctx.translate(cx, cy); ctx.rotate(a + Math.PI / 2);
      ctx.beginPath(); ctx.moveTo(0, -(R - 0.5)); ctx.lineTo(-2.6 * k, -(R - 6 * k)); ctx.lineTo(2.6 * k, -(R - 6 * k)); ctx.closePath();
      ctx.fillStyle = '#ffb35c'; ctx.fill(); ctx.restore();
    }
    // body
    let g;
    const rb = R - 8 * k;
    ctx.save(); ctx.shadowColor = 'rgba(0,0,0,0.7)'; ctx.shadowBlur = 6; ctx.shadowOffsetY = 3;
    g = ctx.createRadialGradient(cx - 8 * k, cy - 9 * k, 2, cx, cy, rb);
    g.addColorStop(0, '#3a4048'); g.addColorStop(0.6, '#1a1e25'); g.addColorStop(1, '#0b0d11');
    ctx.beginPath(); ctx.arc(cx, cy, rb, 0, Math.PI * 2); ctx.fillStyle = g; ctx.fill(); ctx.restore();
    g = ctx.createLinearGradient(cx, cy - R, cx, cy + R); g.addColorStop(0, 'rgba(255,255,255,0.28)'); g.addColorStop(0.5, 'rgba(255,255,255,0.04)'); g.addColorStop(1, 'rgba(0,0,0,0.5)');
    ctx.beginPath(); ctx.arc(cx, cy, rb - 0.5, 0, Math.PI * 2); ctx.strokeStyle = g; ctx.lineWidth = 1.2; ctx.stroke();
    // cap
    const rc = R - 17 * k;
    g = ctx.createRadialGradient(cx - rc * 0.4, cy - rc * 0.45, rc * 0.1, cx, cy, rc);
    g.addColorStop(0, cap.hi); g.addColorStop(0.55, cap.mid); g.addColorStop(1, cap.lo);
    ctx.beginPath(); ctx.arc(cx, cy, rc, 0, Math.PI * 2); ctx.fillStyle = g; ctx.fill();
    ctx.beginPath(); ctx.arc(cx, cy, rc + 1, 0, Math.PI * 2); ctx.strokeStyle = '#0b0d11'; ctx.lineWidth = 2; ctx.stroke();
    g = ctx.createRadialGradient(cx - rc * 0.35, cy - rc * 0.5, 0, cx - rc * 0.35, cy - rc * 0.5, rc * 0.9);
    g.addColorStop(0, 'rgba(255,255,255,0.35)'); g.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.beginPath(); ctx.arc(cx, cy, rc, 0, Math.PI * 2); ctx.fillStyle = g; ctx.fill();
    // pointer
    const a = angle(v);
    ctx.save(); ctx.translate(cx, cy); ctx.rotate(a + Math.PI / 2);
    ctx.shadowColor = 'rgba(255,255,255,0.6)'; ctx.shadowBlur = 5;
    ctx.beginPath(); ctx.moveTo(0, -(rb - 1.5)); ctx.lineTo(0, -(rc + 2));
    ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 2.6 * k; ctx.stroke(); ctx.restore();
  }

  // ── Glass fader (Settings > Controls > Sliders): same value contract, vertical ──
  function drawGlassFader(canvas, value127, wrap) {
    const sz = wrapSize(wrap, 48, 108), w = sz.w, h = sz.h, ctx = prep(canvas, w, h), x = w / 2, top = 12, bot = h - 12;
    const v = clamp127(value127), cap = capColours(wrap);
    const yFor = val => bot - (bot - top) * (clamp127(val) / 127);
    const y = yFor(v);
    // ticks
    for (let i = 0; i <= 10; i++) {
      const ty = bot - (bot - top) * (i / 10), long = (i === 0 || i === 5 || i === 10);
      ctx.beginPath(); ctx.moveTo(x - 12 - (long ? 4 : 2), ty); ctx.lineTo(x - 12, ty);
      ctx.strokeStyle = long ? 'rgba(255,255,255,0.5)' : 'rgba(255,255,255,0.22)'; ctx.lineWidth = 1; ctx.stroke();
    }
    // track
    rr(ctx, x - 3, top, 6, bot - top, 3); ctx.fillStyle = 'rgba(0,0,0,0.55)'; ctx.fill();
    rr(ctx, x - 3, top, 6, bot - top, 3); ctx.strokeStyle = 'rgba(255,255,255,0.10)'; ctx.lineWidth = 1; ctx.stroke();
    if (v > 0) {
      ctx.save(); ctx.shadowColor = 'rgba(255,122,26,0.75)'; ctx.shadowBlur = 6;
      rr(ctx, x - 2, y, 4, bot - y, 2); ctx.fillStyle = '#ff7a1a'; ctx.fill(); ctx.restore();
    }
    // baseline marker
    if (wrap && wrap.dataset.orig !== undefined && wrap.dataset.orig !== '') {
      const oy = yFor(parseInt(wrap.dataset.orig, 10));
      ctx.beginPath(); ctx.moveTo(x + 14, oy); ctx.lineTo(x + 19, oy - 3); ctx.lineTo(x + 19, oy + 3); ctx.closePath();
      ctx.fillStyle = '#ffb35c'; ctx.fill();
    }
    // cap
    const cw = 30, ch = 16;
    ctx.save(); ctx.shadowColor = 'rgba(0,0,0,0.7)'; ctx.shadowBlur = 6; ctx.shadowOffsetY = 3;
    let g = ctx.createLinearGradient(0, y - ch / 2, 0, y + ch / 2); g.addColorStop(0, '#3a4048'); g.addColorStop(0.55, '#1a1e25'); g.addColorStop(1, '#0b0d11');
    rr(ctx, x - cw / 2, y - ch / 2, cw, ch, 4); ctx.fillStyle = g; ctx.fill(); ctx.restore();
    rr(ctx, x - cw / 2 + 0.5, y - ch / 2 + 0.5, cw - 1, ch - 1, 4); ctx.strokeStyle = 'rgba(255,255,255,0.18)'; ctx.lineWidth = 1; ctx.stroke();
    g = ctx.createLinearGradient(x - cw / 2, 0, x + cw / 2, 0); g.addColorStop(0, cap.lo); g.addColorStop(0.4, cap.hi); g.addColorStop(1, cap.mid);
    rr(ctx, x - cw / 2 + 3, y - ch / 2 + 2.5, cw - 6, 3.5, 1.5); ctx.fillStyle = g; ctx.fill();
    ctx.beginPath(); ctx.moveTo(x - cw / 2 + 4, y + 2.5); ctx.lineTo(x + cw / 2 - 4, y + 2.5);
    ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 1.8; ctx.lineCap = 'round'; ctx.stroke();
  }

  function slidersOn() { return document.body.classList.contains('sliders'); }
  // Take over the tick-knob renderer: ui.js's drawKnob dispatches to
  // drawTickKnob by name for every data-style="tick" knob in the app.
  window.drawTickKnob = function (canvas, value127, wrap) {
    if (slidersOn()) drawGlassFader(canvas, value127, wrap); else drawGlassKnob(canvas, value127, wrap);
  };
  try { drawTickKnob = window.drawTickKnob; } catch (e) {}

  function repaintAllKnobs() {
    document.querySelectorAll('.knob-wrap[data-style="tick"]').forEach(function (wrap) {
      const c = wrap.querySelector('canvas.knob-canvas'); if (!c) return;
      if (typeof drawKnob === 'function') drawKnob(c, clamp127(wrap.dataset.value));
    });
  }

  // ════════════════════════════════════════════════════════════════
  // LAYOUT
  // ════════════════════════════════════════════════════════════════
  function buildLayout() {
    document.body.classList.add('studio');

    // ── Top bar: LCD · bank/patch · input · tuner · wordmark ──
    const top = $('topbar');
    const brand = top.querySelector('.app-title').parentElement;
    brand.classList.add('brand');
    const box = $('patch-name-box');
    const hint = box.querySelector('.hint');
    const slotLine = mk('div', { id: 'lcd-slot' });
    slotLine.appendChild(mk('span', { id: 'lcd-slot-text' }, '— · USER'));
    if (hint) { hint.textContent = '◀ user · factory ▶'; slotLine.appendChild(hint); }
    box.insertBefore(slotLine, box.firstChild);
    box.appendChild(mk('div', { id: 'lcd-sub' }, 'Waiting for the rack…'));
    box.title = 'Click the name to rename. Click the left half for the user patch list, the right half for the factory list.';
    const flexRow = top.querySelector('.flex-row.ml-auto');
    const sizeBtns = top.querySelector('.size-btns');
    [box, top.querySelector('.patch-nav'), $('input-group'), $('btn-tuner'), brand].forEach(el => el && top.appendChild(el));
    if (flexRow) flexRow.style.display = 'none';
    const winRow = $('settings-window-row');
    if (winRow && sizeBtns) winRow.querySelector('.settings-row-controls').insertBefore(sizeBtns, winRow.querySelector('.settings-row-controls').firstChild);

    // ── Signal path ──
    const strip = $('chainstrip');
    strip.insertBefore(mk('span', { class: 'cap' }, 'Signal path · click a block to focus · click its name to bypass · drag to reorder'), strip.firstChild);
    const inp = $('chain-input-wrap'), mono = $('mono-indicator');
    if (inp) inp.closest('.chain-slot').insertAdjacentElement('afterbegin', mk('div', { class: 'tile-ico' }, iconSvg('input')));
    if (mono) mono.closest('.chain-slot').insertAdjacentElement('afterbegin', mk('div', { class: 'tile-ico', id: 'stereo-ico' }, iconSvg('stereo')));

    // ── Focus: stage + side cards ──
    const main = $('main');
    const focus = mk('section', { class: 'glass focus mode-amp', id: 'focus' },
      '<span class="cap" id="focus-title">Focus · Amp</span><div id="focus-stage"></div><div id="focus-side"></div>');
    main.insertBefore(focus, main.firstChild);
    const stage = $('focus-stage'), side = $('focus-side');
    PANEL_IDS.forEach(id => { const p = $(id); if (p) stage.appendChild(p); });

    // The amp panel: header controls go to the side cards, row-1 groups go
    // to the master section, the tone knobs go onto the drawn amp.
    const ampPanel = $('panel-ampcab');
    const scard = ampPanel.querySelector('.scard');
    const ampDD = $('amp-select').closest('.ctrl-dd'), cabDD = $('cab-type-select').closest('.ctrl-dd'), micDD = $('mic-type-select').closest('.ctrl-dd');
    const axisTog = $('axis-btn').closest('.ctrl-tog'), breakup = $('breakup-slider').closest('.sctrl'), truez = $('truez-ctrl');
    const groups = Array.from(scard.querySelectorAll('.gate-group'));
    const globals = $('globals-group');
    const toneRow = $('tone-knobs-row'), togRow = $('amp-toggles-row'), dock = scard.querySelector('.tone-dock');

    const stagebox = mk('div', { class: 'stagebox' },
      '<div class="amp fam-black" id="amp-obj">' +
        '<div class="top-panel"><div class="chrome"></div>' +
          '<div class="jacks"><div class="jack"></div><span class="label">Input</span></div>' +
          '<div id="amp-controls"></div>' +
          '<div class="pilot-wrap"><div class="pilot"></div><span class="label">On</span></div>' +
        '</div>' +
        '<div class="cab"><div class="grille"><div class="speakers" id="amp-speakers" data-n="2"><i></i><i></i></div><div class="plate" id="amp-plate">Eleven Rack</div></div></div>' +
      '</div><div class="floor"></div>');
    ampPanel.appendChild(stagebox);
    $('amp-controls').appendChild(toneRow);
    $('amp-controls').appendChild(togRow);
    if (dock) $('amp-controls').appendChild(dock);

    const ampCard = mk('div', { class: 'glass card amp-card' }, '<h3>Amp, cabinet &amp; mic</h3>');
    ampCard.appendChild(kv(ampDD));
    ampCard.appendChild(mk('div', { class: 'kv' }, '<span class="label">Based on*</span><span class="txt" id="amp-based">—</span>'));
    const backline = mk('div', { class: 'backline', id: 'backline' });
    FAMILIES.forEach(f => backline.appendChild(mk('button', { type: 'button', class: 'backline-btn fam-' + f.key, 'data-fam': f.key, title: f.name + ' — click to switch to the first ' + f.name + ' amp' }, '<i></i><i></i>')));
    ampCard.appendChild(mk('div', { class: 'kv' }, '<span class="label">Backline</span>')).appendChild(backline);
    [cabDD, micDD, axisTog, breakup, truez].forEach(c => { if (c) ampCard.appendChild(kv(c)); });
    ampCard.appendChild(mk('div', { class: 'fine' }, '* Trademarks of their owners, not associated with 11 Edit or Avid. Named only to identify the amp each model is based on.'));
    const fxCard = mk('div', { class: 'glass card fx-card' },
      '<h3 id="fx-card-title">Block</h3>' +
      '<div class="kv"><span class="label">Model</span><span class="val" id="fx-card-model">—</span></div>' +
      '<div class="kv"><span class="label">State</span><span class="val" id="fx-card-state">—</span></div>' +
      '<div class="kv"><span class="label">Tip</span><span class="txt">The knobs on the pedal are the block\'s real parameters. The footswitch bypasses it, the same as clicking its name in the signal path.</span></div>' +
      '<button class="bt-btn" id="fx-card-back" type="button">Back to the amp</button>');
    side.appendChild(ampCard); side.appendChild(fxCard);
    $('fx-card-back').addEventListener('click', function () {
      const open = document.querySelector('.chain-open.panel-open'); if (open) open.click();
    });

    // ── Master section ──
    const master = mk('section', { class: 'glass master', id: 'master' }, '<span class="cap">Master section</span>');
    main.insertBefore(master, $('roller-strip'));
    const as = mk('div', { class: 'glass strip amps' }, '<span class="label">Amp section</span><div class="groups" id="master-groups"></div>');
    master.appendChild(as);
    groups.forEach(g => $('master-groups').appendChild(g));
    if (globals) $('master-groups').appendChild(globals);
    const ms = mk('div', { class: 'glass strip meters' },
      '<div class="vus">' +
        '<div class="vu"><canvas id="vu-l" width="200" height="118"></canvas><div class="label">Rig out L</div></div>' +
        '<div class="vu"><canvas id="vu-r" width="200" height="118"></canvas><div class="label">Rig out R</div></div>' +
      '</div><div class="vu-source" id="vu-source">Needle at main volume · MIDI activity</div><div class="meter-row" id="meter-row"></div>');
    master.appendChild(ms);
    $('meter-row').appendChild($('out-vol-group'));
    $('meter-row').appendChild($('tempo-wrap'));
    const rs = mk('div', { class: 'glass strip rig' }, '<span class="label">Rig &amp; bank</span><div id="rig-buttons"></div>');
    master.appendChild(rs);
    const rb = $('rig-buttons');
    [$('btn-save-menu').parentElement, $('btn-load-tfx'), $('btn-export-all-rigs'), $('btn-import-rigs'), $('btn-rig-balance'), $('btn-patches'), $('btn-about'), $('btn-manual'), $('btn-settings')]
      .forEach(b => { if (b) rb.appendChild(b); });
    main.appendChild($('roller-strip'));
    main.appendChild($('btoolbar'));

    // ── Effects as stompboxes ──
    Object.keys(PEDALS).forEach(id => {
      const p = $(id); if (!p) return;
      const cat0 = DOM_DEFAULT_CAT[PEDAL_DOM[id] || 'fx1'] || 'stomp';
      p.classList.add('pedal', 'color-' + (CAT_COLOR[cat0] || 'blue'));
      const hdr = p.querySelector('.scard-hdr');
      if (hdr) { const g = mk('div', { class: 'pedal-glyph', 'data-cat': cat0 }, iconSvg(cat0)); hdr.insertAdjacentElement('afterbegin', g); }
      if (id === 'panel-vol' || id === 'panel-wah') {
        const t = mk('div', { class: 'pedal-treadle', title: 'Treadle — the position is set from the rack\'s expression pedal' });
        if (hdr) hdr.insertAdjacentElement('afterend', t); else p.insertAdjacentElement('afterbegin', t);
      }
      p.appendChild(mk('span', { class: 'pedal-jack in', 'data-lbl': 'IN' }));
      p.appendChild(mk('span', { class: 'pedal-jack out', 'data-lbl': 'OUT' }));
      const foot = mk('div', { class: 'pedal-foot' }, '<div class="pedal-led-wrap"><span class="pedal-led"></span><span class="pedal-hint">On</span></div><button class="foot" type="button" title="Bypass / enable this block"></button><span class="pedal-hint">Bypass</span>');
      p.appendChild(foot);
      foot.querySelector('.foot').addEventListener('click', function () {
        const dom = pedalDom(id); const lbl = dom && $('chain-' + dom);
        if (lbl) lbl.click();
      });
    });

    // ── Patches panel: user/factory switch + search ──
    const mu = $('matrix-user'), mf = $('matrix-factory'), search = $('matrix-search');
    if (mu) mu.addEventListener('click', function () { setMatrixSpace(0); });
    if (mf) mf.addEventListener('click', function () { setMatrixSpace(1); });
    if (search) {
      search.addEventListener('input', applyMatrixFilter);
      search.addEventListener('keydown', function (e) { if (e.key === 'Escape') { search.value = ''; applyMatrixFilter(); } e.stopPropagation(); });
      search.addEventListener('click', function (e) { e.stopPropagation(); });
    }
    const patches = $('btn-patches');
    if (patches) patches.addEventListener('click', function () { if (typeof openJumpList === 'function') openJumpList(0); });
    if (typeof window.refreshMatrixCells === 'function') {
      const orig = window.refreshMatrixCells;
      window.refreshMatrixCells = function () { const r = orig.apply(this, arguments); applyMatrixFilter(); syncMatrixSeg(); return r; };
      try { refreshMatrixCells = window.refreshMatrixCells; } catch (e) {}
    }

    // ── Backline thumbnails: switch to the first amp of that family ──
    backline.addEventListener('click', function (e) {
      const b = e.target.closest('.backline-btn'); if (!b) return;
      const sel = $('amp-select'); if (!sel || sel.disabled || typeof AMP_SELECT_LIST === 'undefined') return;
      const first = AMP_SELECT_LIST.find(a => AMP_FAMILY[a.key] === b.dataset.fam);
      if (!first || sel.value === first.key) return;
      sel.value = first.key;
      sel.dispatchEvent(new Event('change'));
    });
  }

  function pedalDom(panelId) {
    if (panelId === 'panel-fxhost') {
      const slot = (typeof openFxHostSlot !== 'undefined') ? openFxHostSlot : null;
      return (slot !== null && typeof SLOT_ID_TO_DOM !== 'undefined') ? SLOT_ID_TO_DOM[slot] : null;
    }
    return PEDAL_DOM[panelId] || null;
  }

  // ════════════════════════════════════════════════════════════════
  // STATE MIRRORS — LCD lines, the drawn amp, side cards, pedal LEDs
  // ════════════════════════════════════════════════════════════════
  let syncQueued = false;
  function scheduleSync() { if (syncQueued) return; syncQueued = true; requestAnimationFrame(function () { syncQueued = false; syncAll(); }); }

  function selectedText(id) {
    const s = $(id); if (!s || s.selectedIndex < 0) return '';
    const o = s.options[s.selectedIndex]; if (!o || o.disabled || o.value === '' || o.value === '-1') return '';
    return o.textContent.trim();
  }
  function syncAll() {
    try { syncLCD(); syncAmp(); syncChainIcons(); syncFocus(); syncMatrixSeg(); } catch (e) { /* never let a readout break the app */ }
  }
  function syncLCD() {
    const t = $('lcd-slot-text'); if (!t) return;
    const slot = (typeof currentSlot === 'number') ? currentSlot : 0;
    const lbl = (typeof slotLabel === 'function') ? slotLabel(slot) : '—';
    t.textContent = lbl + ' · ' + (slot > 103 ? 'FACTORY' : 'USER');
    const sub = $('lcd-sub'); if (!sub) return;
    const parts = [];
    const amp = (typeof currentAmpName !== 'undefined' && currentAmpName) ? currentAmpName : '';
    if (amp) parts.push(amp);
    const cab = selectedText('cab-type-select'); if (cab) parts.push(cab);
    const mic = selectedText('mic-type-select'); if (mic) parts.push(mic);
    sub.textContent = parts.length ? parts.join(' · ') : (typeof bridgeMidiReady !== 'undefined' && bridgeMidiReady ? 'Reading the patch…' : 'Waiting for the rack…');
  }
  function syncAmp() {
    const key = (typeof currentAmpKey !== 'undefined') ? currentAmpKey : null;
    const fam = (key && AMP_FAMILY[key]) || 'black';
    const obj = $('amp-obj'); if (obj) obj.className = 'amp fam-' + fam;
    const plate = $('amp-plate'); if (plate) plate.textContent = (typeof currentAmpName !== 'undefined' && currentAmpName) ? currentAmpName : 'Eleven Rack';
    const based = $('amp-based'); if (based) based.textContent = key ? (AMP_BASED_ON[key] || '—') : '—';
    document.querySelectorAll('.backline-btn').forEach(b => b.classList.toggle('on', !!key && b.dataset.fam === fam));
    const cabSel = $('cab-type-select');
    const idx = cabSel ? parseInt(cabSel.value, 10) : -1;
    const n = (idx >= 0 && CAB_SPEAKERS[idx]) ? CAB_SPEAKERS[idx] : 2;
    const sp = $('amp-speakers');
    if (sp && sp.dataset.n !== String(n)) { sp.dataset.n = String(n); sp.innerHTML = '<i></i>'.repeat(n); }
  }
  function syncFocus() {
    const focus = $('focus'); if (!focus) return;
    const title = $('focus-title');
    const settings = $('panel-settings');
    let mode = 'none', name = '', pedal = null;
    if (settings && settings.style.display === 'flex') { mode = 'settings'; name = 'Settings'; }
    else if ($('panel-ampcab').style.display !== 'none') { mode = 'amp'; name = 'Focus · Amp'; }
    else {
      Object.keys(PEDALS).forEach(id => { const p = $(id); if (p && p.style.display !== 'none') pedal = p; });
      if (pedal) {
        mode = 'fx';
        const t = pedal.querySelector('.scard-title');
        name = 'Focus · ' + (t ? t.textContent.trim() : 'Effect');
      } else if ($('panel-other').style.display !== 'none') { mode = 'fx'; name = 'Focus · Effect'; }
    }
    ['mode-amp', 'mode-fx', 'mode-settings', 'mode-none'].forEach(c => focus.classList.remove(c));
    focus.classList.add('mode-' + mode);
    if (title) title.textContent = name || 'Focus';
    // pedal: colour for the shared host panel, LED + fx card from the chain label
    if (pedal) {
      const dom = pedalDom(pedal.id), lbl = dom ? $('chain-' + dom) : null;
      const msel = pedal.querySelector('.scard-hdr select');
      const mname = (msel && msel.options[msel.selectedIndex]) ? msel.options[msel.selectedIndex].textContent.trim() : '';
      const cat = catFor(dom, mname);
      const color = 'color-' + (CAT_COLOR[cat] || 'blue');
      if (!pedal.classList.contains(color)) { Array.from(pedal.classList).filter(c => c.indexOf('color-') === 0).forEach(c => pedal.classList.remove(c)); pedal.classList.add(color); }
      const gl = pedal.querySelector('.pedal-glyph'); if (gl && gl.dataset.cat !== cat) { gl.dataset.cat = cat; gl.innerHTML = iconSvg(cat); }
      const on = !!(lbl && lbl.classList.contains('slot-on'));
      const off = !!(lbl && lbl.classList.contains('slot-off'));
      pedal.classList.toggle('on', on);
      const ft = $('fx-card-title'), fm = $('fx-card-model'), fs = $('fx-card-state');
      const t = pedal.querySelector('.scard-title');
      if (ft) ft.textContent = t ? t.textContent.trim() : 'Block';
      const sel = pedal.querySelector('.scard-hdr select');
      if (fm) fm.textContent = sel ? (sel.options[sel.selectedIndex] ? sel.options[sel.selectedIndex].textContent.trim() : '—') : (lbl && lbl.title ? lbl.title.replace(/^.*— /, '') : '—');
      if (fs) fs.textContent = on ? 'Active' : off ? 'Bypassed' : 'Unknown';
    }
    const master = $('master'), ampPanel = $('panel-ampcab');
    if (master && ampPanel) master.classList.toggle('hide-row1-nums', ampPanel.classList.contains('hide-row1-nums'));
  }

  // ── Patches panel helpers ──
  function setMatrixSpace(space) {
    if (typeof matrixSpace === 'undefined') return;
    if (space === 1 && typeof matrixPickerResolve !== 'undefined' && matrixPickerResolve) return;   // picking a save slot: user space only
    matrixSpace = space;
    if (typeof setMatrixScopeText === 'function') setMatrixScopeText(space === 1 ? 'FACTORY PATCHES — click to jump' : 'USER PATCHES — click to jump');
    if (typeof refreshMatrixCells === 'function') refreshMatrixCells();
    if (typeof updateMatrixHighlight === 'function' && typeof currentSlot !== 'undefined') updateMatrixHighlight(currentSlot);
    syncMatrixSeg();
  }
  function syncMatrixSeg() {
    const mu = $('matrix-user'), mf = $('matrix-factory'); if (!mu || !mf) return;
    const space = (typeof matrixSpace !== 'undefined') ? matrixSpace : 0;
    mu.classList.toggle('on', space === 0); mf.classList.toggle('on', space === 1);
    const picking = (typeof matrixPickerResolve !== 'undefined') && !!matrixPickerResolve;
    mf.disabled = picking; mf.title = picking ? 'Factory patches are read-only, so a save slot must be a user slot' : '';
  }
  function applyMatrixFilter() {
    const s = $('matrix-search'); const q = s ? s.value.trim().toLowerCase() : '';
    document.querySelectorAll('.matrix-name-cell').forEach(function (c) {
      const hit = !!q && c.textContent.toLowerCase().indexOf(q) !== -1;
      c.classList.toggle('dim', !!q && !hit); c.classList.toggle('hit', hit);
    });
  }

  // ── Hooks: wrap the app's own updaters so the mirrors repaint right after them ──
  function hook(name) {
    const orig = window[name]; if (typeof orig !== 'function') return;
    window[name] = function () { const r = orig.apply(this, arguments); scheduleSync(); return r; };
  }
  function installHooks() {
    ['setCurrentAmp', 'updateCabTypeDisplay', 'updateMicTypeDisplay', 'updateAxisDisplay', 'updateBreakupDisplay', 'updateDisplay',
     'setTrueZDisplay', 'openFxHostPanel', 'closeFxHostPanel', 'refreshBlockBypassDisplays', 'updateMonoIndicator', 'applyNumberDisplayMode'].forEach(hook);
    ['amp-select', 'cab-type-select', 'mic-type-select', 'dist-model-select', 'reverb-model-select', 'wah-model-select', 'delay-model-select', 'fxhost-model-select']
      .forEach(id => { const s = $(id); if (s) s.addEventListener('change', scheduleSync); });
    const styleObs = new MutationObserver(scheduleSync);
    PANEL_IDS.forEach(id => { const p = $(id); if (p) styleObs.observe(p, { attributes: true, attributeFilter: ['style', 'class'] }); });
    const strip = $('chainstrip');
    if (strip) new MutationObserver(scheduleSync).observe(strip, { attributes: true, subtree: true, attributeFilter: ['class'] });
    const sd = $('slot-display');
    if (sd) new MutationObserver(scheduleSync).observe(sd, { childList: true, characterData: true, subtree: true });
    const sm = $('slot-matrix');
    if (sm) new MutationObserver(function () { syncMatrixSeg(); if (sm.classList.contains('open')) { const s = $('matrix-search'); if (s) { s.value = ''; applyMatrixFilter(); setTimeout(function () { s.focus(); }, 50); } } }).observe(sm, { attributes: true, attributeFilter: ['class'] });
    setInterval(syncAll, 1000);   // safety net: deferred paints land after the hooks fire
  }

  // ════════════════════════════════════════════════════════════════
  // VU METERS — Rig Out L/R. Until the audio driver feeds real level the
  // needle sits at the main volume and twitches on incoming MIDI.
  // window.studioVU.setLevels(dbL, dbR) is the hook for a real source.
  // ════════════════════════════════════════════════════════════════
  const SCALE = [[-20, -46], [-10, -26], [-7, -15], [-5, -7], [-3, 3], [-2, 8], [-1, 13], [0, 19], [1, 27], [2, 36], [3, 46]];
  function dbToAngle(db) {
    if (db <= SCALE[0][0]) return SCALE[0][1];
    for (let i = 1; i < SCALE.length; i++) {
      if (db <= SCALE[i][0]) { const t = (db - SCALE[i - 1][0]) / (SCALE[i][0] - SCALE[i - 1][0]); return SCALE[i - 1][1] + t * (SCALE[i][1] - SCALE[i - 1][1]); }
    }
    return SCALE[SCALE.length - 1][1];
  }
  const VU = { l: { angle: -46, last: 0 }, r: { angle: -46, last: 0 }, kick: 0, peakUntil: 0, raf: null, ext: null, extAt: 0 };
  function fallbackDb() {
    const v = (typeof currentMasterVol === 'number') ? currentMasterVol : null;
    if (v === null) return -20;
    return -20 + 23 * Math.pow(v / 127, 0.55);
  }
  function vuKick() { VU.kick = Math.min(4, VU.kick + 1.2); VU.peakUntil = performance.now() + 140; }
  function rad(deg) { return (deg - 90) * Math.PI / 180; }

  function drawMeter(canvas, m, db, now, label) {
    const w = 200, h = 118, ctx = prep(canvas, w, h);
    const dt = Math.min(0.05, (now - (m.last || now)) / 1000); m.last = now;
    const target = dbToAngle(db);
    m.angle += (target - m.angle) * Math.min(1, dt * 14);
    // face
    let g = ctx.createRadialGradient(w / 2, h * 0.1, 4, w / 2, h * 0.6, w * 0.8);
    g.addColorStop(0, '#f8f0da'); g.addColorStop(0.6, '#f1e7cc'); g.addColorStop(1, '#d0c09b');
    rr(ctx, 0, 0, w, h, 8); ctx.fillStyle = g; ctx.fill();
    g = ctx.createRadialGradient(w / 2, h * 0.1, 2, w / 2, h * 0.1, w * 0.6);
    g.addColorStop(0, 'rgba(255,196,110,0.35)'); g.addColorStop(1, 'rgba(255,196,110,0)');
    ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
    // scale: an arc from the pivot, red only from 0 to +3
    const px = w / 2, py = h, r = 88;
    const arc = function (a0, a1, col, lw) { ctx.beginPath(); ctx.arc(px, py, r, rad(a0), rad(a1)); ctx.strokeStyle = col; ctx.lineWidth = lw; ctx.lineCap = 'butt'; ctx.stroke(); };
    arc(SCALE[0][1], dbToAngle(0), '#1a1a1a', 2);
    arc(dbToAngle(0), SCALE[SCALE.length - 1][1], '#c8281e', 4);
    ctx.font = '700 9px Manrope, Helvetica, Arial, sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    const shown = [-20, -10, -7, -5, -3, 0, 3];
    SCALE.forEach(function (s) {
      const a = rad(s[1]), red = s[0] >= 0;
      const t0 = r - (red ? 6 : 5), t1 = r + 2;
      ctx.beginPath(); ctx.moveTo(px + Math.cos(a) * t0, py + Math.sin(a) * t0); ctx.lineTo(px + Math.cos(a) * t1, py + Math.sin(a) * t1);
      ctx.strokeStyle = red ? '#c8281e' : '#1a1a1a'; ctx.lineWidth = s[0] === 0 ? 1.8 : 1.2; ctx.stroke();
      if (shown.indexOf(s[0]) !== -1) {
        ctx.fillStyle = red ? '#b4221a' : '#1a1a1a';
        ctx.fillText(s[0] > 0 ? '+' + s[0] : String(s[0]), px + Math.cos(a) * (r - 14), py + Math.sin(a) * (r - 14));
      }
    });
    ctx.font = '800 15px Manrope, Helvetica, Arial, sans-serif'; ctx.fillStyle = '#2a2622'; ctx.fillText('VU', px, h - 22);
    ctx.font = '700 6.5px Manrope, Helvetica, Arial, sans-serif'; ctx.fillStyle = '#5a534a'; ctx.fillText(label, px, h - 10);
    // needle + pivot
    const a = rad(m.angle);
    ctx.save(); ctx.shadowColor = 'rgba(0,0,0,0.35)'; ctx.shadowBlur = 2; ctx.shadowOffsetY = 1;
    ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(px + Math.cos(a) * (r + 6), py + Math.sin(a) * (r + 6));
    ctx.strokeStyle = '#111'; ctx.lineWidth = 1.6; ctx.lineCap = 'round'; ctx.stroke(); ctx.restore();
    ctx.beginPath(); ctx.arc(px, py, 10, 0, Math.PI * 2); ctx.fillStyle = '#2b2e33'; ctx.fill();
    // peak lamp
    const lit = now < VU.peakUntil || db >= 2;
    ctx.beginPath(); ctx.arc(w - 14, 14, 3.5, 0, Math.PI * 2); ctx.fillStyle = lit ? '#ff3b30' : '#5a1a16'; ctx.fill();
    if (lit) { ctx.save(); ctx.shadowColor = '#ff3b30'; ctx.shadowBlur = 8; ctx.fill(); ctx.restore(); }
    ctx.font = '700 5.5px Manrope, Helvetica, Arial, sans-serif'; ctx.fillStyle = '#5a534a'; ctx.fillText('PEAK', w - 14, 23);
  }
  function vuLoop(now) {
    const cl = $('vu-l'), cr = $('vu-r');
    if (!cl || !cr) { VU.raf = null; return; }
    const dt = 1 / 60;
    VU.kick *= Math.exp(-dt / 0.22);
    let dbL, dbR;
    if (VU.ext && now - VU.extAt < 400) { dbL = VU.ext.l; dbR = VU.ext.r; }
    else { dbL = fallbackDb() + VU.kick; dbR = fallbackDb() + VU.kick * 0.8; }
    drawMeter(cl, VU.l, dbL, now, 'RIG OUT L');
    drawMeter(cr, VU.r, dbR, now, 'RIG OUT R');
    VU.raf = requestAnimationFrame(vuLoop);
  }
  function startVU() { if (!VU.raf) VU.raf = requestAnimationFrame(vuLoop); }
  window.studioVU = {
    setLevels: function (dbL, dbR) { VU.ext = { l: dbL, r: dbR }; VU.extAt = performance.now(); },
    setSource: function (text) { const s = $('vu-source'); if (s) s.textContent = text; },
    kick: vuKick,
  };
  if (typeof handleBridgeMsg === 'function') {
    const orig = handleBridgeMsg;
    window.handleBridgeMsg = function (msg) { if (msg && msg.type === 'midi_in') vuKick(); return orig(msg); };
    try { handleBridgeMsg = window.handleBridgeMsg; } catch (e) {}
  }
  // Real level from the audio driver: main.js streams the engine's RMS meter
  // for Eleven Rig L/R (0..1 linear) ~30x/s. 0 VU is placed at -18 dBFS RMS.
  const FALLBACK_TEXT = 'Needle at main volume';
  let vuState = '';
  function vuSetState(state, text) { if (vuState === state) return; vuState = state; VU.ext = null; window.studioVU.setSource(text); }
  function rmsToVu(x) { return 20 * Math.log10(Math.max(x, 1e-6)) + 18; }
  if (window.electronAPI && typeof window.electronAPI.onVuLevels === 'function') {
    window.electronAPI.onVuLevels(function (d) {
      if (!d || d.available === false) { vuSetState('off', FALLBACK_TEXT + ' · MIDI activity · no audio driver'); return; }
      if (!d.running) { vuSetState('idle', FALLBACK_TEXT + ' · driver ready, rack audio idle'); return; }
      vuSetState('live', 'Rig out L / R · live' + (d.rate ? ' · ' + (d.rate / 1000).toFixed(1).replace(/\.0$/, '') + ' kHz' : ''));
      window.studioVU.setLevels(rmsToVu(d.l), rmsToVu(d.r));
    });
  }

  // ── Controls: knobs or sliders (Settings > Controls) ──
  function applyControls(mode, persist) {
    const sliders = mode === 'sliders';
    document.body.classList.toggle('sliders', sliders);
    if (persist) { try { localStorage.setItem(CTL_KEY, sliders ? 'sliders' : 'knobs'); } catch (e) {} }
    document.querySelectorAll('.settings-ctl-btn').forEach(b => b.classList.toggle('on', (b.dataset.ctl === 'sliders') === sliders));
    repaintAllKnobs();
  }

  // ── Boot ──
  buildLayout();
  installHooks();
  let saved = null;
  try { saved = localStorage.getItem(CTL_KEY); } catch (e) {}
  applyControls(saved || 'knobs', false);
  document.querySelectorAll('.settings-ctl-btn').forEach(b => b.addEventListener('click', function () { applyControls(b.dataset.ctl, true); }));
  syncAll();
  startVU();
  document.addEventListener('DOMContentLoaded', function () { repaintAllKnobs(); syncAll(); startVU(); });
})();
