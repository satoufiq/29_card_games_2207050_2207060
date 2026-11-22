/* =====================================================================
   Bangladesh 29 — table director
   The server is the single source of truth. This client polls state after
   every action, diffs it with the previous state and turns each difference
   into an animation (deal, bid, card flight, trick sweep, trump reveal...).
   ===================================================================== */
'use strict';

// ------------------------------------------------------------------ utils
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const sleep = (ms) => new Promise((r) => setTimeout(r, Math.max(0, ms)));
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const store = {
  get(k, d) { try { const v = localStorage.getItem('b29.' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem('b29.' + k, JSON.stringify(v)); } catch (e) { /* storage unavailable */ } },
};

// ------------------------------------------------------------------ icons
const ICONS = {
  play: '<polygon points="7 4 20 12 7 20 7 4"/>',
  pause: '<rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/>',
  step: '<polygon points="5 4 15 12 5 20 5 4"/><line x1="19" y1="5" x2="19" y2="19"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-7 8-7s8 3 8 7"/>',
  cpu: '<rect x="5" y="5" width="14" height="14" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
  book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5z"/><path d="M6.5 17A2.5 2.5 0 0 0 4 19.5 2.5 2.5 0 0 0 6.5 22H20v-5"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  rotate: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>',
  flame: '<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.4-.5-2-1-3-1.1-2.1-.2-4 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.2.4-2.3 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>',
  brain: '<circle cx="12" cy="12" r="9"/><polygon points="15.5 8.5 13.4 13.4 8.5 15.5 10.6 10.6"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
  volume: '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14"/>',
  mute: '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="22" y1="9" x2="16" y2="15"/><line x1="16" y1="9" x2="22" y2="15"/>',
  menu: '<line x1="4" y1="7" x2="20" y2="7"/><line x1="4" y1="12" x2="20" y2="12"/><line x1="4" y1="17" x2="20" y2="17"/>',
  sparkles: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 15l.7 2.1L22 18l-2.3.8L19 21l-.7-2.2L16 18l2.3-.9z"/>',
  scroll: '<path d="M8 21h11a2 2 0 0 0 2-2v-2H10v2a2 2 0 1 1-4 0V5a2 2 0 1 0-4 0v3h4"/><path d="M19 17V5a2 2 0 0 0-2-2H4"/><path d="M11 8h5M11 12h5"/>',
  x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
  crown: '<path d="M2 18h20M3 18L2 7l6 5 4-8 4 8 6-5-1 11"/>',
  trophy: '<path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0z"/><path d="M17 5h3v2a4 4 0 0 1-4 4M7 5H4v2a4 4 0 0 0 4 4"/>',
  bulb: '<path d="M9 18h6M10 22h4"/><path d="M12 2a7 7 0 0 0-4 12.7V17h8v-2.3A7 7 0 0 0 12 2z"/>',
  eye: '<path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/><circle cx="12" cy="12" r="3"/>',
  swords: '<path d="M14.5 17.5L3 6V3h3l11.5 11.5M13 19l6-6M16 16l4 4M19 21l2-2"/>',
};
const svg = (name) => `<svg class="ic" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ''}</svg>`;
function hydrateIcons(root = document) {
  $$('[data-icon]', root).forEach((el) => { if (!el.dataset.iconDone) { el.insertAdjacentHTML('afterbegin', svg(el.dataset.icon)); el.dataset.iconDone = '1'; } });
}
const PERSONA_ICON = { AGGRESSIVE: 'flame', STRATEGIC: 'brain', DEFENSIVE: 'shield', HUMAN: 'user' };
const PERSONA_LABEL = { AGGRESSIVE: 'Aggressive', STRATEGIC: 'Strategic', DEFENSIVE: 'Defensive', HUMAN: 'You' };

// ------------------------------------------------------------------ settings
const prefersReduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const S = Object.assign({ sound: true, volume: 0.6, reduced: prefersReduced, pace: 'normal', insight: true }, store.get('settings', {}));
function saveSettings() { store.set('settings', S); applySettings(); }
function applySettings() {
  document.body.classList.toggle('reduced', !!S.reduced);
  ['#btn-sound', '#menu-sound'].forEach((id) => {
    const b = $(id); if (!b) return;
    b.innerHTML = svg(S.sound ? 'volume' : 'mute');
    b.classList.toggle('muted-state', !S.sound);
  });
  if (Sfx.master) Sfx.master.gain.value = S.volume;
}
const PACE = { relaxed: 1.35, normal: 1, fast: 0.55 };
const pace = () => (S.reduced ? 0.35 : PACE[S.pace] || 1);

// ------------------------------------------------------------------ sound (WebAudio synth)
const Sfx = {
  ctx: null, master: null, noiseBuf: null,
  ensure() {
    if (!this.ctx) {
      try {
        this.ctx = new (window.AudioContext || window.webkitAudioContext)();
        this.master = this.ctx.createGain();
        this.master.gain.value = S.volume;
        this.master.connect(this.ctx.destination);
        const len = this.ctx.sampleRate;
        this.noiseBuf = this.ctx.createBuffer(1, len, this.ctx.sampleRate);
        const d = this.noiseBuf.getChannelData(0);
        for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
      } catch (e) { this.ctx = null; }
    }
    if (this.ctx && this.ctx.state === 'suspended') this.ctx.resume();
    return !!this.ctx;
  },
  noise(dur, freq, q, gain, when = 0, type = 'bandpass') {
    const c = this.ctx, t = c.currentTime + when;
    const src = c.createBufferSource(); src.buffer = this.noiseBuf;
    const f = c.createBiquadFilter(); f.type = type; f.frequency.value = freq; f.Q.value = q;
    const g = c.createGain(); g.gain.setValueAtTime(gain, t); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    src.connect(f); f.connect(g); g.connect(this.master);
    src.start(t, Math.random() * 0.5); src.stop(t + dur + 0.02);
  },
  tone(freq, dur, type = 'sine', gain = 0.2, when = 0, slideTo = null, attack = 0.005) {
    const c = this.ctx, t = c.currentTime + when;
    const o = c.createOscillator(); o.type = type; o.frequency.setValueAtTime(freq, t);
    if (slideTo) o.frequency.exponentialRampToValueAtTime(slideTo, t + dur);
    const g = c.createGain(); g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(gain, t + attack);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g); g.connect(this.master); o.start(t); o.stop(t + dur + 0.05);
  },
  play(name) {
    if (!S.sound || !this.ensure()) return;
    switch (name) {
      case 'flick': this.noise(0.07, 3200 + Math.random() * 900, 1.2, 0.35); break;
      case 'place': this.noise(0.09, 1800, 0.9, 0.4); this.tone(140, 0.08, 'sine', 0.18); break;
      case 'chip': this.tone(1320, 0.09, 'triangle', 0.12); this.tone(1760, 0.12, 'triangle', 0.1, 0.05); break;
      case 'pass': this.tone(330, 0.18, 'sine', 0.08, 0, 260); break;
      case 'collect': this.noise(0.28, 900, 0.6, 0.25, 0, 'lowpass'); this.tone(520, 0.12, 'sine', 0.06, 0.05, 780); break;
      case 'reveal': [523, 659, 784, 1046, 1318].forEach((f, i) => this.tone(f, 0.9, 'triangle', 0.09, i * 0.08)); this.noise(0.9, 6000, 0.4, 0.08, 0.1, 'highpass'); break;
      case 'chime': [880, 1108, 1318].forEach((f, i) => this.tone(f, 1.1, 'sine', 0.1, i * 0.12)); break;
      case 'made': [523, 659, 784].forEach((f, i) => this.tone(f, 0.5, 'triangle', 0.12, i * 0.1)); break;
      case 'failed': [392, 330, 262].forEach((f, i) => this.tone(f, 0.5, 'sine', 0.1, i * 0.12)); break;
      case 'win': [523, 659, 784, 1046, 784, 1046, 1318].forEach((f, i) => this.tone(f, 0.45, 'triangle', 0.13, i * 0.11)); break;
      case 'lose': [440, 392, 349, 262].forEach((f, i) => this.tone(f, 0.6, 'sine', 0.1, i * 0.16)); break;
      case 'click': this.tone(900, 0.04, 'square', 0.03); break;
      case 'single': [392, 523, 659, 880].forEach((f, i) => this.tone(f, 0.6, 'sawtooth', 0.05, i * 0.07)); break;
      default: break;
    }
  },
};

// ------------------------------------------------------------------ ambient background
const BG = {
  cv: null, cx: null, w: 0, h: 0, parts: [], glyphs: [], raf: 0,
  init() {
    this.cv = $('#bg-canvas'); this.cx = this.cv.getContext('2d');
    this.resize(); window.addEventListener('resize', () => this.resize());
    for (let i = 0; i < 70; i++) this.parts.push(this.spawn(true));
    const sy = ['♠', '♥', '♦', '♣'];
    for (let i = 0; i < 9; i++) this.glyphs.push({ x: Math.random(), y: Math.random(), s: 18 + Math.random() * 40, v: 0.00004 + Math.random() * 0.00008, r: Math.random() * 6, g: sy[i % 4], a: 0.03 + Math.random() * 0.05 });
    this.loop = this.loop.bind(this); this.raf = requestAnimationFrame(this.loop);
  },
  spawn(anywhere) {
    return { x: Math.random() * this.w, y: anywhere ? Math.random() * this.h : this.h + 10, r: 0.6 + Math.random() * 1.8, vy: 0.12 + Math.random() * 0.35, vx: (Math.random() - 0.5) * 0.15, p: Math.random() * Math.PI * 2 };
  },
  resize() {
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    this.w = window.innerWidth; this.h = window.innerHeight;
    [this.cv, $('#fx-canvas')].forEach((c) => { c.width = this.w * dpr; c.height = this.h * dpr; c.getContext('2d').setTransform(dpr, 0, 0, dpr, 0, 0); });
  },
  loop(t) {
    const cx = this.cx; cx.clearRect(0, 0, this.w, this.h);
    const menu = $('#screen-menu').classList.contains('active');
    const still = S.reduced;
    if (menu) {
      cx.save(); cx.textAlign = 'center'; cx.textBaseline = 'middle';
      this.glyphs.forEach((g) => {
        if (!still) { g.y -= g.v * 16; if (g.y < -0.1) g.y = 1.1; }
        cx.font = `${g.s}px Cinzel, serif`; cx.fillStyle = `rgba(232,199,111,${g.a})`;
        cx.save(); cx.translate(g.x * this.w, g.y * this.h); cx.rotate(Math.sin(t / 4000 + g.r) * 0.3); cx.fillText(g.g, 0, 0); cx.restore();
      });
      cx.restore();
    }
    const count = menu ? this.parts.length : Math.floor(this.parts.length * 0.45);
    for (let i = 0; i < count; i++) {
      const p = this.parts[i];
      if (!still) { p.y -= p.vy; p.x += p.vx + Math.sin(t / 2000 + p.p) * 0.1; if (p.y < -10) this.parts[i] = this.spawn(false); }
      const tw = 0.35 + 0.65 * Math.abs(Math.sin(t / 900 + p.p));
      const grd = cx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * 4);
      grd.addColorStop(0, `rgba(255,232,170,${0.55 * tw})`); grd.addColorStop(1, 'rgba(255,232,170,0)');
      cx.fillStyle = grd; cx.beginPath(); cx.arc(p.x, p.y, p.r * 4, 0, Math.PI * 2); cx.fill();
    }
    this.raf = requestAnimationFrame(this.loop);
  },
};

