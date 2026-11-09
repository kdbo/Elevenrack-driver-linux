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
  // ── Device look-alikes: per-model faceplates that resemble the gear a model
  // is based on — shape, colours and control layout only, with the rack's own
  // model names and no maker's logo or lettering. Models without an entry keep
  // the family amp / category pedal above. Values are look keys in studio.css.
  const AMP_DEVICE = { plexivari: 'plexi-vari', plexi50: 'plexi-50', plexi100: 'plexi-100', j45: 'jtm45', lead800: 'lead800', ac_hi: 'ac30', tweed_bass: 'tweed-bass', tweed_lux: 'tweed-lux', lux_vib: 'lux-vib', lux_norm: 'lux-norm' };
  const CAB_DEVICE = { 2: 'tweed112', 4: 'ac212', 8: 'tweed410', 10: 'mk1960c30', 11: 'mk1960', 12: 'basket412', 13: 'green20' };   // by cab-type-select index
  const MIC_DEVICE = { 1: 'dyn57' };        // by mic-type-select index
  const DIST_DEVICE = { 0x17: 'tri-fuzz', 0x18: 'black-op', 0x19: 'green-jrc', 0x1A: 'white-boost', 0x1B: 'dc-dist' };
  const WAH_DEVICE = { 0x23: 'shine-wah', 0x24: 'black-wah' };
  const DELAY_DEVICE = { 0x1C: 'ep-3', 0x1D: 'ep-3', 0x1E: 'memory-man', 0x1F: 'memory-man', 0x20: 'dyn-delay', 0x21: 'dyn-delay', 0x22: 'dyn-delay' };
  const REVERB_DEVICE = { 0x26: 'blackpanel', 0x27: 'blackpanel', 0x28: 'eleven-sr', 0x29: 'eleven-sr', 0x2A: 'eleven-sr' };
  // mod / FX models (FX1, FX2 and MOD share one host panel), by every mid of the model
  const FX_DEVICE = { 0x01: 'ce-1', 0x02: 'ce-1', 0x03: 'ce-1', 0x09: 'uni-vibe', 0x0A: 'uni-vibe', 0x0B: 'orange-phaser', 0x0C: 'orange-phaser', 0x14: 'gray-comp', 0x0D: 'roto', 0x0E: 'roto', 0x0F: 'roto',
    0x04: 'multi-chorus', 0x05: 'multi-chorus', 0x06: 'multi-chorus', 0x07: 'flanger', 0x08: 'flanger', 0x10: 'graphic-eq', 0x11: 'graphic-eq',
    0x12: 'param-eq', 0x13: 'param-eq', 0x15: 'dyn3', 0x16: 'dyn3' };
  // knob drawn on each look ('' = the app's normal round knob)
  const DEVICE_KNOB = { plexi: 'plexi', 'green-jrc': 'ts', 'black-op': 'rat', 'white-boost': 'rc', 'dc-dist': 'dc', 'tri-fuzz': 'muff', 'shine-wah': 'v847', 'black-wah': 'crybaby', 'fv-vol': 'fv' };
  // printed name on a pedal look: [name, type line]
  const DEVICE_LEGEND = { 'green-jrc': ['Green JRC', 'Overdrive'], 'black-op': ['Black Op', 'Distortion'], 'white-boost': ['White', '-booster'], 'dc-dist': ['DC', 'Distortion'], 'tri-fuzz': ['Tri-Knob', 'Fuzz'] };
  // Surface textures for the looks, as SVG tiles in CSS variables (--tex-*).
  // The browser rasterises each tile once, so they cost nothing per frame.
  function svgTile(w, h, body) {
    return 'url("data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="' + w + '" height="' + h + '">' + body + '</svg>') + '")';
  }
  const noise = (freq, oct, after) => '<filter id="f" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="' + freq + '" numOctaves="' + oct + '" stitchTiles="stitch" result="n"/>' + after + '</filter><rect width="100%" height="100%" filter="url(#f)"/>';
  const TEXTURES = {
    // pebbled vinyl covering, lit from the top left
    levant: svgTile(180, 180, noise('.6', 3, '<feDiffuseLighting in="n" surfaceScale="2.4" lighting-color="#3b3b3e"><feDistantLight azimuth="225" elevation="58"/></feDiffuseLighting>')),
    // fine horizontal brushing, as light streaks over the panel colour
    brushed: svgTile(420, 90, noise('.003 .9', 2, '<feColorMatrix type="matrix" values="0 0 0 0 1  0 0 0 0 .97  0 0 0 0 .85  1.6 0 0 0 -.78"/>')),
    // metal flake in a painted finish
    flake: svgTile(120, 120, noise('1.6', 1, '<feColorMatrix type="matrix" values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  2.2 0 0 0 -1.5"/>')),
    // crinkled black paint
    wrinkle: svgTile(160, 160, noise('.32', 2, '<feDiffuseLighting in="n" surfaceScale="1.6" lighting-color="#3a3a3d"><feDistantLight azimuth="225" elevation="62"/></feDiffuseLighting>')),
    // basket weave: pairs of tan threads, alternating direction per cell
    basket: svgTile(12, 12,
      '<rect width="12" height="12" fill="#1e1a14"/>' +
      '<g fill="#cdbb91"><rect x=".3" y=".6" width="5.4" height="2"/><rect x=".3" y="3.4" width="5.4" height="2"/>' +
      '<rect x="6.6" y="6.3" width="2" height="5.4"/><rect x="9.4" y="6.3" width="2" height="5.4"/></g>' +
      '<g fill="#a99670"><rect x="6.6" y=".3" width="2" height="5.4"/><rect x="9.4" y=".3" width="2" height="5.4"/>' +
      '<rect x=".3" y="6.6" width="5.4" height="2"/><rect x=".3" y="9.4" width="5.4" height="2"/></g>' +
      '<g fill="rgba(255,255,255,.25)"><rect x=".3" y=".6" width="5.4" height=".5"/><rect x=".3" y="3.4" width="5.4" height=".5"/>' +
      '<rect x=".3" y="6.6" width="5.4" height=".5"/><rect x=".3" y="9.4" width="5.4" height=".5"/></g>'),
  };
  Object.keys(TEXTURES).forEach(k => document.documentElement.style.setProperty('--tex-' + k, TEXTURES[k]));
  const PANEL_IDS = ['panel-ampcab','panel-other', 'panel-dist', 'panel-reverb', 'panel-wah', 'panel-vol', 'panel-fxloop', 'panel-delay', 'panel-fxhost', 'panel-settings'];

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
  // Signal-path thumbnails of the look-alikes: the device in miniature.
  const DEVICE_ICON = {
    'green-jrc': '<rect x="7" y="2" width="14" height="24" rx="2" fill="#2bb04f" stroke="rgba(0,0,0,.55)"/><path d="M7.5 11.5 h13" stroke="rgba(0,0,0,.35)" stroke-width="1"/>' +
      '<circle cx="14" cy="3.6" r=".8" fill="#ff5a4a"/><circle cx="10.2" cy="6.4" r="2.1" fill="#111"/><circle cx="17.8" cy="6.4" r="2.1" fill="#111"/><circle cx="14" cy="9" r="1.9" fill="#111"/>' +
      '<rect x="8.6" y="13" width="10.8" height="11.6" fill="none" stroke="#f6faf4" stroke-width=".6"/><rect x="10.2" y="14.6" width="7.6" height="1.6" fill="#f6faf4"/>' +
      '<rect x="12.2" y="19" width="3.6" height="3.2" rx=".4" fill="#ddd5c2" stroke="#8a826e" stroke-width=".5"/>',
    'black-op': '<rect x="9" y="2.4" width="2.4" height="1.8" fill="#c9cdd2"/><rect x="16.6" y="2.4" width="2.4" height="1.8" fill="#c9cdd2"/>' +
      '<rect x="4" y="3.5" width="2.2" height="22.5" rx=".5" fill="#0e0e10"/><rect x="21.8" y="3.5" width="2.2" height="22.5" rx=".5" fill="#0e0e10"/><rect x="6" y="4.2" width="16" height="21" fill="#29292b" stroke="rgba(0,0,0,.6)" stroke-width=".5"/>' +
      '<rect x="7.2" y="5.8" width="13.6" height="2.4" fill="none" stroke="#dcdee1" stroke-width=".5"/><path d="M11.7 5.8 v2.4 M16.3 5.8 v2.4" stroke="#dcdee1" stroke-width=".5"/>' +
      '<circle cx="9.5" cy="11.4" r="1.6" fill="#0c0c0d" stroke="#dcdee1" stroke-width=".4"/><circle cx="14" cy="11.4" r="1.6" fill="#0c0c0d" stroke="#dcdee1" stroke-width=".4"/><circle cx="18.5" cy="11.4" r="1.6" fill="#0c0c0d" stroke="#dcdee1" stroke-width=".4"/>' +
      '<rect x="8.2" y="14.6" width="11.6" height="3.6" fill="none" stroke="#f6f6f6" stroke-width=".7"/><rect x="9.6" y="15.8" width="8.8" height="1.3" fill="#f6f6f6"/><circle cx="14" cy="22" r="1.5" fill="#d4d8dd" stroke="#6a7078" stroke-width=".6"/>',
    'white-boost': '<rect x="7.5" y="2" width="13" height="24" rx="2" fill="#f2f1ec" stroke="rgba(0,0,0,.55)"/><path d="M9 9 v14.5 h10 v-14.5" fill="none" stroke="#222" stroke-width=".5"/>' +
      '<circle cx="11" cy="5" r="1.7" fill="#111" stroke="#b8bec6" stroke-width=".5"/><circle cx="17" cy="5" r="1.7" fill="#111" stroke="#b8bec6" stroke-width=".5"/><circle cx="11" cy="9.6" r="1.7" fill="#111" stroke="#b8bec6" stroke-width=".5"/><circle cx="17" cy="9.6" r="1.7" fill="#111" stroke="#b8bec6" stroke-width=".5"/>' +
      '<rect x="11.4" y="13" width="5.2" height="2" fill="#222"/><circle cx="14" cy="17.4" r=".7" fill="#4aa8ff"/><circle cx="14" cy="20.4" r="1.6" fill="#d4d8dd" stroke="#6a7078" stroke-width=".6"/>',
    'fv-vol': '<path d="M2.5 22.5 L25.5 22.5 L25 18 L5 18 Z" fill="#1c1c1e" stroke="rgba(0,0,0,.6)" stroke-width=".5"/><path d="M3 12.4 L24.5 16.4 L24.2 18.4 L2.6 14.4 Z" fill="#232325" stroke="#000" stroke-width=".5"/>' +
      '<path d="M3.2 12 L8 12.9" stroke="#c8d8e2" stroke-width="1.4"/><path d="M9 12.6 h1.6 M12 13.2 h1.6 M15 13.7 h1.6 M18 14.3 h1.6 M21 14.8 h1.6" stroke="#3a3a3c" stroke-width="1.2"/><circle cx="12" cy="20" r="1.3" fill="#a6c4d2"/>',
    'shine-wah': '<path d="M2.5 22 L25.5 22 L24.5 16 L3.5 16 Z" fill="#2a2a2c" stroke="rgba(0,0,0,.6)" stroke-width=".5"/><rect x="4.5" y="17.4" width="5" height="3" rx=".5" fill="#141416" stroke="#666" stroke-width=".3"/>' +
      '<path d="M3 11 L23 14.6 L22.6 16.6 L2.6 13 Z" fill="#e4e7eb" stroke="#6a7078" stroke-width=".5"/><rect x="6" y="13.4" width="1.6" height="2.8" fill="#c9cdd2"/><rect x="4" y="22" width="2" height="1.4" fill="#0b0b0c"/><rect x="21.5" y="22" width="2" height="1.4" fill="#0b0b0c"/>',
    'black-wah': '<path d="M2.5 22 L25.5 22 L24.5 16 L3.5 16 Z" fill="#1e1e20" stroke="rgba(0,0,0,.6)" stroke-width=".5"/><rect x="4.5" y="17.4" width="5" height="3" rx=".5" fill="#0e0e10" stroke="#555" stroke-width=".3"/>' +
      '<path d="M3 11 L23 14.6 L22.6 16.6 L2.6 13 Z" fill="#2a2a2c" stroke="#000" stroke-width=".5"/><path d="M4 10.6 L21 13.7" stroke="#000" stroke-width="1"/><rect x="6" y="13.4" width="1.6" height="2.8" fill="#c9cdd2"/><rect x="4" y="22" width="2" height="1.4" fill="#0b0b0c"/><rect x="21.5" y="22" width="2" height="1.4" fill="#0b0b0c"/>',
    'tri-fuzz': '<rect x="3.5" y="4" width="21" height="22" rx="1" fill="#d6d8db" stroke="rgba(0,0,0,.55)" stroke-width=".6"/><rect x="9" y="3" width="2.2" height="1.4" fill="#9aa0a8"/><rect x="16.8" y="3" width="2.2" height="1.4" fill="#9aa0a8"/>' +
      '<path d="M5 11.5 v-4.5 q0 -1.6 1.6 -1.6 h14.8 q1.6 0 1.6 1.6 v4.5 z" fill="none" stroke="#111" stroke-width=".6"/><circle cx="8.6" cy="8.6" r="1.8" fill="#151515"/><circle cx="14" cy="8.6" r="1.8" fill="#151515"/><circle cx="19.4" cy="8.6" r="1.8" fill="#151515"/>' +
      '<path d="M5 12.6 h18" stroke="#d23a26" stroke-width=".6"/><rect x="6.5" y="13.4" width="15" height="2.4" fill="#d23a26"/><path d="M5 16.6 h6 a3 3 0 0 0 6 0 h6" fill="none" stroke="#d23a26" stroke-width=".6"/>' +
      '<path d="M5 17.6 h5.4 a3.6 3.6 0 0 0 7.2 0 h5.4 v6 q0 1 -1 1 h-16 q-1 0 -1 -1 z" fill="#111"/><circle cx="14" cy="22" r="1.2" fill="#d4d8dd" stroke="#6a7078" stroke-width=".5"/>',
    'dc-dist': '<path d="M9 2 h10 q4 0 4 4 v1.5 q1 1 1 3 v11 q0 4.5 -4.5 4.5 h-11 q-4.5 0 -4.5 -4.5 v-11 q0 -2 1 -3 v-1.5 q0 -4 4 -4 z" fill="#b8601a" stroke="rgba(0,0,0,.6)" stroke-width=".6"/>' +
      '<path d="M9.3 2.3 h9.4 q3.4 0 3.6 2.4 h-16.6 q.2 -2.4 3.6 -2.4 z" fill="#5a2412"/><path d="M5 9.6 h18" stroke="rgba(0,0,0,.3)" stroke-width=".6"/>' +
      '<circle cx="9" cy="6.6" r="1.6" fill="#111"/><circle cx="14" cy="6.2" r="1.6" fill="#111"/><circle cx="19" cy="6.6" r="1.6" fill="#111"/><circle cx="14" cy="14.4" r="2.8" fill="#111"/>' +
      '<circle cx="14" cy="19.2" r=".7" fill="#4ad8ff"/><rect x="12.4" y="21" width="3.2" height="3" rx=".8" fill="#d4d8dd" stroke="#6a7078" stroke-width=".5"/>',
    plexi: '<rect x="11" y="2.6" width="6" height="1.6" rx=".7" fill="#2a2a2c"/><rect x="3" y="4" width="22" height="12" rx="1.5" fill="#1a1a1c" stroke="#000" stroke-width=".6"/>' +
      '<rect x="4.4" y="5.4" width="19.2" height="9.4" fill="none" stroke="#e6dcc0" stroke-width=".5"/><path d="M8.5 9 c1 -1.6 2 -1.6 2.4 0 s1.4 1.4 2.4 0 s1.6 -1.2 2.6 0 s1.6 1 3 -.4" stroke="#f1e7c6" stroke-width=".9" fill="none" stroke-linecap="round"/>' +
      '<rect x="7" y="11.6" width="14" height="3.2" fill="#d9bf7a"/><path d="M9.5 13.2 h.01 M11.5 13.2 h.01 M13.5 13.2 h.01 M15.5 13.2 h.01 M17.5 13.2 h.01 M19 13.2 h.01" stroke="#1a1a1a" stroke-width="1.3" stroke-linecap="round"/>' +
      '<rect x="3" y="17" width="22" height="9" rx="1.2" fill="#1a1a1c" stroke="#000" stroke-width=".6"/><rect x="4.4" y="18.2" width="19.2" height="6.6" fill="#8a7d5c" stroke="#ece6d4" stroke-width=".4"/>',
  };
  function deviceIconSvg(dev) {
    if (RENDERS[dev]) return '<img class="thumb-ico render-ico" src="' + RENDER_BASE + dev + (RENDERS[dev].frames ? '-' + frameName(RENDERS[dev].frames >> 1) : '-body') + '.webp" alt="">';
    return '<svg class="thumb-ico" viewBox="0 0 28 28" xmlns="http://www.w3.org/2000/svg">' + DEVICE_ICON[dev] + '</svg>';
  }
  function ensureTileParts(slot) {
    const ph = slot.querySelector('.chain-thumb-placeholder'); if (!ph) return null;
    let model = slot.querySelector('.thumb-model');
    if (!model) { model = mk('span', { class: 'thumb-model' }); slot.querySelector('.chain-thumb').insertAdjacentElement('afterend', model); }
    return { ph: ph, model: model };
  }
  function syncChainIcons() {
    const chain = (typeof currentChain !== 'undefined' && Array.isArray(currentChain)) ? currentChain : [];
    const byDom = {}, devByDom = {};
    chain.forEach(b => {
      const dom = (typeof SLOT_ID_TO_DOM !== 'undefined' && SLOT_ID_TO_DOM[b.slotId]) || ((typeof SLOT_AMP !== 'undefined' && b.slotId === SLOT_AMP) ? 'amp' : null);
      if (dom) byDom[dom] = (typeof MODEL_NAMES !== 'undefined' && MODEL_NAMES[b.modelId]) || '';
      if (dom === 'dist' && DIST_DEVICE[b.modelId]) devByDom.dist = DIST_DEVICE[b.modelId];
      if (dom === 'wah' && WAH_DEVICE[b.modelId]) devByDom.wah = WAH_DEVICE[b.modelId];
      if (dom === 'vol') devByDom.vol = 'fv-vol';
      if (dom === 'fxloop' && RENDERS['fx-loop']) devByDom.fxloop = 'fx-loop';
      if (FX_DEVICE[b.modelId] && RENDERS[FX_DEVICE[b.modelId]]) devByDom[dom] = FX_DEVICE[b.modelId];
      if (dom === 'delay' && RENDERS[DELAY_DEVICE[b.modelId]]) devByDom.delay = DELAY_DEVICE[b.modelId];
      if (dom === 'reverb' && RENDERS[REVERB_DEVICE[b.modelId]]) devByDom.reverb = REVERB_DEVICE[b.modelId];
    });
    const ampKey = (typeof currentAmpKey !== 'undefined') ? currentAmpKey : null;
    if (ampKey && AMP_DEVICE[ampKey]) devByDom.amp = AMP_DEVICE[ampKey];
    document.querySelectorAll('#chainstrip .chain-slot, #chainstrip .chain-slot-stack').forEach(slot => {
      const name = slot.querySelector('.chain-name[data-slot], #chain-amp');
      if (!name) return;
      const dom = name.dataset.slot || 'amp';
      const parts = ensureTileParts(slot); if (!parts) return;
      const modelName = dom === 'amp' ? ((typeof currentAmpName !== 'undefined' && currentAmpName) || '') : (byDom[dom] || '');
      const cat = (dom === 'amp' || dom in byDom) ? catFor(dom, modelName) : (DOM_DEFAULT_CAT[dom] || 'stomp');
      const dev = (DEVICE_ICON[devByDom[dom]] || RENDERS[devByDom[dom]]) ? devByDom[dom] : '';
      const look = dev ? 'dev:' + dev : cat;
      if (parts.ph.dataset.cat !== look) {
        parts.ph.dataset.cat = look;
        const old = parts.ph.querySelector('.thumb-ico'); if (old) old.remove();
        parts.ph.insertAdjacentHTML('beforeend', dev ? deviceIconSvg(dev) : iconSvg(cat));
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
    // the round-knob path resizes the backing store itself, so check its size too
    if (canvas.dataset.prep !== key || canvas.width !== Math.round(w * dpr)) {
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
    // a printed dot at the minimum
    if (o.minDot) {
      const p = polar(a0, R * 0.9);
      ctx.beginPath(); ctx.arc(p[0], p[1], Math.max(1.6, R * 0.05), 0, Math.PI * 2); ctx.fillStyle = '#f6f2ea'; ctx.fill();
    }
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

  // ── Device knobs: the knob each look-alike carries. Same value contract and
  // 270° sweep as the other knobs, and the same loaded-value marker (a
  // double-click restores it). Sliders mode still draws the glass fader. ──
  const SPUN_GOLD = { stops: [['#fff3c4', 0], ['#a87e22', 0.13], ['#f0cf78', 0.25], ['#7d5a12', 0.38], ['#fff3c4', 0.5], ['#a87e22', 0.63], ['#e8c46a', 0.75], ['#6e4f0e', 0.88], ['#fff3c4', 1]],
    glow: ['rgba(255,240,190,0.35)', 'rgba(60,40,0,0.25)'] };
  function deviceKnob(canvas, value127, wrap, o) {
    const sz = wrapSize(wrap, 56, 56), w = Math.min(sz.w, sz.h), ctx = prep(canvas, w, w), c = w / 2, R = w / 2;
    const a0 = Math.PI * 0.75, sweep = Math.PI * 1.5;
    const angle = v => a0 + sweep * (clamp127(v) / 127);
    const polar = (a, r) => [c + Math.cos(a) * r, c + Math.sin(a) * r];
    const disc = (r, fill) => { ctx.beginPath(); ctx.arc(c, c, r, 0, Math.PI * 2); ctx.fillStyle = fill; ctx.fill(); };
    let g;
    // scale printed on the panel around the knob (0–10), as numbers or dots
    if (o.numbers) {
      ctx.fillStyle = o.ink; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.font = '700 ' + Math.max(5, R * 0.2).toFixed(1) + 'px ' + getComputedStyle(document.body).fontFamily;
      for (let i = 0; i <= 10; i += 2) { const p = polar(a0 + sweep * i / 10, R * 0.86); ctx.fillText(String(i), p[0], p[1]); }
    } else if (o.arc) {
      // an open arc round the knob with ticks pointing in, the end ticks out
      ctx.strokeStyle = o.ink; ctx.lineWidth = Math.max(1.4, R * 0.045); ctx.lineCap = 'butt';
      ctx.beginPath(); ctx.arc(c, c, R * 0.9, a0, a0 + sweep); ctx.stroke();
      for (let i = 0; i <= 6; i++) {
        const a = a0 + sweep * i / 6, end = i === 0 || i === 6;
        const p = polar(a, end ? R * 0.9 : R * 0.72), q = polar(a, end ? R - 0.5 : R * 0.9);
        ctx.beginPath(); ctx.moveTo(p[0], p[1]); ctx.lineTo(q[0], q[1]); ctx.stroke();
      }
    } else if (o.scale) {
      for (let i = 0; i <= 10; i++) {
        const p = polar(a0 + sweep * i / 10, R - 2.5);
        ctx.beginPath(); ctx.arc(p[0], p[1], o.dots || (i % 5 === 0 ? 1.6 : 1), 0, Math.PI * 2); ctx.fillStyle = o.ink; ctx.fill();
      }
    }
    // a printed dot at the minimum
    if (o.minDot) {
      const p = polar(a0, R * 0.9);
      ctx.beginPath(); ctx.arc(p[0], p[1], Math.max(1.6, R * 0.05), 0, Math.PI * 2); ctx.fillStyle = '#f6f2ea'; ctx.fill();
    }
    if (wrap && wrap.dataset.orig !== undefined && wrap.dataset.orig !== '') {
      const a = angle(parseInt(wrap.dataset.orig, 10));
      ctx.save(); ctx.translate(c, c); ctx.rotate(a + Math.PI / 2);
      ctx.beginPath(); ctx.moveTo(0, -(R * o.skirt + 1.5)); ctx.lineTo(-2.6, -(R - 0.5)); ctx.lineTo(2.6, -(R - 0.5)); ctx.closePath();
      ctx.fillStyle = o.mark; ctx.fill(); ctx.restore();
    }
    const rs = R * o.skirt, rb = R * o.body, rc = R * o.cap;
    // cast shadow on the panel, falling to the lower right
    ctx.save(); ctx.shadowColor = 'rgba(0,0,0,' + (o.shadow || 0.75) + ')'; ctx.shadowBlur = R * 0.22; ctx.shadowOffsetX = R * 0.06; ctx.shadowOffsetY = R * 0.12;
    disc(rs, '#000'); ctx.restore();
    // skirt: a flat flange, lit along its upper edge; toothed (square
    // notches round the rim) or plain
    g = ctx.createLinearGradient(c - rs, c - rs, c + rs, c + rs);
    g.addColorStop(0, o.skirtHi); g.addColorStop(0.5, o.skirtMid); g.addColorStop(1, '#020202');
    if (o.teeth) {
      const step = Math.PI * 2 / o.teeth, rn = rs - R * 0.1;
      ctx.beginPath();
      for (let i = 0; i < o.teeth; i++) {
        const a = i * step;
        ctx.arc(c, c, rs, a, a + step * 0.6); ctx.arc(c, c, rn, a + step * 0.6, a + step);
      }
      ctx.closePath(); ctx.fillStyle = g; ctx.fill();
    } else disc(rs, g);
    // grip: knurled side wall, light and dark ridges shaded by where the light falls
    g = ctx.createLinearGradient(c - rb, c - rb, c + rb, c + rb);
    g.addColorStop(0, o.gripHi || '#4a4a4c'); g.addColorStop(0.45, o.gripMid || '#161617'); g.addColorStop(1, o.gripLo || '#030303');
    disc(rb, g);
    if (o.ribs) {
      for (let i = 0; i < o.ribs; i++) {
        const a = i * Math.PI * 2 / o.ribs, lit = Math.max(0, Math.cos(a + Math.PI * 0.75));
        const p = polar(a, rb - 0.3), q = polar(a, rc + 0.6);
        ctx.beginPath(); ctx.moveTo(p[0], p[1]); ctx.lineTo(q[0], q[1]);
        ctx.strokeStyle = 'rgba(255,255,255,' + (0.05 + 0.32 * lit).toFixed(3) + ')'; ctx.lineWidth = Math.max(0.7, R * 0.025); ctx.stroke();
      }
    }
    // pointer wedge on the skirt, sticking out past the grip
    if (o.wedge) {
      ctx.save(); ctx.translate(c, c); ctx.rotate(angle(value127) + Math.PI / 2);
      ctx.beginPath(); ctx.moveTo(-R * 0.15, -rc); ctx.lineTo(0, -(R - 0.8)); ctx.lineTo(R * 0.15, -rc); ctx.closePath();
      const wc = o.wedge === 'black' ? ['#4a4a4c', '#1a1a1b', '#050505'] : ['#f6f8fa', '#b8bec6', '#5d636b'];
      g = ctx.createLinearGradient(-R * 0.15, 0, R * 0.15, 0); g.addColorStop(0, wc[0]); g.addColorStop(0.5, wc[1]); g.addColorStop(1, wc[2]);
      ctx.fillStyle = g; ctx.fill(); ctx.strokeStyle = 'rgba(0,0,0,.45)'; ctx.lineWidth = 0.6; ctx.stroke(); ctx.restore();
    }
    // bevel where the grip meets the top
    ctx.beginPath(); ctx.arc(c, c, rc + 0.8, Math.PI * 0.9, Math.PI * 1.85); ctx.strokeStyle = 'rgba(255,255,255,0.35)'; ctx.lineWidth = 1; ctx.stroke();
    ctx.beginPath(); ctx.arc(c, c, rc + 0.8, Math.PI * 1.85, Math.PI * 2.9); ctx.strokeStyle = 'rgba(0,0,0,0.6)'; ctx.lineWidth = 1; ctx.stroke();
    // top: spun metal (anisotropic, so a conic sweep of light) or dark plastic
    const spun = o.gold ? SPUN_GOLD : o.spun;
    if (spun && ctx.createConicGradient) {
      g = ctx.createConicGradient(-Math.PI / 4, c, c);
      spun.stops.forEach(st => g.addColorStop(st[1], st[0]));
      disc(rc, g);
      g = ctx.createRadialGradient(c, c, rc * 0.1, c, c, rc);
      g.addColorStop(0, spun.glow[0]); g.addColorStop(1, spun.glow[1]);
      disc(rc, g);
    } else {
      g = ctx.createRadialGradient(c - rc * 0.35, c - rc * 0.45, rc * 0.05, c, c, rc);
      g.addColorStop(0, o.topHi); g.addColorStop(0.7, o.topMid); g.addColorStop(1, '#070707');
      disc(rc, g);
      // soft window reflection (none on matte plastic)
      if (!o.matte) {
        ctx.save(); ctx.beginPath(); ctx.ellipse(c - rc * 0.32, c - rc * 0.42, rc * 0.45, rc * 0.2, -0.6, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(255,255,255,0.10)'; ctx.fill(); ctx.restore();
      }
    }
    // pointer line
    if (o.pointer) {
      ctx.save(); ctx.translate(c, c); ctx.rotate(angle(value127) + Math.PI / 2);
      ctx.beginPath(); ctx.moveTo(0, -rc * o.from); ctx.lineTo(0, -(o.toEdge ? rb - 0.5 : rc - 1.2));
      ctx.strokeStyle = o.pointer; ctx.lineWidth = Math.max(1.8, R * 0.07); ctx.lineCap = 'butt'; ctx.stroke(); ctx.restore();
    }
  }
  // ── Wah and volume pedal, seen from the side: the Position / Volume
  // control drawn as the treadle, tipping toe-up at 0 and toe-down at 127
  // round a pivot near the heel. Same value contract and drag as a knob;
  // the canvas is just wide. ──
  const hammerTiles = {};
  function hammerTone(ctx, dark) {
    // a random speckle tile for hammertone / crinkle paint, made once per shade
    if (!hammerTiles[dark]) {
      const t = document.createElement('canvas'); t.width = t.height = 48;
      const x = t.getContext('2d');
      for (let i = 0; i < 520; i++) {
        x.fillStyle = Math.random() < 0.5 ? 'rgba(255,255,255,' + (0.02 + Math.random() * 0.04).toFixed(3) + ')' : 'rgba(0,0,0,' + (0.1 + Math.random() * 0.18).toFixed(3) + ')';
        x.beginPath(); x.arc(Math.random() * 48, Math.random() * 48, 0.3 + Math.random() * 0.8, 0, Math.PI * 2); x.fill();
      }
      hammerTiles[dark] = t;
    }
    return ctx.createPattern(hammerTiles[dark], 'repeat');
  }
  // Seen from the front left and a little above, like a product photo: the
  // toe end with its name plate, the long side with the jack, and the top
  // of the treadle. The base is a tapered block, the treadle a block that
  // tips round the pivot; a fixed oblique projection, faces lit by hand.
  // Units: the pedal is 1 long (x, toe at 0), D deep (z, near side at 0).
  const TREADLE = {
    chrome: { top: ['#f6f8fa', '#c4c9cf', '#ffffff', '#9aa0a8'], side: ['#ffffff', '#e2e5e9', '#c4c9cf', '#9aa0a8', '#5d636b'], end: ['#d4d8dd', '#8d939b'] },
    black: { top: ['#343437', '#1c1c1e', '#2a2a2c', '#151516'], side: ['#4a4a4e', '#1e1e20', '#222224', '#111112', '#060606'], end: ['#2a2a2c', '#0e0e0f'] },
  };
  function wahSide(canvas, value127, wrap, o) {
    const sz = wrapSize(wrap, 460, 240), W = sz.w, H = sz.h, ctx = prep(canvas, W, H);
    const D = o.depth || 0.4, hb = o.hb || 0.17, ft = 0.025, tt = o.tt || 0.06, xp = 0.86, tMax = o.tMax || 0.24;
    const tilt = (1 - clamp127(value127) / 127) * tMax - 0.02;
    const ya = -0.42, pb = 0.3, ca = Math.cos(ya), sa = Math.sin(ya), cb = Math.cos(pb), sb = Math.sin(pb);
    const cam = p => { const X = p[0] * ca + p[2] * sa, Z = -p[0] * sa + p[2] * ca; return [X, p[1] * cb + Z * sb]; };
    const yp = ft + hb + 0.012;
    const tr = (x, y, z, t) => { t = t === undefined ? tilt : t; const dx = x - xp; return [xp + dx * Math.cos(t) + y * Math.sin(t), yp - dx * Math.sin(t) + y * Math.cos(t), z]; };
    const bot = (x, z) => [x, ft, z];
    const top = (fx, fz) => [0.045 + fx * 0.93, ft + hb, D * (0.02 + fz * 0.96)];
    // fit the drawing to the canvas over the whole travel, so it never jumps
    let mnx = 1e9, mxx = -1e9, mny = 1e9, mxy = -1e9;
    const fit = p => { const c = cam(p); mnx = Math.min(mnx, c[0]); mxx = Math.max(mxx, c[0]); mny = Math.min(mny, c[1]); mxy = Math.max(mxy, c[1]); };
    [0, 1].forEach(x => [0, D].forEach(z => { fit([x, 0, z]); [-0.02, tMax - 0.02].forEach(t => [0, tt + 0.02].forEach(y => fit(tr(x, y, z, t)))); }));
    const S = Math.min((W - 20) / (mxx - mnx), (H - 18) / (mxy - mny));
    const ox = (W - (mxx - mnx) * S) / 2 - mnx * S, oy = (H - (mxy - mny) * S) / 2 + mxy * S;
    const P = p => { const c = cam(p); return [ox + c[0] * S, oy - c[1] * S]; };
    const poly = (pts, fill, rim) => {
      ctx.beginPath(); pts.forEach((p, i) => { const q = P(p); if (i) ctx.lineTo(q[0], q[1]); else ctx.moveTo(q[0], q[1]); }); ctx.closePath();
      ctx.fillStyle = fill; ctx.fill();
      if (rim) { ctx.strokeStyle = 'rgba(255,255,255,' + rim + ')'; ctx.lineWidth = 1; ctx.stroke(); }
    };
    const grad = (p0, p1, stops) => { const a = P(p0), b = P(p1), g = ctx.createLinearGradient(a[0], a[1], b[0], b[1]); stops.forEach((c, i) => g.addColorStop(i / (stops.length - 1), c)); return g; };
    // draw in a local lw x lh box laid on a face: o3 its top left, u3 top right, v3 bottom left
    const onFace = (o3, u3, v3, lw, lh, fn) => { const O = P(o3), U = P(u3), V = P(v3); ctx.save(); ctx.transform((U[0] - O[0]) / lw, (U[1] - O[1]) / lw, (V[0] - O[0]) / lh, (V[1] - O[1]) / lh, O[0], O[1]); fn(); ctx.restore(); };
    const toePt = (zf, yf) => [0.045 * yf, ft + hb * yf, D * (zf * (1 - 0.04 * yf) + 0.02 * yf)];
    const nearPt = (x, yf) => [x, ft + hb * yf, D * 0.02 * yf];
    // shadow on the floor
    const c0 = P([0.5, 0, D / 2]);
    ctx.save(); ctx.filter = 'blur(7px)'; ctx.fillStyle = 'rgba(0,0,0,.55)'; ctx.beginPath(); ctx.ellipse(c0[0], c0[1] + 4, (mxx - mnx) * S * 0.46, (mxy - mny) * S * 0.16, 0, 0, Math.PI * 2); ctx.fill(); ctx.restore();
    // rubber feet (the near ones show)
    [[0.07, 0], [0.88, 0], [0.07, D - 0.06]].forEach(f => poly([[f[0], 0, f[1]], [f[0] + 0.05, 0, f[1]], [f[0] + 0.05, ft, f[1]], [f[0], ft, f[1]]], '#0a0a0b'));
    // base: top (mostly hidden), toe end, near side
    const bTop = [top(0, 0), top(1, 0), top(1, 1), top(0, 1)];
    poly(bTop, '#0c0c0d');
    const toeFace = [bot(0, 0), bot(0, D), top(0, 1), top(0, 0)], nearFace = [bot(0, 0), bot(1, 0), top(1, 0), top(0, 0)];
    poly(toeFace, grad(top(0, 0.5), bot(0, D / 2), [shade(o.base[0], 0.8), shade(o.base[1], 0.8)]), o.rim);
    if (o.hammer) poly(toeFace, hammerTone(ctx, o.base[1]));
    poly(nearFace, grad(top(0.5, 0), bot(0.5, 0), o.base), o.rim);
    if (o.hammer) poly(nearFace, hammerTone(ctx, o.base[1]));
    // a soft sheen along the top of the base's side, a lit top edge
    poly([top(0, 0), top(1, 0), nearPt(0.98, 0.7), nearPt(0.03, 0.7)], 'rgba(255,255,255,.05)');
    { const a = P(top(0, 0)), b = P(top(1, 0)); ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.strokeStyle = 'rgba(255,255,255,.22)'; ctx.lineWidth = 1; ctx.stroke(); }
    // the dark gap under the treadle, the toe-switch post in it
    poly([top(0.005, 0), tr(0, 0, 0), tr(xp, 0, 0), [xp, ft + hb, 0]], '#070708');
    poly([top(0, 0), top(0, 1), tr(0, 0, D), tr(0, 0, 0)], '#0b0b0c');
    if (o.post !== false) {
      const pb3 = [0.17, ft + hb, D * 0.3], pt3 = tr(0.17, 0, D * 0.3), B = P(pb3), T = P(pt3), r = 0.02 * S;
      const g = ctx.createLinearGradient(B[0] - r, 0, B[0] + r, 0); g.addColorStop(0, '#5d636b'); g.addColorStop(0.4, '#f4f6f8'); g.addColorStop(1, '#4e5359');
      ctx.fillStyle = g; ctx.fillRect(B[0] - r, T[1], r * 2, B[1] - T[1]);
      ctx.fillStyle = 'rgba(0,0,0,.35)'; for (let y = T[1] + 3; y < B[1] - 2; y += 3) ctx.fillRect(B[0] - r, y, r * 2, 1);
    }
    // name plate on the toe end, jack and power socket on the near side
    if (o.plate) onFace(toePt(0.86, 0.82), toePt(0.14, 0.82), toePt(0.86, 0.18), 100, 44, () => {
      if (typeof rr === 'function') rr(ctx, 0, 0, 100, 44, 4);
      ctx.fillStyle = '#141416'; ctx.fill(); ctx.strokeStyle = 'rgba(255,255,255,.16)'; ctx.lineWidth = 1.2; ctx.stroke();
      ctx.fillStyle = o.plateInk || '#d8dadd'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.font = (o.plateFont || '700 {s}px Georgia, "DejaVu Serif", serif').replace('{s}', '26'); ctx.fillText(o.plate, 50, 24);
    });
    const jx = o.jackX || 0.58;
    onFace(nearPt(jx, 0.78), nearPt(jx + 0.09, 0.78), nearPt(jx, 0.22), 40, 40, () => {
      ctx.beginPath(); for (let i = 0; i < 6; i++) { const a = i * Math.PI / 3; ctx.lineTo(16 + Math.cos(a) * 12, 20 + Math.sin(a) * 12); } ctx.closePath();
      const g = ctx.createLinearGradient(4, 8, 28, 32); g.addColorStop(0, '#f4f6f8'); g.addColorStop(1, '#5d636b'); ctx.fillStyle = g; ctx.fill();
      ctx.beginPath(); ctx.arc(16, 20, 5.5, 0, Math.PI * 2); ctx.fillStyle = '#050505'; ctx.fill();
      ctx.fillStyle = '#0a0a0b'; ctx.fillRect(31, 12, 8, 16);
    });
    // treadle: near side, toe end, top
    const T = TREADLE[o.treadle] || TREADLE.black, x0 = 0, x1 = 0.985;
    poly([tr(x0, 0, D), tr(x0, 0, 0), tr(x0, tt, 0), tr(x0, tt, D)], grad(tr(x0, tt, D / 2), tr(x0, 0, D / 2), T.end), o.rim);
    poly([tr(x0, 0, 0), tr(x1, 0, 0), tr(x1, tt, 0), tr(x0, tt, 0)], grad(tr(0.5, tt, 0), tr(0.5, 0, 0), T.side), o.rim);
    poly([tr(x0, tt, 0), tr(x1, tt, 0), tr(x1, tt, D), tr(x0, tt, D)], grad(tr(0.5, tt, 0), tr(0.5, tt, D), T.top), o.rim);
    // specular edges: the treadle's near top edge and toe top edge catch the light
    const edge = (a3, b3, alpha, w) => { const a = P(a3), b = P(b3); ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.strokeStyle = 'rgba(255,255,255,' + alpha + ')'; ctx.lineWidth = w; ctx.stroke(); };
    edge(tr(x0, tt, 0), tr(x1, tt, 0), o.treadle === 'chrome' ? 0.95 : 0.35, 1.3);
    edge(tr(x0, tt, 0), tr(x0, tt, D), o.treadle === 'chrome' ? 0.7 : 0.25, 1);
    edge(tr(x0, 0, 0), tr(x1, 0, 0), 0.0, 0);
    if (o.toeCap) {
      const h = tt + 0.008;
      poly([tr(0.01, tt, 0.02 * D), tr(0.27, tt, 0.02 * D), tr(0.27, h, 0.02 * D), tr(0.01, h, 0.02 * D)], shade(o.toeCap, 0.75));
      poly([tr(0.01, h, 0.02 * D), tr(0.27, h, 0.02 * D), tr(0.27, h, 0.98 * D), tr(0.01, h, 0.98 * D)], grad(tr(0.14, h, 0), tr(0.14, h, D), [o.toeCap, shade(o.toeCap, 0.85)]));
    }
    if (o.ribs) {
      // ribbed rubber: raised bars across the treadle
      const h = tt + 0.012;
      for (let x = 0.31; x < 0.95; x += 0.055) {
        poly([tr(x, tt, 0.05 * D), tr(x + 0.028, tt, 0.05 * D), tr(x + 0.028, h, 0.05 * D), tr(x, h, 0.05 * D)], '#101011');
        poly([tr(x, h, 0.05 * D), tr(x + 0.028, h, 0.05 * D), tr(x + 0.028, h, 0.95 * D), tr(x, h, 0.95 * D)], '#2e2e31');
      }
    }
  }
  const DEVICE_KNOBS = {
    // volume pedal: the Volume control is the treadle (black plastic, ribbed
    // rubber, pale toe cap, low wedge base); the minimum-volume knob is the
    // small pale-blue knob on the side of the real thing
    fv: (cv, v, w) => (w && w.id === 'vol-w-02')
      ? wahSide(cv, v, w, { post: false, ribs: true, rim: 0.16, toeCap: '#c8d8e2', depth: 0.5, hb: 0.1, tt: 0.07, jackX: 0.12, base: ['#2a2a2c', '#0f0f10'], treadle: 'black' })
      : deviceKnob(cv, v, w, { scale: true, ink: '#9aa0a8', mark: '#9aa0a8', skirt: 0.7, body: 0.66, cap: 0.5, ribs: 22, matte: true,
          skirtHi: '#c4dbe6', skirtMid: '#6e93a6', gripHi: '#d6e8f0', gripMid: '#8fb2c4', gripLo: '#4a6a7a', topHi: '#e2eef4', topMid: '#a6c4d2', pointer: '#2a3a44', from: 0.2, shadow: 0.5 }),
    // chrome treadle on a black hammertone base
    v847: (cv, v, w) => wahSide(cv, v, w, { plate: 'Shine', hammer: true, base: ['#3a3a3d', '#1c1c1e'], treadle: 'chrome' }),
    // satin black all over, the name in white lower-case on the toe plate
    crybaby: (cv, v, w) => wahSide(cv, v, w, { plate: 'black', plateInk: '#f4f4f4', plateFont: '800 {s}px ' + getComputedStyle(document.body).fontFamily, base: ['#262628', '#0e0e0f'], rim: 0.16, treadle: 'black' }),
    // small gold-topped knob with a wide black fluted side, in a printed 0–10 scale
    plexi: (cv, v, w) => deviceKnob(cv, v, w, { numbers: true, ink: '#3a2c10', mark: '#3a2c10', skirt: 0.6, body: 0.54, cap: 0.36, ribs: 24, gold: true,
      skirtHi: '#3a3a3a', skirtMid: '#111', pointer: '#2a1d06', from: 0.1, shadow: 0.45 }),
    // large flat-topped black knob on a notched skirt, short white line at the
    // rim, in a ring of printed dots
    ts: (cv, v, w) => deviceKnob(cv, v, w, { scale: true, dots: 1.7, ink: '#f3f7ee', mark: '#f3f7ee', skirt: 0.86, body: 0.74, cap: 0.71, ribs: 0, teeth: 16, matte: true,
      skirtHi: '#3c3c3c', skirtMid: '#141414', gripHi: '#2e2e30', gripMid: '#121213', topHi: '#232325', topMid: '#18181a', pointer: '#f4f4f4', from: 0.72, shadow: 0.55 }),
    // tall knurled black knob with a matte top and a white line down its
    // side, inside a printed arc with ticks
    rat: (cv, v, w) => deviceKnob(cv, v, w, { arc: true, ink: '#d9dbde', mark: '#d9dbde', skirt: 0.62, body: 0.58, cap: 0.46, ribs: 40, matte: true,
      skirtHi: '#2a2a2c', skirtMid: '#0c0c0d', gripHi: '#3a3a3c', gripMid: '#141415', topHi: '#262628', topMid: '#161618', pointer: '#f4f4f4', from: 0.55, toEdge: true, shadow: 0.7 }),
    // big flat-topped black knob over a chrome nut, short white line
    muff: (cv, v, w) => deviceKnob(cv, v, w, { ink: '#111', mark: '#111', skirt: 0.88, body: 0.82, cap: 0.8, ribs: 0, matte: true,
      skirtHi: '#f4f6f8', skirtMid: '#9aa0a8', gripHi: '#3a3a3c', gripMid: '#1a1a1b', topHi: '#2e2e30', topMid: '#1c1c1e', pointer: '#f4f4f4', from: 0.62, shadow: 0.5 }),
    // round black knob with a pointed nub for a pointer
    dc: (cv, v, w) => deviceKnob(cv, v, w, { ink: '#2a1206', mark: '#2a1206', skirt: 0.74, body: 0.72, cap: 0.64, ribs: 0, wedge: 'black', minDot: !!(w && w.id === 'dist-w-02'),
      skirtHi: '#3c3c3c', skirtMid: '#141414', gripHi: '#3a3a3c', gripMid: '#141415', topHi: '#3a3a3c', topMid: '#121214', shadow: 0.6 }),
    // glossy black dome on a knurled chrome skirt with a pointer wedge
    rc: (cv, v, w) => deviceKnob(cv, v, w, { ink: '#222', mark: '#222', skirt: 0.8, body: 0.76, cap: 0.66, ribs: 44, wedge: true,
      skirtHi: '#f4f6f8', skirtMid: '#9aa0a8', gripHi: '#eef0f3', gripMid: '#9aa0a8', gripLo: '#3a3e44', topHi: '#55555a', topMid: '#0c0c0e', shadow: 0.45 }),
  };

  // ── Rendered looks (editor/tools/render-devices, Blender): the enclosure
  // is a picture, each knob a lit picture with its pointer turned on top. ──
  const RENDERS = window.DEVICE_RENDERS || {};
  const RENDER_BASE = '../assets/devices/';
  const RENDER_LED = { 'green-jrc': '#ff3b2a', 'black-op': '#ff3b2a', 'white-boost': '#ff3b2a', 'dc-dist': '#ff3b2a', 'tri-fuzz': '#ff3b2a', 'orange-phaser': '#ff3b2a', 'flanger': '#c070ff', 'multi-chorus': '#3d8bff', 'roto': '#ffb43a', 'dyn3': '#a565ff', 'param-eq': '#a565ff', 'fx-loop': '#a565ff', 'eleven-sr': '#a565ff', 'dyn-delay': '#a565ff' };
  const renderImgs = {};
  function renderImg(dev, part) {
    const key = dev + '-' + part;
    if (!renderImgs[key]) {
      const im = new Image();
      im.onload = function () {
        // controls drawn before their picture arrived: draw them again
        document.querySelectorAll('[data-knob] .knob-wrap canvas.knob-canvas').forEach(function (c) {
          const w = c.closest('.knob-wrap');
          if (!w) return;
          if (w.dataset.slider && c.dataset.look === 'render:' + dev) drawRenderedKnob(c, clamp127(w.dataset.value), w, dev);
          else if (c.dataset.look === 'render:' + dev || treadleDev(c.dataset.look, w) === dev) drawKnob(c, clamp127(w.dataset.value));
        });
      };
      im.src = RENDER_BASE + key + '.webp';
      renderImgs[key] = im;
    }
    return renderImgs[key];
  }
  function drawRenderedKnob(canvas, value127, wrap, dev) {
    canvas.dataset.look = 'render:' + dev;
    if (wrap.dataset.slider) {
      // a slider: its carriage sprite slid from the track's minimum end to its maximum end
      const sl = (RENDERS[dev].sliders || {})[wrap.dataset.slider], sz = wrapSize(wrap, 100, 40), ctx = prep(canvas, sz.w, sz.h);
      const im = sl && renderImg(dev, sl[5]);
      if (im && im.complete && im.naturalWidth) {
        const s = sl[4], t = clamp127(value127) / 127;
        const x = sl[0] + t * (sl[2] - sl[0]) - Math.min(sl[0], sl[2]), y = sl[1] + t * (sl[3] - sl[1]) - Math.min(sl[1], sl[3]);
        ctx.save(); ctx.shadowColor = 'rgba(0,0,0,.5)'; ctx.shadowBlur = s * 0.07; ctx.shadowOffsetY = s * 0.05;
        ctx.drawImage(im, x, y, s, s); ctx.restore();
      }
      return;
    }
    const sz = wrapSize(wrap, 56, 56), s = Math.min(sz.w, sz.h), ctx = prep(canvas, s, s);
    const m = RENDERS[dev] || {};
    if (wrap.dataset.bar) {
      // a value with no knob in the picture: a level bar
      const bsz = wrapSize(wrap, 200, 14), bc = prep(canvas, bsz.w, bsz.h), v = clamp127(value127) / 127;
      bc.fillStyle = 'rgba(0,0,0,.55)'; rr(bc, 0, 0, bsz.w, bsz.h, bsz.h / 2); bc.fill();
      const g = bc.createLinearGradient(0, 0, 0, bsz.h); g.addColorStop(0, '#8fb2f4'); g.addColorStop(1, '#3f6fd6');
      if (v > 0) { bc.fillStyle = g; rr(bc, 1, 1, Math.max(bsz.h - 2, (bsz.w - 2) * v), bsz.h - 2, (bsz.h - 2) / 2); bc.fill(); }
      return;
    }
    if (m.spin !== undefined) {
      // a knob cut out of an illustration: the whole picture turns, from the
      // angle it was drawn at (m.spin) to the value's
      const im = renderImg(dev, 'knob-' + wrap.id.replace(/^.*-w-?/, ''));
      if (im.complete && im.naturalWidth) {
        ctx.save(); ctx.translate(s / 2, s / 2); ctx.rotate((-135 + 270 * clamp127(value127) / 127 - m.spin) * Math.PI / 180);
        ctx.drawImage(im, -s / 2, -s / 2, s, s); ctx.restore();
      }
      return;
    }
    const knob = renderImg(dev, 'knob'), ptr = renderImg(dev, 'pointer');
    if (knob.complete && knob.naturalWidth) {
      // its shadow on the panel, drawn here: WebKitGTK drops a CSS filter on a canvas
      ctx.save(); ctx.shadowColor = 'rgba(0,0,0,.5)'; ctx.shadowBlur = s * 0.07; ctx.shadowOffsetX = s * 0.015; ctx.shadowOffsetY = s * 0.05;
      ctx.drawImage(knob, 0, 0, s, s); ctx.restore();
    }
    if (ptr.complete && ptr.naturalWidth) {
      ctx.save(); ctx.translate(s / 2, s / 2); ctx.rotate((-135 + 270 * clamp127(value127) / 127) * Math.PI / 180);
      ctx.drawImage(ptr, -s / 2, -s / 2, s, s); ctx.restore();
    }
  }
  // Treadle pedals rendered at a run of treadle positions: the control whose
  // value is the treadle shows the frame for its value, cross-faded with the
  // next so a drag moves smoothly.
  const TREADLE_LOOK = { v847: 'shine-wah', crybaby: 'black-wah', fv: 'fv-vol' };
  function treadleDev(look, wrap) {
    const dev = TREADLE_LOOK[look];
    if (!dev || !RENDERS[dev] || !RENDERS[dev].frames) return '';
    return (look !== 'fv' || (wrap && wrap.id === 'vol-w-02')) ? dev : '';
  }
  const frameName = i => 'f' + String(i).padStart(2, '0');
  function drawTreadleFrames(canvas, value127, wrap, dev) {
    const m = RENDERS[dev], sz = wrapSize(wrap, m.width, m.height);
    const w = Math.min(sz.w, sz.h * m.width / m.height), h = w * m.height / m.width, ctx = prep(canvas, w, h);
    const pos = clamp127(value127) / 127 * (m.frames - 1), i = Math.floor(pos), t = pos - i;
    const a = renderImg(dev, frameName(i)), b = renderImg(dev, frameName(Math.min(m.frames - 1, i + 1)));
    for (let k = 0; k < m.frames; k++) renderImg(dev, frameName(k));   // load the rest for the next drag
    if (a.complete && a.naturalWidth) ctx.drawImage(a, 0, 0, w, h);
    if (t > 0.01 && b.complete && b.naturalWidth) { ctx.globalAlpha = t; ctx.drawImage(b, 0, 0, w, h); ctx.globalAlpha = 1; }
  }
  // Lay a panel's controls on its rendered enclosure: knobs, LED and the
  // stomp switch's click area go to the centres export.py measured.
  function clearRenderCtrls(el) {
    el.querySelectorAll('.render-ctrl').forEach(n => {
      n.classList.remove('render-ctrl'); n.style.left = n.style.top = '';
      [n, ...n.querySelectorAll(':scope > select')].forEach(c => { if (c.tagName === 'SELECT' || c.tagName === 'BUTTON') { c.style.removeProperty('width'); c.style.removeProperty('height'); } });
    });
  }
  function layoutRendered(el, dev) {
    const m = RENDERS[dev];
    // a pedal carries the picture itself; an amp lays it in its head's top panel
    const host = el.id === 'amp-obj' ? (el.querySelector('.top-panel') || el) : el;
    let body = host.querySelector(':scope > img.render-body');
    if (!m) {
      if (body) body.remove();
      if (host !== el) host.style.height = '';
      el.querySelectorAll('.render-led, img.render-tog, img.render-dial').forEach(n => n.remove());
      clearRenderCtrls(el);
      if (el.classList.contains('pedal')) el.style.width = el.style.height = '';
      el.querySelectorAll('.ctrl-knob, .pedal-led-wrap, .foot').forEach(n => { n.style.left = n.style.top = n.style.width = n.style.height = ''; });
      el.querySelectorAll('.knob-wrap').forEach(n => { n.style.width = n.style.height = ''; delete n.dataset.slider; delete n.dataset.bar; });
      el.querySelectorAll('.render-bar').forEach(n => n.classList.remove('render-bar'));
      return;
    }
    if (!body) { body = mk('img', { class: 'render-body', alt: '' }); host.insertAdjacentElement('afterbegin', body); }
    const src = RENDER_BASE + dev + '-body.webp';
    if (body.getAttribute('src') !== src) body.setAttribute('src', src);
    // a perspective picture is larger than the front it shows: lay it where export.py says
    // (cleared otherwise: the previous model's placement must not stay on the img)
    const pl = m.img ? { left: m.img.left + 'px', top: m.img.top + 'px', width: m.img.width + 'px', height: m.img.height + 'px' } : { left: '', top: '', width: '', height: '' };
    Object.assign(body.style, pl);
    if (host !== el) host.style.height = m.height ? m.height + 'px' : '';
    if (el.classList.contains('pedal')) { el.style.width = m.width + 'px'; el.style.height = m.height + 'px'; }
    el.style.setProperty('--led', RENDER_LED[dev] || '#ff3b2a');
    el.querySelectorAll('.ctrl-knob').forEach(k => {
      // knob-wrap ids end in the key export.py used: dist-w-02 -> 02, tone-w0 -> 0
      const w = k.querySelector('.knob-wrap'), key = w && w.id.replace(/^.*-w-?/, ''), sl = w && (m.sliders || {})[key];
      const bar = w && (m.bars || {})[key];
      if (bar) {
        w.dataset.bar = key; k.classList.add('render-bar');
        k.style.left = bar[0] + 'px'; k.style.top = bar[1] + 'px';
        if (w.style.width !== bar[2] + 'px') { w.style.width = bar[2] + 'px'; w.style.height = bar[3] + 'px'; const c = w.querySelector('canvas.knob-canvas'); if (c) drawRenderedKnob(c, clamp127(w.dataset.value), w, dev); }
        return;
      }
      if (sl) {
        // spans the track; the carriage moves along it
        const width = Math.round(Math.abs(sl[2] - sl[0]) + sl[4]), height = Math.round(Math.abs(sl[3] - sl[1]) + sl[4]);
        w.dataset.slider = key;
        k.style.left = ((sl[0] + sl[2]) / 2) + 'px'; k.style.top = ((sl[1] + sl[3]) / 2) + 'px';
        if (w.style.width !== width + 'px' || w.style.height !== height + 'px') {
          w.style.width = width + 'px'; w.style.height = height + 'px';
          const c = w.querySelector('canvas.knob-canvas'); if (c) drawRenderedKnob(c, clamp127(w.dataset.value), w, dev);
        }
        return;
      }
      const p = w && m.knobs[key];
      if (!p) return;
      const size = Math.round(m.knob * p[2]);
      k.style.left = p[0] + 'px'; k.style.top = p[1] + 'px';
      if (w.style.width !== size + 'px') { w.style.width = w.style.height = size + 'px'; const c = w.querySelector('canvas.knob-canvas'); if (c) drawKnob(c, clamp127(w.dataset.value)); }
    });
    const led = el.querySelector('.pedal-led-wrap');
    if (led) { led.style.left = m.led[0] + 'px'; led.style.top = m.led[1] + 'px'; }
    // other controls (a toggle as a click area over a rendered switch, a sync
    // picker as a small select), keyed by the end of their id: fxhost-tgl-05 -> tgl-05
    // (or by its whole id: an amp's own toggle or picker, outside any knob cell, is placed itself;
    // the previous model's are let go first)
    clearRenderCtrls(el);
    Object.keys(m.controls || {}).forEach(key => {
      const c = el.querySelector('#' + key) || el.querySelector('[id$="-' + key + '"]'), cell = c && (c.closest('.ctrl-knob') || c), p = m.controls[key];
      if (!cell) return;
      cell.classList.add('render-ctrl'); cell.dataset.kind = key.split('-')[0];
      if (p[4]) cell.dataset.style = p[4]; else delete cell.dataset.style;   // e.g. rocker: shade the off half
      // (important: the pedal's selects are otherwise sized to their text)
      cell.style.left = p[0] + 'px'; cell.style.top = p[1] + 'px';
      c.style.setProperty('width', p[2] + 'px', c.tagName === 'SELECT' ? 'important' : ''); c.style.height = p[3] + 'px';
    });
    // lamps and flipped bats left from the previous model's picture go
    el.querySelectorAll('.render-led[data-for]').forEach(n => { if (!(m.leds || {})[n.dataset.for]) n.remove(); });
    el.querySelectorAll('img.render-tog[data-for]').forEach(n => { if (!(m.toggles || {})[n.dataset.for]) n.remove(); });
    // a toggle is on by its value, or (a plain button) by its 'on' class; a change
    // of either, from a click or from the rack, lays the picture out again
    const isOn = c => !!c && (c.dataset.value !== undefined ? c.dataset.value !== '0' : c.classList.contains('on'));
    const watchOn = c => {
      if (!c || c._renderOn !== undefined) return;
      c._renderOn = isOn(c);
      new MutationObserver(() => { if (isOn(c) !== c._renderOn) { c._renderOn = isOn(c); if (el.dataset.render) layoutRendered(el, el.dataset.render); } })
        .observe(c, { attributes: true, attributeFilter: ['class', 'data-value'] });
    };
    // bat toggles drawn into the picture: their flipped bat laid over them while on
    Object.keys(m.toggles || {}).forEach(key => {
      let t = el.querySelector('img.render-tog[data-for="' + key + '"]');
      if (!t) { t = mk('img', { class: 'render-tog', 'data-for': key, alt: '' }); host.appendChild(t); }
      if (t.getAttribute('src') !== RENDER_BASE + dev + '-tog-' + key + '.webp') t.setAttribute('src', RENDER_BASE + dev + '-tog-' + key + '.webp');
      const p = m.toggles[key], c = el.querySelector('#' + key) || el.querySelector('[id$="-' + key + '"]');
      Object.assign(t.style, { left: p[0] + 'px', top: p[1] + 'px', width: p[2] + 'px', height: p[2] + 'px' });
      watchOn(c); t.hidden = !isOn(c);
    });
    // a picker (or two-way toggle) drawn as a knob: the knob's picture turns to the picked option's tick
    el.querySelectorAll('img.render-dial').forEach(n => { if (!(m.dials || {})[n.dataset.for]) n.remove(); });
    Object.keys(m.dials || {}).forEach(key => {
      const c = el.querySelector('[id$="-' + key + '"]'), d = m.dials[key], src = RENDER_BASE + dev + '-knob-' + key + '.webp';
      let k = el.querySelector('img.render-dial[data-for="' + key + '"]');
      if (!k) { k = mk('img', { class: 'render-dial', 'data-for': key, alt: '' }); el.appendChild(k); }
      if (k.getAttribute('src') !== src) k.setAttribute('src', src);
      // (a select's option, or a two-way toggle's side; a toggle's own click handler runs first)
      if (c && !c.dataset.dialHooked) { c.dataset.dialHooked = '1'; c.addEventListener(c.tagName === 'SELECT' ? 'change' : 'click', () => setTimeout(() => { if (el.dataset.render) layoutRendered(el, el.dataset.render); })); }
      const idx = !c ? 0 : c.tagName === 'SELECT' ? c.selectedIndex : (parseInt(c.dataset.value) > 0 ? 1 : 0);
      const a = d[3][Math.min(Math.max(idx, 0), d[3].length - 1)] - d[4];
      Object.assign(k.style, { left: d[0] + 'px', top: d[1] + 'px', width: d[2] + 'px', height: d[2] + 'px', transform: 'translate(-50%, -50%) rotate(' + a + 'deg)' });
    });
    // extra LEDs lit while a toggle is on (the mode lamp of a two-mode pedal),
    // or a picker is off its first option (a Sync lamp); 'sel-02:1': lit while
    // that picker is on option 1 (a row of lamps showing which one)
    Object.keys(m.leds || {}).forEach(key => {
      let lamp = el.querySelector('.render-led[data-for="' + key + '"]');
      if (!lamp) { lamp = mk('span', { class: 'render-led', 'data-for': key }); el.appendChild(lamp); }
      lamp.style.left = m.leds[key][0] + 'px'; lamp.style.top = m.leds[key][1] + 'px';
      const [ctl, opt] = key.split(':'), c = el.querySelector('[id$="-' + ctl + '"]'), v = c && (c.tagName === 'SELECT' ? c.value : isOn(c) ? (c.dataset.value || '1') : '0');
      if (c && c.tagName !== 'SELECT') watchOn(c);
      if (c && c.tagName === 'SELECT' && !c.dataset.ledHooked) { c.dataset.ledHooked = '1'; c.addEventListener('change', () => { if (el.dataset.render) layoutRendered(el, el.dataset.render); }); }
      lamp.classList.toggle('lit', opt !== undefined ? v === opt : (v !== undefined && v !== '' && v !== '0'));
    });
    const foot = el.querySelector('.foot');
    if (foot) { foot.style.left = m.switch[0] + 'px'; foot.style.top = m.switch[1] + 'px'; foot.style.width = foot.style.height = (m.switch[2] * 2) + 'px'; }
  }

  function slidersOn() { return document.body.classList.contains('sliders'); }
  // The device knob a wrap sits under ('' = none, also in sliders mode).
  function knobLook(wrap) {
    const dev = (!slidersOn() && wrap && wrap.closest) ? wrap.closest('[data-knob]') : null;
    return dev ? dev.dataset.knob : '';
  }
  // Keep the original round pointer knobs; Studio still supplies the faders.
  const drawRoundKnob = window.drawTickKnob;
  window.drawTickKnob = function (canvas, value127, wrap) {
    const look = knobLook(wrap);
    canvas.dataset.look = look;
    const deviceKnob = DEVICE_KNOBS[look];
    if (look.startsWith('render:')) {
      drawRenderedKnob(canvas, value127, wrap, look.slice(7));
    } else if (treadleDev(look, wrap)) {
      drawTreadleFrames(canvas, value127, wrap, treadleDev(look, wrap));
    } else if (deviceKnob) {
      deviceKnob(canvas, value127, wrap);
    } else if (slidersOn()) {
      drawGlassFader(canvas, value127, wrap);
    } else {
      // Reset the fader's backing size/transform and fit the round drawing
      // to its layout box instead of overflowing it at its native 70px.
      const size = wrap.clientWidth || 56;
      const pixels = Math.round(size * (window.devicePixelRatio || 1));
      canvas.width = pixels;
      canvas.height = pixels;
      canvas.dataset.logicalSize = '70';
      canvas.getContext('2d').setTransform(pixels / 70, 0, 0, pixels / 70, 0, 0);
      canvas.style.width = '100%';
      canvas.style.height = '100%';
      drawRoundKnob(canvas, value127, wrap);
    }
  };
  try { drawTickKnob = window.drawTickKnob; } catch (e) {}
  // a graphic EQ's faders on a rendered look slide its rendered carriage
  const drawPlainEqSlider = window.drawEqSlider;
  if (drawPlainEqSlider) window.drawEqSlider = function (canvas, value127, wrap) {
    const look = knobLook(wrap);
    if (look.startsWith('render:') && wrap.dataset.slider) drawRenderedKnob(canvas, value127, wrap, look.slice(7));
    else drawPlainEqSlider.apply(this, arguments);
  };

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
    const logo = mk('img', { class: 'editor-logo', src: '../assets/eleven-rack-editor-logo.png', alt: 'Eleven Rack Editor logo' });
    logo.setAttribute('role', 'button');
    logo.setAttribute('tabindex', '0');
    logo.setAttribute('aria-label', 'About Eleven Rack Editor');
    logo.title = 'About Eleven Rack Editor';
    logo.addEventListener('click', () => window.openEditorAbout());
    logo.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        window.openEditorAbout();
      }
    });
    brand.prepend(logo);
    const box = $('patch-name-box');
    const hint = box.querySelector('.hint');
    const slotLine = mk('div', { id: 'lcd-slot' });
    slotLine.appendChild(mk('span', { id: 'lcd-slot-text' }, '— · USER'));
    if (hint) {
      hint.textContent = '';
      hint.appendChild(mk('span', { 'data-preset-space': '0' }, '◀ user'));
      hint.appendChild(document.createTextNode(' · '));
      hint.appendChild(mk('span', { 'data-preset-space': '1' }, 'factory ▶'));
      slotLine.appendChild(hint);
    }
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
          '<div class="jacks"><span class="label jl">I</span><span class="label jl">II</span>' +
            '<div class="jack"></div><div class="jack x"></div><div class="jack x"></div><div class="jack x"></div><span class="label">Input</span></div>' +
          '<div id="amp-controls"></div>' +
          '<div class="pilot-wrap"><div class="rockers"><span><b>Off</b><i></i><b>On</b></span><span><b>Standby</b><i></i><b>On</b></span></div><div class="pilot"></div><span class="label">On</span></div>' +
          '<i class="corner hc bl"></i><i class="corner hc br"></i>' +
        '</div>' +
        '<div class="head-front"><i class="corner hc tl"></i><i class="corner hc tr"></i><div class="plate" id="amp-head-plate"></div></div>' +
        '<div class="cab"><div class="grille"><div class="speakers" id="amp-speakers" data-n="2"><i></i><i></i></div><div class="plate" id="amp-plate">Eleven Rack</div></div>' +
          '<i class="corner tl"></i><i class="corner tr"></i><i class="corner bl"></i><i class="corner br"></i>' +
          '<div class="mic" id="amp-mic" aria-hidden="true"></div></div>' +
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
      '<div class="kv" id="fx-card-model-row"><span class="label">Model</span><span class="val" id="fx-card-model">—</span></div>' +
      '<div class="kv"><span class="label">State</span><span class="val" id="fx-card-state">—</span></div>' +
      '<div class="kv"><span class="label">Tip</span><span class="txt">The knobs on the pedal are the block\'s real parameters. The footswitch bypasses it, the same as clicking its name in the signal path.</span></div>' +
      '<button class="bt-btn" id="fx-card-back" type="button">Back to the amp</button>');
    side.appendChild(ampCard); side.appendChild(fxCard);
    // each pedal's model picker moves into this card while its pedal is in focus
    Object.keys(PEDALS).forEach(id => { const dd = $(id) && $(id).querySelector('.scard-hdr .ctrl-dd'); if (dd) dd.dataset.home = id; });
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
      '</div><div class="meter-status"><span class="vu-source" id="vu-source">Audio levels unavailable</span><span class="activity-label" title="Incoming MIDI activity"><i class="activity-led" id="midi-activity-led" aria-hidden="true"></i>MIDI IN</span></div><div class="meter-row" id="meter-row"></div>');
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
    try { syncLCD(); syncAmp(); syncDevices(); syncChainIcons(); syncFocus(); syncMatrixSeg(); } catch (e) { /* never let a readout break the app */ }
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
  // drawn mics, side view with the head towards the speaker
  const MIC_SVG = {
    dyn57: '<svg viewBox="0 0 150 60" xmlns="http://www.w3.org/2000/svg">' +
      '<defs><pattern id="mic-mesh" width="2.4" height="2.4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="2.4" height="2.4" fill="#1d2024"/><rect width="1.1" height="2.4" fill="#8d939b"/><rect width="2.4" height=".8" fill="#5d636b"/></pattern>' +
      '<linearGradient id="mic-shade" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".55"/><stop offset=".3" stop-color="#fff" stop-opacity=".08"/><stop offset=".6" stop-color="#000" stop-opacity=".1"/><stop offset="1" stop-color="#000" stop-opacity=".7"/></linearGradient>' +
      '<linearGradient id="mic-body" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#6b7077"/><stop offset=".18" stop-color="#2a2d32"/><stop offset=".55" stop-color="#16181b"/><stop offset="1" stop-color="#050506"/></linearGradient>' +
      '<linearGradient id="mic-metal" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fafbfc"/><stop offset=".35" stop-color="#c2c7cd"/><stop offset=".7" stop-color="#6b7077"/><stop offset="1" stop-color="#3a3e44"/></linearGradient></defs>' +
      '<path d="M133 30 C143 31 146 44 150 60" fill="none" stroke="#0b0b0c" stroke-width="5.5"/>' +
      '<path d="M133 30 C143 31 146 44 150 60" fill="none" stroke="rgba(255,255,255,.18)" stroke-width="1.2" transform="translate(-1 -1)"/>' +
      // grille: mesh cylinder with a rounded nose and two ribs
      '<path d="M40 18.5 H13 C6 18.5 3 23 3 30 C3 37 6 41.5 13 41.5 H40 Z" fill="url(#mic-mesh)"/>' +
      '<path d="M40 18.5 H13 C6 18.5 3 23 3 30 C3 37 6 41.5 13 41.5 H40 Z" fill="url(#mic-shade)" stroke="#0e0f11" stroke-width="1"/>' +
      '<rect x="20" y="18" width="2.2" height="24" fill="url(#mic-metal)" opacity=".9"/><rect x="31" y="18" width="2.2" height="24" fill="url(#mic-metal)" opacity=".9"/>' +
      '<rect x="39" y="17" width="6" height="26" rx="1.5" fill="url(#mic-metal)" stroke="#2a2d31" stroke-width=".8"/>' +
      // tapered body with a soft specular band
      '<path d="M45 17.5 L121 23.5 L121 36.5 L45 42.5 Z" fill="url(#mic-body)" stroke="#040405" stroke-width=".8"/>' +
      '<path d="M47 20 L119 25 L119 26.6 L47 23 Z" fill="#fff" opacity=".22"/>' +
      // swivel clip
      '<path d="M76 37 h16 l-2 12 h-12 Z" fill="#141518" stroke="#000" stroke-width=".8"/><circle cx="84" cy="44" r="3" fill="url(#mic-metal)" stroke="#111"/>' +
      // connector end
      '<rect x="121" y="22.5" width="13" height="15" rx="2" fill="url(#mic-metal)" stroke="#2a2d31" stroke-width=".8"/>' +
      '<path d="M124 23 v14 M127.5 23 v14 M131 23 v14" stroke="rgba(0,0,0,.25)" stroke-width=".8"/></svg>',
  };
  // Per-model looks: amp faceplate, head + cabinet, mic and the DIST pedal.
  function syncDevices() {
    const key = (typeof currentAmpKey !== 'undefined') ? currentAmpKey : null;
    const obj = $('amp-obj'); if (!obj) return;
    const ampDev = (key && AMP_DEVICE[key]) || '';
    const cabSel = $('cab-type-select'), cabIdx = cabSel ? parseInt(cabSel.value, 10) : -1;
    const cabDev = CAB_DEVICE[cabIdx] || '';
    const micSel = $('mic-type-select'), micIdx = micSel ? parseInt(micSel.value, 10) : -1;
    const micDev = MIC_DEVICE[micIdx] || '';
    setDevice(obj, ampDev);
    if (obj.dataset.cab !== cabDev) { if (cabDev) obj.dataset.cab = cabDev; else delete obj.dataset.cab; }
    // a rendered cabinet: its picture under the grille's name plate
    const cabRender = { basket412: 'cab-green25', green20: 'cab-green20', ac212: 'cab-ac212', tweed410: 'cab-tweed410', tweed112: 'cab-tweed112', mk1960: 'cab-1960', mk1960c30: 'cab-1960c30' }[cabDev], cabEl = obj.querySelector('.cab');
    if (cabEl) {
      let ci = cabEl.querySelector(':scope > img.render-cab');
      if (cabRender && RENDERS[cabRender]) {
        if (!ci) { ci = mk('img', { class: 'render-cab', alt: '' }); cabEl.insertAdjacentElement('afterbegin', ci); }
        const src = RENDER_BASE + cabRender + '-body.webp';
        if (ci.getAttribute('src') !== src) ci.setAttribute('src', src);
        const cm = RENDERS[cabRender];
        if (cm.img) Object.assign(ci.style, { left: cm.img.left + 'px', top: cm.img.top + 'px', width: cm.img.width + 'px', height: cm.img.height + 'px' });
        // (a picture as tall as its own front; one with its name lettered on hides the plate)
        cabEl.style.height = cm.height ? cm.height + 'px' : '';
        const plate = $('amp-plate');
        if (plate && cm.plate) { plate.style.left = (cm.plate[0] - 88) + 'px'; plate.style.top = (cm.plate[1] - 15) + 'px'; }
        if (plate) plate.style.visibility = cm.label === 'baked' ? 'hidden' : '';
        obj.dataset.cabRender = cabRender;
      } else {
        if (ci) ci.remove(); delete obj.dataset.cabRender; cabEl.style.height = '';
        const plate = $('amp-plate'); if (plate) plate.style.visibility = '';
      }
    }
    obj.classList.toggle('stack', !!cabDev || ampDev === 'plexi' || !!RENDERS[ampDev]);   // a Plexi, or any drawn head, is always a head
    const hp = $('amp-head-plate'); if (hp) hp.textContent = (typeof currentAmpName !== 'undefined' && currentAmpName) ? currentAmpName.replace(/^\d+\s+/, '') : '';
    // a separate cabinet carries its own name; the head front carries the amp's
    const plate = $('amp-plate'); if (plate && obj.classList.contains('stack')) plate.textContent = selectedText('cab-type-select');
    const mic = $('amp-mic');
    if (mic && mic.dataset.dev !== micDev) { mic.dataset.dev = micDev; mic.innerHTML = MIC_SVG[micDev] || ''; }
    if (mic) mic.classList.toggle('off-axis', ($('axis-btn') || {}).textContent === 'OFF AXIS');

    const vol = $('panel-vol');
    if (vol) setDevice(vol, 'fv-vol');
    const fxl = $('panel-fxloop');
    if (fxl) setDevice(fxl, RENDERS['fx-loop'] ? 'fx-loop' : '');
    const rvb = $('panel-reverb');
    if (rvb) { const rs = $('reverb-model-select'), rd = (rs && REVERB_DEVICE[parseInt(rs.value, 10)]) || ''; setDevice(rvb, RENDERS[rd] ? rd : ''); }
    const dly = $('panel-delay');
    if (dly) { const ds = $('delay-model-select'), dd = (ds && DELAY_DEVICE[parseInt(ds.value, 10)]) || ''; setDevice(dly, RENDERS[dd] ? dd : ''); }
    const fxh = $('panel-fxhost');
    if (fxh) {
      // only a rendered look: these models have no drawn one
      const fs = $('fxhost-model-select'), fd = (fs && FX_DEVICE[parseInt(fs.value, 10)]) || '';
      setDevice(fxh, RENDERS[fd] ? fd : '');
    }
    const wah = $('panel-wah');
    if (wah) { const ws = $('wah-model-select'); setDevice(wah, (ws && WAH_DEVICE[parseInt(ws.value, 10)]) || ''); }
    const dist = $('panel-dist');
    if (dist) {
      const sel = $('dist-model-select');
      const distDev = (sel && DIST_DEVICE[parseInt(sel.value, 10)]) || '';
      setDevice(dist, distDev);
      let legend = dist.querySelector('.device-legend');
      if (!legend) { legend = mk('div', { class: 'device-legend' }); dist.insertBefore(legend, dist.querySelector('.pedal-foot')); }
      const l = DEVICE_LEGEND[distDev] || ['', ''];
      if (legend.dataset.dev !== distDev) { legend.dataset.dev = distDev; legend.innerHTML = '<b></b><span></span>'; legend.firstChild.textContent = l[0]; legend.lastChild.textContent = l[1]; }
    }
    // Panels build their knobs before attaching them, so a fresh knob is
    // drawn without its look: redraw every knob whose look is stale.
    document.querySelectorAll('.knob-wrap[data-style="tick"]').forEach(function (wrap) {
      const c = wrap.querySelector('canvas.knob-canvas');
      if (c && (c.dataset.look || '') !== knobLook(wrap)) drawKnob(c, clamp127(wrap.dataset.value));
    });
  }
  // Set (or clear) an element's look and the knob it carries.
  function setDevice(el, dev) {
    // a rendered look takes data-render (and its picture knobs); a drawn
    // one data-device and the knob its look carries
    const rendered = !!RENDERS[dev] && !RENDERS[dev].frames;   // treadle frames keep the drawn layout
    if ((el.dataset.device || '') !== (rendered ? '' : dev) || (el.dataset.render || '') !== (rendered ? dev : '')) {
      const knob = rendered ? 'render:' + dev : (DEVICE_KNOB[dev] || '');
      if (dev && !rendered) el.dataset.device = dev; else delete el.dataset.device;
      if (rendered) el.dataset.render = dev; else delete el.dataset.render;
      if (knob) el.dataset.knob = knob; else delete el.dataset.knob;
    }
    if (el.classList.contains('pedal') || el.id === 'amp-obj') layoutRendered(el, rendered ? dev : '');
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
      // the pedal's model picker into the fx card, any other one back home
      const dd = document.querySelector('.ctrl-dd[data-home="' + pedal.id + '"]'), row = $('fx-card-model-row');
      document.querySelectorAll('.ctrl-dd[data-home]').forEach(d => {
        if (d === dd || !row || d.parentElement !== row) return;
        const hdr = $(d.dataset.home).querySelector('.scard-hdr');
        hdr.insertBefore(d, hdr.querySelector(':scope > button'));
      });
      if (row) { if (dd && dd.parentElement !== row) row.appendChild(dd); row.classList.toggle('has-dd', !!dd); }
      const msel = dd ? dd.querySelector('select') : null;
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
      const sel = msel;
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
     'setTrueZDisplay', 'openFxHostPanel', 'closeFxHostPanel', 'renderDistKnobs', 'renderFxHostKnobs', 'updateFxHostKnob', 'refreshBlockBypassDisplays', 'updateMonoIndicator', 'applyNumberDisplayMode'].forEach(hook);
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
  // VU METERS — Rig Out L/R. Without fresh audio levels, needles rest
  // at the bottom of the scale. MIDI and volume settings are not levels.
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
  const VU = { l: { angle: -46, last: 0 }, r: { angle: -46, last: 0 }, raf: null, ext: null, extAt: 0 };
  const activity = { midiUntil: 0 };
  function updateActivity(now) {
    const connected = typeof bridgeMidiReady !== 'undefined' && bridgeMidiReady;
    const midi = $('midi-activity-led');
    if (midi) midi.classList.toggle('on', connected && now < activity.midiUntil);
  }
  if (typeof handleBridgeMsg === 'function') {
    const orig = handleBridgeMsg;
    window.handleBridgeMsg = function (msg) {
      if (msg && msg.type === 'midi_in') activity.midiUntil = performance.now() + 100;
      return orig.apply(this, arguments);
    };
    try { handleBridgeMsg = window.handleBridgeMsg; } catch (e) {}
  }
  function rad(deg) { return (deg - 90) * Math.PI / 180; }

  // The face is drawn once into an offscreen canvas: redrawing its gradients
  // and labels every frame kept WebKit busy and made the whole editor slow
  // without GPU acceleration.
  const VU_W = 200, VU_H = 118, VU_PX = VU_W / 2, VU_PY = VU_H, VU_R = 88;
  function meterFace(m, dpr, label) {
    const w = VU_W, h = VU_H, px = VU_PX, py = VU_PY, r = VU_R, key = label + '@' + dpr;
    if (m.face && m.faceKey === key) return m.face;
    const face = document.createElement('canvas');
    face.width = Math.round(w * dpr); face.height = Math.round(h * dpr);
    const ctx = face.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    let g = ctx.createRadialGradient(w / 2, h * 0.1, 4, w / 2, h * 0.6, w * 0.8);
    g.addColorStop(0, '#f8f0da'); g.addColorStop(0.6, '#f1e7cc'); g.addColorStop(1, '#d0c09b');
    rr(ctx, 0, 0, w, h, 8); ctx.fillStyle = g; ctx.fill();
    g = ctx.createRadialGradient(w / 2, h * 0.1, 2, w / 2, h * 0.1, w * 0.6);
    g.addColorStop(0, 'rgba(255,196,110,0.35)'); g.addColorStop(1, 'rgba(255,196,110,0)');
    ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
    // scale: an arc from the pivot, red only from 0 to +3
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
    ctx.font = '700 5.5px Manrope, Helvetica, Arial, sans-serif'; ctx.fillText('PEAK', w - 14, 23);
    m.face = face; m.faceKey = key;
    return face;
  }
  // Fonts that finish loading after the first frame need a new face.
  if (document.fonts) document.fonts.addEventListener('loadingdone', function () { VU.l.face = VU.r.face = null; });

  function drawMeter(canvas, m, db, now, label) {
    const w = VU_W, h = VU_H, px = VU_PX, py = VU_PY, r = VU_R;
    const dt = Math.min(0.05, (now - (m.last || now)) / 1000); m.last = now;
    const target = dbToAngle(db);
    m.angle += (target - m.angle) * Math.min(1, dt * 14);
    const lit = db >= 2, face = meterFace(m, Math.min(window.devicePixelRatio || 1, 3), label);
    // A resting needle needs no new frame.
    if (m.canvas === canvas && m.drawn === face && m.lit === lit && Math.abs(m.angle - m.drawnAngle) < 0.05) return;
    m.canvas = canvas; m.drawn = face; m.lit = lit; m.drawnAngle = m.angle;
    const ctx = prep(canvas, w, h);
    ctx.drawImage(face, 0, 0, w, h);
    // needle + pivot
    const a = rad(m.angle);
    ctx.save(); ctx.shadowColor = 'rgba(0,0,0,0.35)'; ctx.shadowBlur = 2; ctx.shadowOffsetY = 1;
    ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(px + Math.cos(a) * (r + 6), py + Math.sin(a) * (r + 6));
    ctx.strokeStyle = '#111'; ctx.lineWidth = 1.6; ctx.lineCap = 'round'; ctx.stroke(); ctx.restore();
    ctx.beginPath(); ctx.arc(px, py, 10, 0, Math.PI * 2); ctx.fillStyle = '#2b2e33'; ctx.fill();
    // peak lamp
    ctx.beginPath(); ctx.arc(w - 14, 14, 3.5, 0, Math.PI * 2); ctx.fillStyle = lit ? '#ff3b30' : '#5a1a16'; ctx.fill();
    if (lit) { ctx.save(); ctx.shadowColor = '#ff3b30'; ctx.shadowBlur = 8; ctx.fill(); ctx.restore(); }
  }
  function vuLoop(now) {
    updateActivity(now);
    const cl = $('vu-l'), cr = $('vu-r');
    if (!cl || !cr) { VU.raf = null; return; }
    let dbL, dbR;
    if (VU.ext && now - VU.extAt < 400) { dbL = VU.ext.l; dbR = VU.ext.r; }
    else {
      dbL = dbR = -Infinity;
      if (VU.ext) vuSetState('stale', 'Audio levels unavailable');
    }
    drawMeter(cl, VU.l, dbL, now, 'RIG OUT L');
    drawMeter(cr, VU.r, dbR, now, 'RIG OUT R');
    VU.raf = requestAnimationFrame(vuLoop);
  }
  function startVU() { if (!VU.raf) VU.raf = requestAnimationFrame(vuLoop); }
  window.studioVU = {
    setLevels: function (dbL, dbR) { VU.ext = { l: dbL, r: dbR }; VU.extAt = performance.now(); },
    setSource: function (text) { const s = $('vu-source'); if (s) s.textContent = text; },
  };
  // Real level from the audio driver: main.js streams the engine's RMS meter
  // for Eleven Rig L/R (0..1 linear) ~30x/s. 0 VU is placed at -18 dBFS RMS.
  const FALLBACK_TEXT = 'Audio levels unavailable';
  let vuState = '';
  function vuSetState(state, text) { if (vuState === state) return; vuState = state; VU.ext = null; window.studioVU.setSource(text); }
  function rmsToVu(x) { return 20 * Math.log10(Math.max(x, 1e-6)) + 18; }
  if (window.electronAPI && typeof window.electronAPI.onVuLevels === 'function') {
    window.electronAPI.onVuLevels(function (d) {
      if (!d || d.available === false) { vuSetState('off', FALLBACK_TEXT + ' · no audio source'); return; }
      if (!d.running) { vuSetState('idle', 'Rack audio idle'); return; }
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