const FX = {
  cv: null, cx: null, parts: [], running: false,
  init() { this.cv = $('#fx-canvas'); this.cx = this.cv.getContext('2d'); },
  confetti(n = 160) {
    if (S.reduced) return;
    const cols = ['#f6e3a1', '#e8c76f', '#fffcf3', '#4fd6a6', '#c19a3c', '#ff9a6b'];
    for (let i = 0; i < n; i++) this.parts.push({ x: window.innerWidth / 2 + (Math.random() - 0.5) * 300, y: window.innerHeight * 0.35, vx: (Math.random() - 0.5) * 14, vy: -Math.random() * 14 - 4, g: 0.32, s: 5 + Math.random() * 7, r: Math.random() * 6, vr: (Math.random() - 0.5) * 0.4, c: cols[i % cols.length], life: 160 + Math.random() * 80 });
    this.run();
  },
  burst(x, y, n = 50) {
    if (S.reduced) return;
    for (let i = 0; i < n; i++) { const a = Math.random() * Math.PI * 2, v = 2 + Math.random() * 7; this.parts.push({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, g: 0.05, s: 2 + Math.random() * 3, r: 0, vr: 0, c: Math.random() < 0.5 ? '#fff1c1' : '#e8c76f', life: 50 + Math.random() * 40, spark: true }); }
    this.run();
  },
  run() {
    if (this.running) return; this.running = true;
    const step = () => {
      const cx = this.cx; cx.clearRect(0, 0, window.innerWidth, window.innerHeight);
      this.parts = this.parts.filter((p) => p.life > 0);
      this.parts.forEach((p) => {
        p.vy += p.g; p.vx *= 0.99; p.x += p.vx; p.y += p.vy; p.r += p.vr; p.life -= 1;
        cx.globalAlpha = Math.min(1, p.life / 40); cx.fillStyle = p.c;
        if (p.spark) { cx.beginPath(); cx.arc(p.x, p.y, p.s, 0, Math.PI * 2); cx.fill(); }
        else { cx.save(); cx.translate(p.x, p.y); cx.rotate(p.r); cx.fillRect(-p.s / 2, -p.s / 4, p.s, p.s / 2); cx.restore(); }
      });
      cx.globalAlpha = 1;
      if (this.parts.length) requestAnimationFrame(step); else { this.running = false; cx.clearRect(0, 0, window.innerWidth, window.innerHeight); }
    };
    requestAnimationFrame(step);
  },
};

// ------------------------------------------------------------------ cards
const SUIT_SYM = { Hearts: '♥', Diamonds: '♦', Clubs: '♣', Spades: '♠' };
const SUIT_FROM_LETTER = { H: 'Hearts', D: 'Diamonds', C: 'Clubs', S: 'Spades' };
const RED = { Hearts: true, Diamonds: true };
const POINTS = { J: 3, 9: 2, A: 1, 10: 1 };
function parseCode(code) {
  const s = SUIT_FROM_LETTER[code.slice(-1)]; const r = code.slice(0, -1);
  return { suit: s, rank: r, code, points: POINTS[r] || 0, symbol: SUIT_SYM[s] };
}
// Card artwork lives in web/cards/*.svg.
function cardFace(c, cls = '') {
  if (typeof c === 'string') c = parseCode(c);
  const code = c.code || (c.rank + c.suit[0]);
  const label = `${c.rank}${SUIT_SYM[c.suit] || ''}`;
  return `<div class="card face ${RED[c.suit] ? 'red' : 'black'} ${cls}" data-code="${code}"><img src="cards/${code}.svg" alt="${label}" draggable="false"></div>`;
}
const cardBack = (cls = '') => `<div class="card back ${cls}"><img src="cards/back.svg" alt="" draggable="false"></div>`;
function preloadCards() {
  ['back', ...['S', 'H', 'D', 'C'].flatMap((s) => ['7', '8', '9', '10', 'J', 'Q', 'K', 'A'].map((r) => r + s))]
    .forEach((n) => { const i = new Image(); i.src = `cards/${n}.svg`; });
}

// ------------------------------------------------------------------ API
async function getState() {
  const r = await fetch('/api/state', { cache: 'no-store' });
  if (!r.ok) throw new Error('state ' + r.status);
  return r.json();
}
async function act(action, extra = {}) {
  const r = await fetch('/api/action', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.assign({ action }, extra)) });
  return r.json();
}

// ------------------------------------------------------------------ toasts / center calls
function toast(msg, kind = '') {
  const t = document.createElement('div'); t.className = 'toast ' + kind; t.textContent = msg;
  $('#toasts').appendChild(t); setTimeout(() => t.remove(), 3800);
}
function centerCall(html, cls = '', low = false) {
  const host = $('#center-call'); host.classList.toggle('low', low); host.innerHTML = `<div class="call ${cls}">${html}</div>`;
}
function floatPoints(text, x, y) {
  const f = document.createElement('div'); f.className = 'float-pts'; f.textContent = text;
  f.style.left = x + 'px'; f.style.top = y + 'px'; document.body.appendChild(f); setTimeout(() => f.remove(), 1600);
}
function countUp(el, to, dur = 700) {
  if (!el) return;
  const from = parseFloat(el.dataset.v ?? el.textContent) || 0;
  el.dataset.v = to;
  if (from === to || S.reduced) { el.textContent = to; return; }
  const t0 = performance.now();
  const tick = (t) => {
    const k = clamp((t - t0) / dur, 0, 1); const e = 1 - Math.pow(1 - k, 3);
    el.textContent = Math.round(from + (to - from) * e);
    if (k < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

// ------------------------------------------------------------------ game state & layout
const G = {
  st: null, viewer: 0, token: 0, wakeFn: null, paused: false, stepOnce: false,
  dealId: null, dealStage: 0, bidSeen: 0, trickKey: null, trickSeen: 0, pendingFrom: null,
  dealing: false, revealedKey: null, marriageKey: null, singleKey: null, insightSeq: 0, logSeen: -1,
  handKey: '', dockKey: '', seatKeys: {}, spSpeed: store.get('spSpeed', 'normal'), started: false,
  defaults: null, cfg: null, lastRoundShown: null, prevGP: null,
};
// Seats in play order go clockwise around the screen: you (bottom) → left → top → right.
const POS = ['bottom', 'left', 'top', 'right'];
const posOf = (seat) => POS[(seat - G.viewer + 4) % 4];
const seatEl = (seat) => $('#seat-' + posOf(seat));
const slotEl = (seat) => $(`.trick-slot[data-pos="${posOf(seat)}"]`);
const nameOf = (seat) => (G.st && G.st.players && G.st.players[seat] ? G.st.players[seat].name : 'P' + seat);
const teamOf = (seat) => (seat % 2 === 0 ? 0 : 1);
const initialsOf = (name) => {
  const n = String(name || '').trim();
  if (!n) return '?';
  if (n === 'You') return 'You';
  const parts = n.split(' ').filter(Boolean);
  return (parts.length > 1 ? parts[0][0] + parts[1][0] : n.slice(0, 2)).toUpperCase();
};
const PHASE_LABEL = { BIDDING: 'Auction', TRUMP_SELECTION: 'Choosing trump', SINGLE_HAND: 'Single Hand?', DOUBLING: 'Doubling', PLAYING: 'Play', ROUND_OVER: 'Round over', GAME_OVER: 'Match over' };
function actorOf(st) {
  if (!st || st.deal_abandoned) return null;
  switch (st.phase) {
    case 'BIDDING': return st.current_player;
    case 'TRUMP_SELECTION': return st.highest_bidder;
    case 'SINGLE_HAND': return st.single_hand_turn;
    case 'DOUBLING': return st.doubling_decision_player;
    case 'PLAYING': return st.pending_trick_pause ? null : st.current_player;
    default: return null;
  }
}
function centerBox(el) {
  const r = el.getBoundingClientRect();
  const w = el.offsetWidth || r.width, h = el.offsetHeight || r.height;
  return { cx: r.left + r.width / 2, cy: r.top + r.height / 2, w, h };
}

// ------------------------------------------------------------------ flight engine
function fly({ html, back = false, from, to, toW, rotFrom = 0, rotTo = 0, duration = 450, delay = 0, fade = false, endScale = 1 }) {
  return new Promise((resolve) => {
    const w = toW || to.w;
    const wrap = document.createElement('div');
    wrap.style.cssText = `position:absolute;left:0;top:0;width:${w}px;height:${w * 1.4}px;transform-origin:50% 50%;`;
    wrap.innerHTML = back ? cardBack() : html;
    const inner = wrap.firstElementChild; inner.style.setProperty('--cw', w + 'px');
    $('#flight-layer').appendChild(wrap);
    const s0 = from.w ? from.w / w : 1;
    const fx = from.cx - w / 2, fy = from.cy - (w * 1.4) / 2;
    const tx = to.cx - w / 2, ty = to.cy - (w * 1.4) / 2;
    const d = duration * pace();
    const kf = [
      { transform: `translate(${fx}px,${fy}px) rotate(${rotFrom}deg) scale(${s0})`, opacity: 1 },
      { transform: `translate(${(fx + tx) / 2}px,${Math.min(fy, ty) - 30}px) rotate(${(rotFrom + rotTo) / 2 + 6}deg) scale(${(s0 + endScale) / 2 + 0.08})`, opacity: 1, offset: 0.5 },
      { transform: `translate(${tx}px,${ty}px) rotate(${rotTo}deg) scale(${endScale})`, opacity: fade ? 0 : 1 },
    ];
    const anim = wrap.animate(kf, { duration: d, delay, easing: 'cubic-bezier(.22,.8,.25,1)', fill: 'forwards' });
    if (back && html) {
      setTimeout(() => {
        const a1 = inner.animate([{ transform: 'scaleX(1)' }, { transform: 'scaleX(0)' }], { duration: d * 0.22, fill: 'forwards' });
        a1.onfinish = () => { wrap.innerHTML = html; const n = wrap.firstElementChild; n.style.setProperty('--cw', w + 'px'); n.animate([{ transform: 'scaleX(0)' }, { transform: 'scaleX(1)' }], { duration: d * 0.22 }); };
      }, delay + d * 0.3);
    }
    anim.onfinish = () => { wrap.remove(); resolve(); };
  });
}

// ------------------------------------------------------------------ static rendering
function renderAll(st) {
  renderHUD(st);
  renderSeats(st);
  renderBubbles(st, false);
  renderRibbons(st);
  renderPlaque(st);
  renderHand(st);
  renderDock(st);
  renderInsight(st);
  renderLog(st);
  renderSpectator(st);
}

function renderHUD(st) {
  $('#hud-round').textContent = `Round ${st.round_number}`;
  const cv = $('#hud-contract-value'), cs = $('#hud-contract-sub');
  if (st.single_hand) {
    cv.textContent = 'SINGLE'; cs.textContent = `${nameOf(st.single_hand_declarer)} alone`;
  } else if (st.highest_bidder == null) {
    cv.textContent = st.phase === 'BIDDING' ? (st.min_next_bid || 16) + '+' : '—'; cs.textContent = 'Auction open';
  } else {
    cv.textContent = st.target_bid !== st.bid ? `${st.target_bid}` : `${st.bid}`;
    const mult = st.contract_multiplier > 1 ? ` · ×${st.contract_multiplier}` : '';
    const adj = st.target_bid !== st.bid ? ` · bid ${st.bid}` : '';
    cs.textContent = `${nameOf(st.highest_bidder)}${adj}${mult}`;
  }
  const em = $('#hud-trump-emblem'), ts = $('#hud-trump-sub');
  em.classList.remove('red', 'black');
  if (st.single_hand && !st.trump_suit) { em.textContent = 'NT'; ts.textContent = 'No trump'; }
  else if (st.trump_suit) {
    em.textContent = st.trump_symbol; em.classList.add(RED[st.trump_suit] ? 'red' : 'black');
    ts.textContent = st.trump_revealed ? st.trump_suit : `${st.trump_suit} (secret)`;
  } else if (st.trump_hidden) { em.textContent = '?'; ts.textContent = st.is_seventh_card_trump ? '7th card' : 'Hidden'; }
  else { em.textContent = '—'; ts.textContent = 'Not chosen'; }
  $('#hud-trick').textContent = `${st.completed_tricks_count}/8`;
  $('#hud-phase').textContent = PHASE_LABEL[st.phase] || st.phase;

  const [a, b] = st.game_points; const tgt = st.match_target || 6;
  const ea = $('#mp-a'), eb = $('#mp-b');
  if (G.prevGP && (G.prevGP[0] !== a)) { ea.classList.remove('bump'); void ea.offsetWidth; ea.classList.add('bump'); }
  if (G.prevGP && (G.prevGP[1] !== b)) { eb.classList.remove('bump'); void eb.offsetWidth; eb.classList.add('bump'); }
  G.prevGP = [a, b];
  ea.textContent = a > 0 ? '+' + a : a; eb.textContent = b > 0 ? '+' + b : b;
  const human = st.mode === 'human';
  $('#lbl-a').textContent = human ? 'Us' : 'Team A';
  $('#lbl-b').textContent = human ? 'Them' : 'Team B';
  $('#hud-mult').textContent = st.contract_multiplier > 1 ? `Stakes ×${st.contract_multiplier}` : `First to ±${tgt}`;
}

function fanHTML(n, pos) {
  // A small fan of card backs behind the avatar, like a real player holding cards.
  const shown = Math.min(n, 6);
  if (!shown) return '<div class="fan"></div>';
  const base = { top: 0, left: -90, right: 90 }[pos] || 0;   // fan points away from the table
  const spread = 13;
  return `<div class="fan">${Array.from({ length: shown }, (_, i) => {
    const a = base + (i - (shown - 1) / 2) * spread;
    return `<div class="card back" style="transform: translate(-50%, -50%) rotate(${a}deg) translateY(-34px)"><img src="cards/back.svg" alt="" draggable="false"></div>`;
  }).join('')}</div>`;
}
function seatHTML(st, seat) {
  const p = st.players[seat];
  const pos = posOf(seat);
  const persona = p.is_human ? 'HUMAN' : p.personality;
  const initials = initialsOf(p.name);
  const isDealer = st.dealer === seat;
  const team = teamOf(seat) === 0 ? 'a' : 'b';
  const declarer = st.single_hand ? st.single_hand_declarer === seat : (st.highest_bidder === seat && st.phase !== 'BIDDING');
  let status = '';
  if (st.sitting_out === seat) status = 'Sitting out';
  else if (declarer) status = '<b>Declarer</b>';
  const inPlay = st.phase === 'PLAYING' || st.phase === 'ROUND_OVER';
  const badge = inPlay ? (st.tricks_won ? st.tricks_won[seat] : 0) : st.card_counts[seat];
  const badgeTitle = inPlay ? 'Tricks won' : 'Cards in hand';
  const fan = pos === 'bottom' || st.all_hands ? '' : fanHTML(st.card_counts[seat], pos);
  const open = pos !== 'bottom' && st.all_hands && st.all_hands[seat] ? `<div class="open-hand">${st.all_hands[seat].map((c) => cardFace(c)).join('')}</div>` : '';
  const avatar = `<div class="seat-fig">${fan}<div class="avatar team-${team}"><span class="ring"></span>${esc(initials)}
      <span class="persona-dot ${persona}">${svg(PERSONA_ICON[persona])}</span>${isDealer ? '<span class="dealer-badge" title="Dealer">D</span>' : ''}</div></div>`;
  const info = `<div class="seat-info"><div class="nameplate"><span class="np-name">${esc(p.name)}</span><span class="np-badge team-${team}" title="${badgeTitle}">${badge}</span></div>
      <div class="np-sub"><span class="persona-chip ${persona}">${svg(PERSONA_ICON[persona])}${PERSONA_LABEL[persona] || ''}</span>
      <span class="seat-status"><span class="thinking"><i></i><i></i><i></i></span> ${status}</span></div></div>`;
  return avatar + info + open + '<div class="bubble-host"></div>';
}
function renderSeats(st) {
  const actor = actorOf(st);
  for (let seat = 0; seat < 4; seat++) {
    const el = seatEl(seat);
    const html = seatHTML(st, seat);
    if (G.seatKeys[seat] !== html) { const bubble = $('.bubble-host', el); const keep = bubble ? bubble.innerHTML : ''; el.innerHTML = html; const nb = $('.bubble-host', el); if (nb) nb.innerHTML = keep; G.seatKeys[seat] = html; }
    el.classList.toggle('active', actor === seat);
    el.classList.toggle('sitting-out', st.sitting_out === seat);
  }
}
function bubbleFor(st, seat) {
  if (st.phase !== 'BIDDING' && st.phase !== 'TRUMP_SELECTION') return null;
  const v = st.player_bids ? st.player_bids[seat] : '';
  if (!v) return null;
  if (v === 'PASS') return { text: 'Pass', cls: 'pass' };
  if (v === 'SINGLE') return { text: 'Single!', cls: 'single' };
  return { text: v.replace('*', ''), cls: '' };
}
function renderBubbles(st, popSeat) {
  for (let seat = 0; seat < 4; seat++) {
    const host = $('.bubble-host', seatEl(seat)); if (!host) continue;
    const b = bubbleFor(st, seat);
    const key = b ? b.text + b.cls : '';
    if (host.dataset.k === key && popSeat !== seat) continue;
    host.dataset.k = key;
    host.innerHTML = b ? `<div class="bid-bubble ${b.cls} ${popSeat === seat ? 'pop' : ''}">${esc(b.text)}</div>` : '';
  }
}

function renderRibbons(st) {
  const [a, b] = st.round_points; countUp($('#pts-a'), a); countUp($('#pts-b'), b);
  const total = st.game_variant === '29' ? 29 : 28;
  $('#bar-a').style.width = `${(a / total) * 100}%`; $('#bar-b').style.width = `${(b / total) * 100}%`;
  ['a', 'b'].forEach((t, i) => {
    const em = $('#tgt-' + t); const rb = $('#ribbon-' + t);
    const isBidder = st.highest_bidder != null && teamOf(st.single_hand ? st.single_hand_declarer : st.highest_bidder) === i && st.phase !== 'BIDDING';
    rb.classList.toggle('bidding-team', isBidder);
    if (isBidder && !st.single_hand && st.target_bid) { em.style.display = 'block'; em.style.left = `${(st.target_bid / total) * 100}%`; }
    else em.style.display = 'none';
  });
}

function renderPlaque(st) {
  const pl = $('#trump-plaque');
  const relevant = ['DOUBLING', 'SINGLE_HAND', 'PLAYING', 'ROUND_OVER'].includes(st.phase) && st.highest_bidder != null;
  if (!relevant || (st.single_hand && !st.trump_suit)) {
    if (relevant && st.single_hand) {
      pl.classList.remove('hidden'); pl.classList.add('revealed');
      $('#tp-card').innerHTML = '<div class="tp-emblem black">✦</div>'; $('#tp-title').textContent = 'Single Hand'; $('#tp-sub').textContent = 'No trump';
    } else pl.classList.add('hidden');
    return;
  }
  pl.classList.remove('hidden');
  pl.classList.toggle('revealed', !!st.trump_revealed);
  const bidderName = nameOf(st.highest_bidder);
  if (st.trump_revealed && st.trump_suit) {
    $('#tp-card').innerHTML = `<div class="tp-emblem ${RED[st.trump_suit] ? 'red' : 'black'}">${st.trump_symbol}</div>`;
    $('#tp-title').textContent = `Trump · ${st.trump_suit}`; $('#tp-sub').textContent = st.single_hand ? 'Named openly' : 'Revealed';
  } else if (st.trump_suit) {
    $('#tp-card').innerHTML = st.seventh_card ? cardFace(st.seventh_card) : `<div class="tp-emblem ${RED[st.trump_suit] ? 'red' : 'black'}">${st.trump_symbol}</div>`;
    $('#tp-title').textContent = st.mode === 'ai' ? `${bidderName}'s secret trump` : 'Your secret trump';
    $('#tp-sub').textContent = st.is_seventh_card_trump ? '7th card · face down' : (st.mode === 'ai' ? 'Hidden from the table' : 'Only you know it');
  } else {
    $('#tp-card').innerHTML = cardBack();
    $('#tp-title').textContent = 'Secret trump'; $('#tp-sub').textContent = `${st.is_seventh_card_trump ? '7th card · ' : ''}set by ${bidderName}`;
  }
}

function fanVars(i, n) {
  const mid = (n - 1) / 2; const step = Math.min(5, 36 / Math.max(1, n));
  return `--r:${((i - mid) * step).toFixed(2)}deg;--y:${(Math.pow(i - mid, 2) * 1.6).toFixed(1)}px`;
}
function syncPanels() {
  const ins = $('#insight-panel').classList.contains('open');
  const log = $('#log-panel').classList.contains('open');
  $('#btn-insight').classList.toggle('active', ins);
  $('#btn-log').classList.toggle('active', log);
  $('#screen-game').classList.toggle('panel-open', ins || log);
}
function renderHand(st, opts = {}) {
  const hand = $('#hand');
  const humanMode = st.mode === 'human';
  let cards = []; let interactive = false; let legal = new Set(st.legal_cards || []);
  if (humanMode) { cards = st.hand; interactive = st.is_human_turn && st.phase === 'PLAYING'; }
  else if (st.all_hands) cards = st.all_hands[0];
  const backs = !humanMode && !st.all_hands ? st.card_counts[0] : 0;
  const trumpSuit = st.trump_suit;
  const key = JSON.stringify([cards.map((c) => c.code), [...legal], interactive, backs, trumpSuit, st.trump_revealed, st.sitting_out === G.viewer, G.dealing]);
  if (G.handKey === key && !opts.force) return;
  G.handKey = key;
  hand.classList.toggle('my-turn', interactive);
  hand.classList.toggle('dealing', !!G.dealing);
  const n = cards.length || backs;
  let html = '';
  if (cards.length) {
    html = cards.map((c, i) => {
      const cls = ['hand-card'];
      if (interactive) cls.push(legal.has(c.code) ? 'legal' : 'illegal');
      if (opts.dealIn) cls.push('deal-in');
      if (trumpSuit && c.suit === trumpSuit && humanMode) cls.push('trump-mark');
      const delay = opts.dealIn ? `animation-delay:${i * 45}ms;` : '';
      return `<div class="${cls.join(' ')}" style="${fanVars(i, n)};${delay}" data-code="${c.code}">${cardFace(c)}</div>`;
    }).join('');
  } else if (backs) {
    html = Array.from({ length: backs }, (_, i) => `<div class="hand-card ${opts.dealIn ? 'deal-in' : ''}" style="${fanVars(i, n)};${opts.dealIn ? `animation-delay:${i * 45}ms` : ''}">${cardBack()}</div>`).join('');
  }
  hand.innerHTML = html;
  hand.style.opacity = st.sitting_out === G.viewer ? '0.4' : '1';
  if (interactive) $$('.hand-card.legal', hand).forEach((el) => el.addEventListener('click', () => onPlayCard(el)));
}

// ------------------------------------------------------------------ action dock
function bidHistoryHTML(st) {
  const hist = st.bidding_history || [];
  if (!hist.length) return '';
  return `<div class="bid-history">${hist.map((h, i) => {
    const pass = h.bid === 'PASS'; const single = h.bid === 'SINGLE';
    return `<span class="bh team-${teamOf(h.player) === 0 ? 'a' : 'b'} ${pass ? 'pass' : ''} ${i === hist.length - 1 ? 'latest' : ''}">${esc(nameOf(h.player))} <b>${pass ? 'Pass' : single ? 'Single' : (h.action === 'HOLD' ? `Hold ${h.bid}` : h.bid)}</b></span>`;
  }).join('')}</div>`;
}
function statusPill(text) { return `<div class="dock-status">${text}</div>`; }
function renderDock(st) {
  const dock = $('#action-dock');
  let html = '';
  const human = st.mode === 'human';
  const actor = actorOf(st);
  const myTurn = human && st.is_human_turn;
  const thinking = actor != null && !myTurn && !isYou(actor) ? `<b>${esc(nameOf(actor))}</b> is thinking…` : '';
  if (st.deal_abandoned || st.phase === 'ROUND_OVER' || st.phase === 'GAME_OVER') html = '';
  else if (st.phase === 'BIDDING') {
    const duel = st.auction_holder != null && st.auction_challenger != null
      ? `Duel: <b>${esc(nameOf(st.auction_holder))}</b> (holds) vs <b>${esc(nameOf(st.auction_challenger))}</b>` : '';
    if (myTurn) {
      const lo = st.min_next_bid, hi = st.max_bid || 28;
      const buttons = [];
      for (let b = lo; b <= hi; b++) {
        const hold = st.can_hold && b === st.bid;
        buttons.push(`<button class="bid-btn ${hold ? 'hold' : ''}" data-bid="${b}">${hold ? `Hold ${b}` : b}</button>`);
      }
      let title, sub;
      if (st.highest_bidder == null) { title = 'Open the bidding'; sub = `Bid ${lo} or more, or pass. Passing is final.`; }
      else if (st.can_hold) { title = 'You hold the bid'; sub = `${esc(nameOf(st.highest_bidder))} bid <b>${st.bid}</b>. Hold at ${st.bid} — you never need to go higher — or pass.`; }
      else { title = 'Your challenge'; sub = `${esc(nameOf(st.highest_bidder))} holds at <b>${st.bid}</b>. Bid higher than ${st.bid} or pass. Passing is final.`; }
      html = `<div class="dock-panel"><div class="dock-title">${title}</div><div class="dock-sub">${sub}</div>
        <div class="bid-grid">${buttons.join('') || '<span class="dock-sub">No higher bid is possible.</span>'}</div>
        <div class="dock-row">
          <button class="btn-lux small ghost" data-act="pass">Pass</button>
          ${st.can_call_single_hand ? '<button class="btn-lux small danger" data-act="single">Single Hand</button>' : ''}
        </div>${bidHistoryHTML(st)}</div>`;
    } else html = `${statusPill([duel, thinking].filter(Boolean).join(' · ') || 'Auction in progress')}${bidHistoryHTML(st) ? `<div class="dock-panel">${bidHistoryHTML(st)}</div>` : ''}`;
  } else if (st.phase === 'TRUMP_SELECTION') {
    html = statusPill(myTurn ? 'Choose your trump…' : `<b>${esc(nameOf(st.highest_bidder))}</b> is choosing ${st.single_hand ? 'an open' : 'a secret'} trump…`);
  } else if (st.phase === 'SINGLE_HAND') {
    if (myTurn) {
      const r = st.rules.single_hand;
      html = `<div class="dock-panel"><div class="dock-title">Call Single Hand?</div>
        <div class="dock-sub">Win condition: ${esc(r.win_condition_text)}. ${r.partner_sits_out ? 'Your partner sits out.' : 'Your partner keeps playing.'} ${r.trump === 'none' ? 'No trump.' : 'You name trump openly.'} +${r.win_points} / −${r.loss_points} match points.</div>
        <div class="dock-row"><button class="btn-lux small danger" data-act="single-yes">Call Single Hand</button><button class="btn-lux small primary" data-act="single-no">No, continue</button></div></div>`;
    } else html = statusPill(`Single Hand? <b>${esc(nameOf(st.single_hand_turn))}</b> is deciding…`);
  } else if (st.phase === 'DOUBLING') {
    if (myTurn && st.can_human_double) {
      html = `<div class="dock-panel"><div class="dock-title">Double the contract?</div><div class="dock-sub">${esc(nameOf(st.highest_bidder))} must make ${st.target_bid}. Doubling makes the result worth ×2.</div>
        <div class="dock-row"><button class="btn-lux small danger" data-act="double">Double ×2</button><button class="btn-lux small primary" data-act="no-double">No double</button></div></div>`;
    } else if (myTurn && st.can_human_redouble) {
      html = `<div class="dock-panel"><div class="dock-title">Redouble?</div><div class="dock-sub">The defenders doubled. Redouble to play for ×4.</div>
        <div class="dock-row"><button class="btn-lux small danger" data-act="redouble">Redouble ×4</button><button class="btn-lux small primary" data-act="no-redouble">Play at ×2</button></div></div>`;
    } else html = statusPill(thinking || 'Doubling…');
  } else if (st.phase === 'PLAYING') {
    if (st.pending_trick_pause) html = '';
    else if (human && st.sitting_out === st.human_seat) html = statusPill('You are sitting out this Single Hand — watch your partner.');
    else if (myTurn) {
      const extra = [];
      if (st.can_reveal_trump) extra.push('<button class="btn-lux small danger" data-act="reveal">Call for Trump</button>');
      if (st.can_declare_pair) extra.push('<button class="btn-lux small primary" data-act="pair">Announce Marriage</button>');
      html = `${statusPill('<b>Your turn</b> — play a highlighted card')}<div class="dock-row">${extra.join('')}</div>`;
    } else html = statusPill(thinking || '…');
  }
  if (html === G.dockKey) return;
  G.dockKey = html;
  dock.innerHTML = html;
  $$('[data-bid]', dock).forEach((b) => b.addEventListener('click', () => humanAction('bid', { bid_value: +b.dataset.bid })));
  $$('[data-act]', dock).forEach((b) => b.addEventListener('click', () => {
    const a = b.dataset.act;
    const map = {
      pass: ['pass'], single: ['single_hand'], 'single-yes': ['single_hand_decision', { declare: true }], 'single-no': ['single_hand_decision', { declare: false }],
      double: ['double', { double: true }], 'no-double': ['double', { double: false }], redouble: ['redouble', { redouble: true }], 'no-redouble': ['redouble', { redouble: false }],
      reveal: ['reveal_trump'], pair: ['declare_pair'],
    };
    if (map[a]) humanAction(...map[a]);
  }));
}

// ------------------------------------------------------------------ insight & log panels
function bars(obj, max = 100) {
  return Object.entries(obj || {}).map(([k, v]) => `<span class="lbl">${esc(k.replace(/_/g, ' '))}</span><span class="bar"><i style="width:${clamp((v / max) * 100, 0, 100)}%"></i></span><span class="val">${Math.round(v)}</span>`).join('');
}
function decisionHTML(d) {
  const det = d.details || {};
  const kv = [];
  const add = (k, v, f = (x) => x) => { if (v !== undefined && v !== null) kv.push(`<span>${k} <b>${esc(f(v))}</b></span>`); };
  add('simulations', det.simulations);
  add('time', det.elapsed, (x) => x + 's');
  add('minimax nodes', det.minimax_nodes);
  add('hand strength', det.hand_strength);
  add('risk', det.risk, (x) => Math.round(x));
  add('P(make)', det.success_probability, (x) => Math.round(x * 100) + '%');
  add('probability bar', det.probability_bar, (x) => Math.round(x * 100) + '%');
  add('ceiling', det.ceiling);
  add('best trump', det.best_trump);
  add('P(single hand)', det.single_hand_probability, (x) => Math.round(x * 100) + '%');
  add('P(contract fails)', det.p_contract_fails, (x) => Math.round(x * 100) + '%');
  add('P(contract makes)', det.p_contract_makes, (x) => Math.round(x * 100) + '%');
  add('P(holding trump)', det.p_holding_trump, (x) => Math.round(x * 100) + '%');
  add('selected', det.selected);
  let adv = kv.length ? `<div class="adv-kv">${kv.join('')}</div>` : '';
  if (det.proof) adv += `<div class="adv-h">Propositional proof</div><ul class="adv-rules"><li>${esc(det.proof)}</li></ul>`;
  if (det.fuzzy_inputs) adv += `<div class="adv-h">Fuzzy inputs</div><div class="adv-grid">${bars(det.fuzzy_inputs)}</div>`;
  if (det.fuzzy_outputs) adv += `<div class="adv-h">Fuzzy outputs</div><div class="adv-grid">${bars(det.fuzzy_outputs)}</div>`;
  if (det.fuzzy_rules && det.fuzzy_rules.length) adv += `<div class="adv-h">Strongest rules</div><ul class="adv-rules">${det.fuzzy_rules.map((r) => `<li>${esc(r)}</li>`).join('')}</ul>`;
  if (det.candidates && det.candidates.length) {
    const mm = det.candidates[0].minimax !== undefined;
    adv += `<div class="adv-h">Candidate moves</div><table class="cand-table"><tr><th>Card</th>${mm ? '<th>Minimax</th>' : '<th>Visits</th><th>ISMCTS</th>'}<th>Fuzzy</th><th>Score</th></tr>${det.candidates.map((c) => {
      const red = /[♥♦]/.test(c.card) ? 'redc' : '';
      return `<tr class="${c.card === det.selected ? 'sel' : ''}"><td class="${red}">${esc(c.card)}</td>${mm ? `<td>${c.minimax}</td>` : `<td>${c.visits}</td><td>${c.mcts}</td>`}<td>${c.fuzzy}</td><td>${c.score}</td></tr>`;
    }).join('')}</table>`;
  }
  if (d.private_hidden) adv += '<div class="adv-hidden">Private evaluation (hand strength, fuzzy inputs, candidate cards) is hidden in Human vs AI to keep the game fair.</div>';
  const persona = d.personality || 'STRATEGIC';
  return `<div class="dec ${persona}" data-seq="${d.seq}">
    <div class="dec-top"><span class="persona-chip ${persona}">${svg(PERSONA_ICON[persona])}${PERSONA_LABEL[persona]}</span><span class="dec-who">${esc(d.name)}</span><span class="dec-action">${esc(d.action)}</span></div>
    <div class="dec-sum">${esc(d.summary)}</div>
    <span class="dec-algo">${esc(d.algorithm)} · R${d.round} T${d.trick}</span>
    <div class="dec-adv">${adv || '<div class="adv-hidden">No additional data.</div>'}</div></div>`;
}
function renderInsight(st) {
  const feed = $('#insight-feed');
  $('#insight-note').textContent = st.mode === 'human' ? 'In Human vs AI, opponents\' private evaluations are hidden. Switch on Advanced to see search statistics.' : 'Spectator mode: full AI evaluations are shown.';
  const decs = (st.decisions || []).filter((d) => d.seq > G.insightSeq);
  if (!decs.length) return;
  decs.forEach((d) => { feed.insertAdjacentHTML('afterbegin', decisionHTML(d)); G.insightSeq = Math.max(G.insightSeq, d.seq); });
  while (feed.children.length > 60) feed.lastElementChild.remove();
}
function renderLog(st) {
  const feed = $('#log-feed');
  (st.recent_events || []).filter((e) => e.id > G.logSeen).forEach((e) => {
    if (G.logRound !== e.round) { feed.insertAdjacentHTML('afterbegin', `<div class="log-sep">— Round ${e.round} begins —</div>`); G.logRound = e.round; }
    feed.insertAdjacentHTML('afterbegin', `<div class="log-row ${e.type}"><i></i><span>${esc(e.text)}</span></div>`);
    G.logSeen = Math.max(G.logSeen, e.id);
  });
  while (feed.children.length > 160) feed.lastElementChild.remove();
  $('#match-history').innerHTML = (st.round_history || []).map((r) => `<span class="mh ${r.fulfilled ? 'made' : 'failed'}">R${r.round} ${r.single_hand ? 'Single' : r.target} ${r.fulfilled ? '✓' : '✗'} ${r.delta[0] ? (r.delta[0] > 0 ? 'A+' : 'A') + r.delta[0] : (r.delta[1] > 0 ? 'B+' : 'B') + r.delta[1]}</span>`).join('');
}
function renderSpectator(st) {
  const bar = $('#spectator-bar');
  bar.classList.toggle('hidden', st.mode !== 'ai');
  $('#sp-play').innerHTML = svg(G.paused ? 'play' : 'pause');
  $$('#sp-speed button').forEach((b) => b.classList.toggle('active', b.dataset.speed === G.spSpeed));
}

// ------------------------------------------------------------------ animations
function sourceBox(seat, code) {
  const el = seatEl(seat);
  if (code) { const c = $(`.open-hand [data-code="${code}"]`, el); if (c && c.offsetWidth) return centerBox(c); }
  const fan = $('.fan .card', el); if (fan) { const av = centerBox($('.avatar', el)); return { cx: av.cx, cy: av.cy, w: 40 }; }
  const av = $('.avatar', el); if (av) return Object.assign(centerBox(av), { w: 30 });
  return centerBox(el);
}
function handCardWidth() {
  const slot = $('.trick-slot');
  return slot && slot.offsetWidth ? slot.offsetWidth / 0.9 : 70;
}
function targetBoxForDeal(seat) {
  if (posOf(seat) === 'bottom') {
    const h = $('#hand'); const r = h.getBoundingClientRect();
    return { cx: r.left + r.width / 2, cy: r.bottom - handCardWidth() * 0.75, w: handCardWidth() };
  }
  return sourceBox(seat);
}
async function animateDeal(st, stage) {
  G.dealing = true; G.handKey = '';
  $('#table-area').classList.add('dealing');
  renderHand(st);
  const deck = $('#deck-stack'); deck.innerHTML = cardBack() + cardBack() + cardBack(); deck.classList.add('show');
  $$('.card', deck).forEach((c, i) => { c.style.transform = `translate(calc(-50% + ${i * 1.5}px), calc(-50% - ${i * 1.5}px))`; });
  const from = centerBox(deck.firstElementChild);
  const order = [1, 2, 3, 4].map((k) => (st.dealer + k) % 4);
  const flights = [];
  const stagger = 55 * pace();
  for (let r = 0; r < 4; r++) {
    for (const seat of order) {
      const to = targetBoxForDeal(seat);
      const toTable = stage === 2 && r === 2 && st.is_seventh_card_trump && seat === st.highest_bidder;
      const dest = toTable ? centerBox($('#trump-plaque').classList.contains('hidden') ? $('#felt') : $('#tp-card')) : to;
      flights.push(fly({ back: true, from: { cx: from.cx, cy: from.cy, w: from.w }, to: dest, toW: Math.min(to.w || 40, 60), rotFrom: 0, rotTo: (Math.random() - 0.5) * 24, duration: 380, fade: !toTable, endScale: toTable ? 0.6 : 0.9 }));
      Sfx.play('flick');
      await sleep(stagger);
    }
  }
  await Promise.all(flights);
  deck.classList.remove('show');
  $('#table-area').classList.remove('dealing');
  G.dealing = false; G.handKey = '';
  renderSeats(st);
  renderHand(st, { dealIn: true, force: true });
}

// Second-person grammar only when the human kept the name "You".
const isYou = (seat) => G.st && G.st.mode === 'human' && seat === G.st.human_seat && nameOf(seat) === 'You';
const verb = (seat, third, second) => `${esc(nameOf(seat))} ${isYou(seat) ? second : third}`;
async function animateBid(st, h) {
  const seat = h.player;
  renderBubbles(st, seat);
  const name = esc(nameOf(seat));
  if (h.bid === 'PASS') { centerCall(`Pass<small>${name}</small>`, 'pass'); Sfx.play('pass'); }
  else if (h.bid === 'SINGLE') { centerCall(`Single Hand!<small>${name}</small>`, 'single'); Sfx.play('single'); }
  else {
    const what = h.action === 'OPEN' ? verb(seat, 'opens', 'open') : h.action === 'FORCED' ? verb(seat, 'is forced', 'are forced')
      : h.action === 'HOLD' ? verb(seat, 'holds', 'hold') : verb(seat, 'bids', 'bid');
    centerCall(`${h.bid}<small>${what}</small>`); Sfx.play('chip');
  }
  await sleep(650 * pace());
}

async function animatePlay(st, pc) {
  const seat = pc.player_id; const slot = slotEl(seat);
  const to = centerBox(slot);
  let from = null;
  if (posOf(seat) === 'bottom' && G.pendingFrom) from = G.pendingFrom;
  else if (posOf(seat) === 'bottom') { const el = $(`#hand [data-code="${pc.card.code}"]`); from = el ? centerBox(el) : centerBox($('#hand')); }
  else from = sourceBox(seat, pc.card.code);
  G.pendingFrom = null;
  const rot = { bottom: -3, top: 4, left: -9, right: 8 }[posOf(seat)];
  const openSource = posOf(seat) === 'bottom' ? (st.mode === 'human' || !!st.all_hands) : !!st.all_hands;
  slot.innerHTML = '';
  await fly({ html: cardFace(pc.card), back: !openSource, from, to, rotFrom: rot * 3, rotTo: rot, duration: 460 });
  slot.innerHTML = cardFace(pc.card) + (pc.is_trump ? '<span class="trump-tag">TRUMP</span>' : '');
  Sfx.play('place');
}

function renderTrickStatic(st) {
  const shown = {};
  if (st.current_trick) st.current_trick.cards.forEach((pc) => { shown[posOf(pc.player_id)] = pc; });
  $$('.trick-slot').forEach((slot) => {
    const pc = shown[slot.dataset.pos];
    const code = pc ? pc.card.code : '';
    if (slot.dataset.code === code) return;
    slot.dataset.code = code;
    slot.innerHTML = pc ? cardFace(pc.card) + (pc.is_trump ? '<span class="trump-tag">TRUMP</span>' : '') : '';
  });
}

async function collectTrick(st) {
  const lt = st.last_completed_trick; if (!lt) return;
  const winner = lt.winner;
  const wslot = slotEl(winner);
  const wc = $('.card', wslot); if (wc) wc.classList.add('winner');
  centerCall(`+${lt.points}<small>${verb(winner, 'wins', 'win')} the trick</small>`, 'trick', true);
  await sleep((st.mode === 'ai' ? { relaxed: 1500, normal: 1050, fast: 480 }[G.spSpeed] : 1150) * (S.reduced ? 0.5 : 1));
  const to = centerBox($('.avatar', seatEl(winner)));
  const flights = $$('.trick-slot').map((slot) => {
    const c = $('.card', slot); if (!c) return null;
    const from = centerBox(slot); slot.innerHTML = ''; slot.dataset.code = '';
    return fly({ html: c.outerHTML.replace(' winner', ''), from, to, toW: from.w, rotFrom: 0, rotTo: (Math.random() - 0.5) * 60, duration: 520, fade: true, endScale: 0.35 });
  }).filter(Boolean);
  Sfx.play('collect');
  await Promise.all(flights);
  const rb = centerBox($(teamOf(winner) === 0 ? '#ribbon-a' : '#ribbon-b'));
  if (lt.points) floatPoints(`+${lt.points}`, rb.cx, rb.cy - 30);
}

async function cinematicReveal(st) {
  const ov = $('#ov-reveal'); const rc = $('#reveal-card');
  const red = RED[st.trump_suit];
  if (st.is_seventh_card_trump && st.seventh_card) rc.innerHTML = `<div class="flipper">${cardBack()}${cardFace(st.seventh_card)}</div>`;
  else rc.innerHTML = `<div class="big-glyph ${red ? 'red' : 'black'}">${st.trump_symbol}</div>`;
  $('#reveal-kicker').textContent = st.single_hand ? 'Single Hand trump' : 'Trump revealed';
  $('#reveal-suit').textContent = `${st.trump_suit}`;
  const ev = [...(st.recent_events || [])].reverse().find((e) => e.type === 'trump');
  $('#reveal-sub').textContent = ev ? ev.text : '';
  ov.classList.add('open'); Sfx.play('reveal');
  await sleep(350); const b = centerBox(rc); FX.burst(b.cx, b.cy, 70);
  await sleep(2100 * pace());
  ov.classList.remove('open');
  const em = $('#hud-trump-emblem'); em.classList.remove('pulse'); void em.offsetWidth; em.classList.add('pulse');
}

// ------------------------------------------------------------------ overlays
function openOverlay(id) { $(id).classList.add('open'); hydrateIcons($(id)); }
function closeOverlay(id) { $(id).classList.remove('open'); }
const isOpen = (id) => $(id).classList.contains('open');

function showTrumpPicker(st) {
  if (isOpen('#ov-trump')) return;
  const hand = st.hand || [];
  const single = st.single_hand;
  $('#trump-kicker').textContent = single ? 'Single Hand' : `You won the auction at ${st.bid}`;
  $('#trump-title').textContent = single ? 'Name the open trump' : 'Choose your secret trump';
  $('#trump-help').textContent = single ? 'Your trump is announced to everyone.' : 'Only you will know it until a player who cannot follow suit calls for the trump. You must hold a point card (J, 9, A, 10) of your trump.';
  const suits = ['Spades', 'Hearts', 'Clubs', 'Diamonds'];
  const score = (s) => { const cs = hand.filter((c) => c.suit === s); const pts = cs.reduce((a, c) => a + c.points, 0); return { n: cs.length, pts, has: cs.some((c) => c.points > 0) }; };
  let tiles = suits.map((s) => {
    const sc = score(s);
    return `<button class="suit-tile ${RED[s] ? 'red' : 'black'}" data-opt="${s.toUpperCase()}">
      <span class="glyph">${SUIT_SYM[s]}</span><b>${s}</b><small>${sc.n} card${sc.n === 1 ? '' : 's'} · ${sc.pts} pt${sc.pts === 1 ? '' : 's'}</small>
      ${!sc.has && !single ? '<span class="warn">No point card — deal would be void</span>' : ''}</button>`;
  }).join('');
  if (!single && st.rules.allow_seventh_card) tiles += `<button class="suit-tile seventh" data-opt="SEVENTH_CARD"><span class="glyph">7th</span><b>7th Card</b><small>Your concealed 7th card decides</small></button>`;
  $('#suit-choices').innerHTML = tiles;
  $('#suit-choices').style.gridTemplateColumns = `repeat(${!single && st.rules.allow_seventh_card ? 5 : 4}, 1fr)`;
  $('#trump-mini-hand').innerHTML = hand.map((c) => cardFace(c)).join('');
  $$('.suit-tile', $('#suit-choices')).forEach((t) => t.addEventListener('click', async () => {
    t.classList.add('chosen'); Sfx.play('chip');
    await sleep(380);
    closeOverlay('#ov-trump');
    humanAction('select_trump', { option: t.dataset.opt });
  }));
  openOverlay('#ov-trump');
}

function waitClick(btn, autoMs, noteEl) {
  return new Promise((resolve) => {
    let done = false; let timer = null; let iv = null;
    const finish = () => { if (done) return; done = true; clearTimeout(timer); clearInterval(iv); btn.removeEventListener('click', finish); if (noteEl) noteEl.textContent = ''; resolve(); };
    btn.addEventListener('click', finish);
    if (autoMs) {
      let left = Math.ceil(autoMs / 1000);
      if (noteEl) noteEl.textContent = `Continuing in ${left}s…`;
      iv = setInterval(() => { if (G.paused) { if (noteEl) noteEl.textContent = 'Paused'; return; } left -= 1; if (noteEl) noteEl.textContent = `Continuing in ${left}s…`; if (left <= 0) finish(); }, 1000);
    }
  });
}

async function showMarriage(st) {
  const m = st.marriage_popup_info; if (!m) return;
  $('#marriage-cards').innerHTML = cardFace({ suit: m.trump_suit, rank: 'K', code: 'K' + m.trump_suit[0] }) + cardFace({ suit: m.trump_suit, rank: 'Q', code: 'Q' + m.trump_suit[0] });
  $('#marriage-text').textContent = m.message;
  $('#m-old').textContent = m.old_bid; $('#m-new').textContent = m.new_bid;
  openOverlay('#ov-marriage'); Sfx.play('chime');
  await waitClick($('#btn-marriage-ok'), st.mode === 'ai' ? 3000 : 0, null);
  closeOverlay('#ov-marriage');
  await act('dismiss_marriage_popup');
}

async function showRoundSummary(st) {
  const r = st.last_round_result; if (!r) return;
  const made = r.fulfilled;
  const banner = $('#round-banner'); banner.className = 'result-banner ' + (made ? 'made' : 'failed');
  $('#round-kicker').textContent = `Round ${r.round}`;
  $('#round-title').textContent = r.single_hand ? (made ? 'Single Hand Made!' : 'Single Hand Failed') : (made ? 'Contract Made' : 'Contract Failed');
  const trump = r.trump ? `${r.trump_symbol} ${r.trump}` : 'no trump';
  $('#round-detail').textContent = r.single_hand ? `${nameOf(r.bidder)} played alone (${trump}): ${r.detail}.`
    : `${nameOf(r.bidder)} bid ${r.bid}${r.target !== r.bid ? ` (target ${r.target})` : ''} with ${trump} trumps: ${r.detail}${r.multiplier > 1 ? ` · ×${r.multiplier}` : ''}.`;
  $('#rs-a').dataset.v = 0; $('#rs-b').dataset.v = 0; $('#rs-a').textContent = '0'; $('#rs-b').textContent = '0';
  const delta = (d, el) => { el.textContent = d ? (d > 0 ? `+${d}` : `${d}`) + ' match' : '±0'; el.className = d > 0 ? 'up' : d < 0 ? 'down' : ''; };
  delta(r.delta[0], $('#rs-a-delta')); delta(r.delta[1], $('#rs-b-delta'));
  $('#round-tricks').innerHTML = [0, 1, 2, 3].map((s) => `<div class="rtk ${st.sitting_out === s ? 'sat' : ''}"><b>${r.tricks_won[s]}</b>${esc(nameOf(s))}</div>`).join('');
  $('#rm-a').textContent = r.game_points[0]; $('#rm-b').textContent = r.game_points[1];
  openOverlay('#ov-round');
  setTimeout(() => { countUp($('#rs-a'), r.round_points[0], 900); countUp($('#rs-b'), r.round_points[1], 900); }, 250);
  const humanTeam = st.mode === 'human' ? teamOf(st.human_seat) : r.bidder_team;
  const good = st.mode === 'human' ? (r.delta[humanTeam] > 0 || r.delta[1 - humanTeam] < 0) : made;
  Sfx.play(good ? 'made' : 'failed');
  if (made && !S.reduced) FX.burst(window.innerWidth / 2, window.innerHeight * 0.3, 60);
  const isOver = st.phase === 'GAME_OVER';
  $('#btn-next-round').innerHTML = `${svg(isOver ? 'trophy' : 'play')}${isOver ? 'See Result' : 'Next Round'}`;
  await waitClick($('#btn-next-round'), st.mode === 'ai' ? 5000 : 0, $('#round-auto'));
  closeOverlay('#ov-round');
}

function showGameOver(st) {
  const w = st.match_winner;
  const human = st.mode === 'human';
  const won = human ? w === teamOf(st.human_seat) : true;
  const modal = $('.gameover-modal'); modal.classList.toggle('defeat', !won);
  $('#go-emblem').innerHTML = svg(won ? 'trophy' : 'shield');
  $('#go-kicker').textContent = 'Match complete';
  $('#go-title').textContent = human ? (won ? 'Victory' : 'Defeat') : `Team ${w === 0 ? 'A' : 'B'} Wins`;
  const names = (t) => [0, 1, 2, 3].filter((s) => teamOf(s) === t).map(nameOf).join(' & ');
  $('#go-sub').textContent = `Team ${w === 0 ? 'A' : 'B'} (${names(w)}) reached the match target.`;
  $('#go-a').textContent = st.game_points[0]; $('#go-b').textContent = st.game_points[1];
  $('#go-history').innerHTML = (st.round_history || []).map((r) => `<span class="mh ${r.fulfilled ? 'made' : 'failed'}">R${r.round} ${r.single_hand ? 'Single' : r.target} ${r.fulfilled ? '✓' : '✗'}</span>`).join('');
  openOverlay('#ov-gameover');
  Sfx.play(won ? 'win' : 'lose');
  if (won) FX.confetti(220);
}

async function showAbandon(st) {
  $('#abandon-text').textContent = st.abandon_reason || 'The deal was abandoned.';
  openOverlay('#ov-abandon');
  await waitClick($('#btn-abandon-ok'), st.mode === 'ai' ? 4000 : 0, $('#abandon-auto'));
  closeOverlay('#ov-abandon');
  await act('dismiss_abandoned_deal');
}

// ------------------------------------------------------------------ human actions
// A wake that arrives while the director is busy animating is remembered, not lost.
function wake() {
  if (G.wakeFn) { const f = G.wakeFn; G.wakeFn = null; f(); }
  else G.wakePending = true;
}
function waitWake(ms) {
  if (G.wakePending) { G.wakePending = false; return Promise.resolve(); }
  return new Promise((res) => { G.wakeFn = res; if (ms) setTimeout(() => { if (G.wakeFn === res) { G.wakeFn = null; res(); } }, ms); });
}
async function humanAction(action, extra = {}) {
  if (G.acting) return false;
  G.acting = true;
  Sfx.ensure();
  let r;
  try { r = await act(action, extra); } catch (e) { r = { success: false, message: 'Server not reachable' }; }
  G.acting = false;
  if (!r.success) { toast(r.message || 'Not allowed', 'error'); G.dockKey = ''; renderDock(G.st); G.handKey = ''; renderHand(G.st, { force: true }); return false; }
  if (action === 'select_trump' && r.message) toast(r.message);
  G.dockKey = '';
  wake();
  return true;
}
function onPlayCard(el) {
  if (!G.st || !G.st.is_human_turn || G.acting) return;
  G.pendingFrom = centerBox(el);
  el.style.visibility = 'hidden';
  humanAction('play_card', { card_code: el.dataset.code });
}

// ------------------------------------------------------------------ the director
async function sync(st) {
  const prev = G.st;
  const newMatch = !prev || prev.match_id !== st.match_id;
  if (newMatch) {
    G.insightSeq = 0; G.logSeen = -1; G.logRound = null; G.seatKeys = {}; G.handKey = ''; G.dockKey = '';
    $('#insight-feed').innerHTML = ''; $('#log-feed').innerHTML = ''; G.prevGP = null;
  }
  G.viewer = st.human_seat ?? 0;
  G.st = st;
  const newDeal = G.dealId !== null && st.deal_id !== G.dealId;
  const firstSight = G.dealId === null;
  const stage2 = !newDeal && !firstSight && G.dealStage === 1 && st.deal_stage === 2;

  if (newDeal || firstSight) { G.bidSeen = firstSight ? (st.bidding_history || []).length : 0; G.trickKey = null; G.trickSeen = 0; G.revealedKey = null; G.singleKey = null; }
  renderHUD(st); renderRibbons(st); renderPlaque(st); renderInsight(st); renderLog(st); renderSpectator(st);

  if (newDeal || (G.animateFirstDeal && firstSight)) {
    G.animateFirstDeal = false;
    renderSeats(st); renderBubbles(st, false);
    $$('.trick-slot').forEach((s) => { s.innerHTML = ''; s.dataset.code = ''; });
    $('#center-call').innerHTML = '';
    G.dealId = st.deal_id; G.dealStage = 1;
    const s1 = Object.assign({}, st);
    await animateDeal(s1, 1);
    if (st.deal_stage === 2) { G.dealStage = 2; await animateDeal(st, 2); }
  } else if (stage2) {
    renderSeats(st);
    G.dealStage = 2;
    await animateDeal(st, 2);
  }
  G.dealId = st.deal_id; G.dealStage = st.deal_stage;

  renderSeats(st);
  // Bids
  const hist = st.bidding_history || [];
  while (G.bidSeen < hist.length) { await animateBid(st, hist[G.bidSeen]); G.bidSeen += 1; }
  renderBubbles(st, false);

  // Single Hand announcement
  const shKey = `${st.deal_id}`;
  if (st.single_hand && G.singleKey !== shKey) {
    G.singleKey = shKey;
    if (!firstSight) { centerCall(`Single Hand<small>${verb(st.single_hand_declarer, 'plays', 'play')} alone</small>`, 'single'); Sfx.play('single'); await sleep(1200 * pace()); }
  }
  // Trump reveal
  const revKey = `${st.deal_id}:${st.trump_suit}`;
  if (st.trump_revealed && st.trump_suit && G.revealedKey !== revKey) {
    const wasHidden = prev && prev.deal_id === st.deal_id && !prev.trump_revealed;
    G.revealedKey = revKey;
    if (wasHidden && !firstSight) await cinematicReveal(st);
  }
  // Trick plays
  const tr = st.current_trick;
  if (tr) {
    const key = `${st.deal_id}:${tr.trick_number}`;
    if (G.trickKey !== key) {
      G.trickKey = key; G.trickSeen = firstSight ? tr.cards.length : 0;
      if (!firstSight) $$('.trick-slot').forEach((s) => { s.innerHTML = ''; s.dataset.code = ''; });
    }
    renderHand(st);
    while (G.trickSeen < tr.cards.length) {
      const pc = tr.cards[G.trickSeen];
      G.trickSeen += 1;
      await animatePlay(st, pc);
      const slot = slotEl(pc.player_id); slot.dataset.code = pc.card.code;
    }
  }
  if (!G.dealing) renderTrickStatic(st);
  renderHand(st); renderDock(st); renderSeats(st);
}

function nextMove(st) {
  if (st.deal_abandoned) return 'abandoned';
  if (st.marriage_popup_pending) return 'marriage';
  if (st.phase === 'GAME_OVER') return 'gameover';
  if (st.phase === 'ROUND_OVER') return 'roundover';
  if (st.pending_trick_pause) return 'collect';
  if (st.mode === 'human' && st.is_human_turn) return 'human';
  return 'ai';
}
const THINK = { relaxed: 1000, normal: 560, fast: 140 };

async function director(token) {
  let failures = 0;
  while (token === G.token) {
    let st;
    try { st = await getState(); failures = 0; }
    catch (e) { failures += 1; if (failures === 2) toast('Connection to the game server lost — retrying…', 'error'); await sleep(Math.min(5000, 600 * failures)); continue; }
    if (token !== G.token) return;
    await sync(st);
    if (token !== G.token) return;
    const move = nextMove(st);
    try {
      if (move === 'abandoned') { await showAbandon(st); }
      else if (move === 'marriage') { await showMarriage(st); }
      else if (move === 'gameover') {
        if (G.lastRoundShown !== `${st.match_id}:${st.round_number}`) { G.lastRoundShown = `${st.match_id}:${st.round_number}`; await showRoundSummary(st); }
        showGameOver(st); return;
      } else if (move === 'roundover') {
        if (G.lastRoundShown !== `${st.match_id}:${st.round_number}`) { G.lastRoundShown = `${st.match_id}:${st.round_number}`; await showRoundSummary(st); }
        if (token !== G.token) return;
        await act('next_round');
      } else if (move === 'collect') {
        await collectTrick(st);
        await act('clear_trick');
      } else if (move === 'human') {
        if (st.phase === 'TRUMP_SELECTION') showTrumpPicker(st);
        await waitWake();
      } else {
        if (st.mode === 'ai' && G.paused && !G.stepOnce) { await waitWake(); continue; }
        G.stepOnce = false;
        const actor = actorOf(st);
        if (actor != null) seatEl(actor).classList.add('thinking');
        const base = st.mode === 'ai' ? THINK[G.spSpeed] : 480;
        await sleep(base * (S.reduced ? 0.6 : 1));
        await act('step');
        if (actor != null) seatEl(actor).classList.remove('thinking');
      }
    } catch (e) {
      console.error(e); await sleep(800);
    }
  }
}
function startDirector(animateDeal = false) {
  G.token += 1; G.st = null; G.dealId = null; G.dealStage = 0; G.animateFirstDeal = animateDeal;
  G.paused = false; G.wakeFn = null; G.wakePending = false; G.acting = false;
  director(G.token);
}

// ------------------------------------------------------------------ screens & menus
function showScreen(id) { $$('.screen').forEach((s) => s.classList.toggle('active', s.id === id)); }
function openSetup(mode) {
  const cfg = G.cfg; if (mode) cfg.mode = mode;
  $$('#mode-switch button').forEach((b) => b.classList.toggle('active', b.dataset.mode === cfg.mode));
  buildSeatGrid(); fillRules(); openOverlay('#ov-setup');
}
function buildSeatGrid() {
  const cfg = G.cfg; const labels = ['South (bottom)', 'West (left)', 'North (top) — partner of South', 'East (right)'];
  $('#seat-grid').innerHTML = [0, 1, 2, 3].map((s) => {
    const human = cfg.mode === 'human' && s === 0;
    const team = teamOf(s) === 0 ? 'a' : 'b';
    const pick = human ? '<div class="human-tag">You play this seat</div>' :
      `<div class="persona-pick" data-seat="${s}">${['AGGRESSIVE', 'STRATEGIC', 'DEFENSIVE'].map((p) => `<button data-p="${p}" class="${cfg.personalities[s] === p ? 'active' : ''}">${svg(PERSONA_ICON[p])}${PERSONA_LABEL[p]}</button>`).join('')}</div>`;
    const name = human ? (cfg.human_name || 'You') : cfg.names[s];
    return `<div class="seat-cfg"><div class="seat-cfg-top"><div class="avatar team-${team}" data-av="${s}">${esc(initialsOf(name))}</div>
      <div class="name-edit"><input class="name-input" data-seat="${s}" data-human="${human ? 1 : 0}" maxlength="16" value="${esc(name)}"
        aria-label="${human ? 'Your name' : 'Player name'}" placeholder="${human ? 'Your name' : 'Player name'}" spellcheck="false">
      <small>${labels[s]} · Team ${team.toUpperCase()}</small></div></div>${pick}</div>`;
  }).join('');
  $$('.persona-pick button').forEach((b) => b.addEventListener('click', () => {
    const seat = +b.parentElement.dataset.seat; G.cfg.personalities[seat] = b.dataset.p; Sfx.play('click'); buildSeatGrid();
  }));
  $$('.name-input').forEach((inp) => inp.addEventListener('input', () => {
    const seat = +inp.dataset.seat; const val = inp.value.replace(/\s+/g, ' ').slice(0, 16);
    if (inp.dataset.human === '1') G.cfg.human_name = val; else G.cfg.names[seat] = val;
    $(`[data-av="${seat}"]`).textContent = initialsOf(val || (inp.dataset.human === '1' ? 'You' : '?'));
  }));
  $$('#cfg-speed button').forEach((b) => b.classList.toggle('active', b.dataset.v === cfg.ai_speed));
}
function fillRules() {
  const r = G.cfg.rules; const sh = r.single_hand;
  $('#r-last-trick').checked = r.last_trick_bonus; $('#r-seventh').checked = r.allow_seventh_card; $('#r-double').checked = r.double_redouble;
  $('#r-marriage').checked = r.marriage_enabled; $('#r-marriage-mode').value = r.marriage_mode; $('#r-marriage-value').value = String(r.marriage_value);
  $('#r-all-pass').value = r.all_pass_rule; $('#r-target').value = String(r.match_target);
  $('#s-enabled').checked = sh.enabled; $('#s-timing').value = sh.timing; $('#s-sits-out').checked = sh.partner_sits_out;
  $('#s-partner-counts').checked = sh.partner_tricks_count; $('#s-all-tricks').checked = sh.must_win_all_tricks; $('#s-target').checked = sh.use_contract_target;
  $('#s-trump').value = sh.trump; $('#s-win').value = String(sh.win_points); $('#s-loss').value = String(sh.loss_points);
  syncRuleDisabling();
}
function syncRuleDisabling() {
  const on = $('#s-enabled').checked;
  ['#s-timing', '#s-sits-out', '#s-partner-counts', '#s-all-tricks', '#s-target', '#s-trump', '#s-win', '#s-loss'].forEach((id) => { const el = $(id); el.disabled = !on; const f = el.closest('.toggle-field,.select-field'); if (f) f.style.opacity = on ? 1 : 0.45; });
  const pc = $('#s-partner-counts'); const sits = $('#s-sits-out').checked;
  pc.disabled = !on || sits; pc.closest('.toggle-field').style.opacity = (!on || sits) ? 0.45 : 1;
  $('#r-marriage-mode').disabled = !$('#r-marriage').checked; $('#r-marriage-value').disabled = !$('#r-marriage').checked;
}
function readRules() {
  const r = G.cfg.rules;
  r.last_trick_bonus = $('#r-last-trick').checked; r.allow_seventh_card = $('#r-seventh').checked; r.double_redouble = $('#r-double').checked;
  r.marriage_enabled = $('#r-marriage').checked; r.marriage_mode = $('#r-marriage-mode').value; r.marriage_value = +$('#r-marriage-value').value;
  r.all_pass_rule = $('#r-all-pass').value; r.match_target = +$('#r-target').value;
  const sh = r.single_hand;
  sh.enabled = $('#s-enabled').checked; sh.timing = $('#s-timing').value; sh.partner_sits_out = $('#s-sits-out').checked;
  sh.partner_tricks_count = $('#s-partner-counts').checked; sh.must_win_all_tricks = $('#s-all-tricks').checked; sh.use_contract_target = $('#s-target').checked;
  if (!sh.must_win_all_tricks && !sh.use_contract_target) { sh.must_win_all_tricks = true; $('#s-all-tricks').checked = true; toast('A Single Hand needs a win condition — "win all tricks" re-enabled.'); }
  sh.trump = $('#s-trump').value; sh.win_points = +$('#s-win').value; sh.loss_points = +$('#s-loss').value;
}
async function startMatch() {
  readRules();
  store.set('config', G.cfg);
  Sfx.ensure(); Sfx.play('chip');
  const r = await act('new_match', { config: G.cfg });
  if (!r.success) { toast(r.message || 'Could not start: the game server did not accept the new match. Restart it with py main.py.', 'error'); return; }
  closeOverlay('#ov-setup');
  enterTable(true);
}
function enterTable(animate) {
  showScreen('screen-game'); G.started = true;
  $('#btn-resume').classList.remove('hidden');
  $('#insight-panel').classList.toggle('open', !!S.insight && window.innerWidth >= 1180);
  $('#log-panel').classList.remove('open');
  syncPanels();
  $$('.overlay').forEach((o) => { if (o.id !== 'ov-setup') o.classList.remove('open'); });
  startDirector(animate);
}

// ------------------------------------------------------------------ server version check
const APP_VERSION = '2.2.0';
async function versionAt(origin) {
  try {
    const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 1200);
    const r = await fetch(origin + '/api/version', { cache: 'no-store', signal: ctl.signal }); clearTimeout(t);
    if (!r.ok) return null;
    const v = await r.json();
    return v && v.app === 'bangladesh-29' ? v.version : null;
  } catch (e) { return null; }
}
// If this page was served by an older copy of the game server, find the current one and go there.
async function ensureCurrentServer() {
  if ((await versionAt('')) === APP_VERSION) return true;
  const port = +(location.port || 80);
  for (let p = 8029; p <= 8036; p++) {
    if (p === port) continue;
    const origin = `${location.protocol}//127.0.0.1:${p}`;
    if ((await versionAt(origin)) === APP_VERSION) { location.replace(origin + '/'); return false; }
  }
  const box = document.createElement('div');
  box.className = 'overlay open';
  box.innerHTML = `<div class="modal small-modal"><div class="kicker">Game server</div><h2>Start the game with py main.py</h2>
    <p>This browser tab is connected to an outdated copy of the game server.</p>
    <p>Run <b>py main.py</b> in the game folder. It replaces any old copy automatically and opens the table in your browser.</p></div>`;
  document.body.appendChild(box);
  return false;
}

// ------------------------------------------------------------------ init
async function init() {
  hydrateIcons();
  preloadCards();
  BG.init(); FX.init(); applySettings();

  // Menu decorations
  const heroes = ['JS', '9H', 'AC', '10D'];
  $$('.hero-card').forEach((h, i) => { h.innerHTML = cardFace(heroes[i]); });
  $('#rank-strip').innerHTML = ['J', '9', 'A', '10', 'K', 'Q', '8', '7'].map((r) => cardFace(r + 'S')).join('');

  const FALLBACK = {
    mode: 'human', personalities: ['STRATEGIC', 'AGGRESSIVE', 'STRATEGIC', 'DEFENSIVE'], names: ['Rafi', 'Nadia', 'Tanvir', 'Mitu'], human_name: 'You', ai_speed: 'normal',
    rules: { last_trick_bonus: false, all_pass_rule: 'dealer_forced', min_bid: 16, max_bid: 28, allow_seventh_card: true, marriage_enabled: true, marriage_mode: 'auto', marriage_value: 4, double_redouble: true, match_target: 6,
      single_hand: { enabled: true, timing: 'after_deal', partner_sits_out: true, partner_tricks_count: false, must_win_all_tricks: true, use_contract_target: false, trump: 'none', win_points: 3, loss_points: 3 } },
  };
  if (!(await ensureCurrentServer())) return;
  try {
    const d = await (await fetch('/api/defaults', { cache: 'no-store' })).json();
    G.defaults = d.config;
  } catch (e) { G.defaults = null; }
  const base = G.defaults || FALLBACK;
  const saved = store.get('config', null);
  const usable = saved && saved.personalities && saved.names && saved.rules && saved.rules.single_hand;
  G.cfg = JSON.parse(JSON.stringify(usable ? saved : base));

  // Is there a game in progress on the server?
  try {
    const st = await getState();
    if (st.round_number > 1 || (st.bidding_history || []).length || st.phase !== 'BIDDING') $('#btn-resume').classList.remove('hidden');
  } catch (e) { toast('Game server not reachable. Start it with: py main.py', 'error'); }

  // Menu
  $$('[data-menu]').forEach((b) => b.addEventListener('click', () => {
    Sfx.ensure(); Sfx.play('click');
    const m = b.dataset.menu;
    if (m === 'start') openSetup(G.cfg.mode || 'human');
    else if (m === 'human' || m === 'ai') openSetup(m);
    else if (m === 'howto') openOverlay('#ov-howto');
    else if (m === 'settings') openSettings();
    else if (m === 'resume') enterTable(false);
  }));
  $$('#mode-switch button').forEach((b) => b.addEventListener('click', () => { G.cfg.mode = b.dataset.mode; $$('#mode-switch button').forEach((x) => x.classList.toggle('active', x === b)); buildSeatGrid(); Sfx.play('click'); }));
  $$('.tab').forEach((t) => t.addEventListener('click', () => { $$('.tab').forEach((x) => x.classList.toggle('active', x === t)); $$('.tab-pane').forEach((p) => p.classList.toggle('active', p.id === t.dataset.tab)); }));
  $$('#cfg-speed button').forEach((b) => b.addEventListener('click', () => { G.cfg.ai_speed = b.dataset.v; $$('#cfg-speed button').forEach((x) => x.classList.toggle('active', x === b)); }));
  ['#s-enabled', '#s-sits-out', '#r-marriage'].forEach((id) => $(id).addEventListener('change', syncRuleDisabling));
  $('#btn-start-match').addEventListener('click', startMatch);
  $$('[data-dismiss]').forEach((b) => b.addEventListener('click', () => closeOverlay('#' + b.closest('.overlay').id)));
  $$('.overlay').forEach((o) => o.addEventListener('click', (e) => { if (e.target === o && ['ov-setup', 'ov-settings', 'ov-howto'].includes(o.id)) closeOverlay('#' + o.id); }));

  // HUD
  $('#btn-menu').addEventListener('click', () => { G.token += 1; showScreen('screen-menu'); $$('.overlay').forEach((o) => o.classList.remove('open')); });
  $('#btn-insight').addEventListener('click', () => { $('#insight-panel').classList.toggle('open'); $('#log-panel').classList.remove('open'); syncPanels(); });
  $('#btn-log').addEventListener('click', () => { $('#log-panel').classList.toggle('open'); $('#insight-panel').classList.remove('open'); syncPanels(); });
  $$('[data-close]').forEach((b) => b.addEventListener('click', () => { $('#' + b.dataset.close).classList.remove('open'); syncPanels(); }));
  $('#adv-toggle').addEventListener('change', (e) => $('#insight-feed').classList.toggle('show-adv', e.target.checked));
  [$('#btn-sound'), $('#menu-sound')].forEach((b) => b.addEventListener('click', () => { S.sound = !S.sound; saveSettings(); if (S.sound) { Sfx.ensure(); Sfx.play('chip'); } }));
  $('#btn-settings').addEventListener('click', openSettings);

  // Spectator
  $('#sp-play').addEventListener('click', () => { G.paused = !G.paused; if (G.paused) G.wakePending = false; renderSpectator(G.st || {}); if (!G.paused) wake(); });
  $('#sp-step').addEventListener('click', () => { G.paused = true; G.stepOnce = true; renderSpectator(G.st || {}); wake(); });
  $$('#sp-speed button').forEach((b) => b.addEventListener('click', () => { G.spSpeed = b.dataset.speed; store.set('spSpeed', G.spSpeed); renderSpectator(G.st || {}); }));

  // Overlays
  $('#btn-rematch').addEventListener('click', async () => { closeOverlay('#ov-gameover'); await act('rematch'); enterTable(true); });
  $('#btn-go-menu').addEventListener('click', () => { closeOverlay('#ov-gameover'); G.token += 1; showScreen('screen-menu'); });

  // Settings
  bindSettings();

  // Keyboard: Escape closes panels/dialogs
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { ['#ov-settings', '#ov-howto', '#ov-setup'].forEach((id) => closeOverlay(id)); $('#insight-panel').classList.remove('open'); $('#log-panel').classList.remove('open'); syncPanels(); }
    if (e.key === ' ' && G.st && G.st.mode === 'ai' && $('#screen-game').classList.contains('active')) { e.preventDefault(); $('#sp-play').click(); }
  });
  hydrateIcons();
}

function openSettings() {
  $('#set-sound').checked = S.sound; $('#set-volume').value = Math.round(S.volume * 100); $('#set-reduced').checked = S.reduced;
  $('#set-insight').checked = S.insight;
  $$('#set-pace button').forEach((b) => b.classList.toggle('active', b.dataset.v === S.pace));
  openOverlay('#ov-settings');
}
function bindSettings() {
  $('#set-sound').addEventListener('change', (e) => { S.sound = e.target.checked; saveSettings(); });
  $('#set-volume').addEventListener('input', (e) => { S.volume = e.target.value / 100; saveSettings(); });
  $('#set-volume').addEventListener('change', () => Sfx.play('chip'));
  $('#set-reduced').addEventListener('change', (e) => { S.reduced = e.target.checked; saveSettings(); });
  $('#set-insight').addEventListener('change', (e) => { S.insight = e.target.checked; saveSettings(); });
  $$('#set-pace button').forEach((b) => b.addEventListener('click', () => { S.pace = b.dataset.v; saveSettings(); $$('#set-pace button').forEach((x) => x.classList.toggle('active', x === b)); }));
}

document.addEventListener('DOMContentLoaded', init);
