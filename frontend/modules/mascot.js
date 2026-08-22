// OTTO mascot — live vanilla-JS port of jeremy-prt/bloub's SVG bot engine (MIT).
// Renders BotEngine.sample(t) into imperative SVG, drives it off OTTO app events.
import { BotEngine } from '../assets/mascot/bot/engine.js';
import { EXPRESSION_BY_ID } from '../assets/mascot/bot/expressions.js';
import { SHAPE_BY_ID, COLOR_BY_ID, mixHex } from '../assets/mascot/bot/skins.js';
import { DEMI_VIEWBOX, RAYON } from '../assets/mascot/bot/repere.js';
import { STATE_BY_ID } from '../assets/mascot/bot/states.js';
import { lookTarget, TURN_TIME } from '../assets/mascot/bot/gaze.js';
import { easings, clamp } from '../assets/mascot/bot/math.js';

const SVG_NS = 'http://www.w3.org/2000/svg';

const SHAPE_ID = 'squircle';
const COLOR_ID = 'encre';
const EXPRESSION_ID = 'attentif';
const SLEEP_AFTER_MS = 5 * 60 * 1000;

function el(tag, attrs = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}

export class OttoMascot {
  constructor(containerId = 'mascotContainer', opts = {}) {
    this.container = document.getElementById(containerId);
    if (!this.container) return;
    this.size = opts.size ?? 48;
    this.paper = opts.paper ?? '#f7f5f0';

    this.shapeRadii = SHAPE_BY_ID.get(SHAPE_ID)?.radii ?? null;
    this.ink = COLOR_BY_ID.get(COLOR_ID)?.hex ?? '#0a0a0c';
    this.expression = EXPRESSION_BY_ID.get(EXPRESSION_ID) ?? null;

    this.engine = new BotEngine(RAYON, 'idle', this.shapeRadii, this.expression);
    this.uid = Math.random().toString(36).slice(2, 8);

    this.clock = 0;
    this.last = 0;
    this.pointer = null;
    this.aiming = false;
    this.turnSince = 0;
    this.lastInteraction = performance.now();
    this.sleeping = false;

    this._buildDom();
    this._bindEvents();
    this._raf = requestAnimationFrame((ms) => this._tick(ms));
  }

  _buildDom() {
    this.container.innerHTML = '';
    const vb = DEMI_VIEWBOX;
    this.svg = el('svg', {
      width: this.size,
      height: this.size,
      viewBox: `${-vb} ${-vb} ${vb * 2} ${vb * 2}`,
      role: 'img',
      'aria-label': 'OTTO mascot',
      style: 'cursor:pointer;display:block'
    });

    const defs = el('defs');
    this.mask = el('mask', { id: `bot-mask-${this.uid}`, maskUnits: 'userSpaceOnUse', x: -vb, y: -vb, width: vb * 2, height: vb * 2 });
    this.maskBody = el('path', { fill: '#fff' });
    this.maskNotch = el('circle', { fill: '#000' });
    this.mask.appendChild(this.maskBody);
    this.mask.appendChild(this.maskNotch);
    defs.appendChild(this.mask);
    this.gradDefs = defs;
    this.svg.appendChild(defs);

    this.backArcs = el('g', { fill: 'none', 'stroke-linecap': 'round' });
    this.dotsBehind = el('g');
    this.bodyGroup = el('g');
    this.bodyBg = el('path', { fill: this.paper });
    this.bodyFill = el('g', { mask: `url(#bot-mask-${this.uid})` });
    this.bodyRect = el('rect', { x: -vb, y: -vb, width: vb * 2, height: vb * 2, fill: this.ink });
    this.bodyFill.appendChild(this.bodyRect);
    this.bodyGroup.appendChild(this.bodyBg);
    this.bodyGroup.appendChild(this.bodyFill);
    this.dotsFront = el('g');
    this.notifCircle = el('circle', { fill: '#2496e8', style: 'display:none' });
    this.frontArcs = el('g', { fill: 'none', 'stroke-linecap': 'round' });

    this.svg.appendChild(this.backArcs);
    this.svg.appendChild(this.dotsBehind);
    this.svg.appendChild(this.bodyGroup);
    this.svg.appendChild(this.dotsFront);
    this.svg.appendChild(this.notifCircle);
    this.svg.appendChild(this.frontArcs);

    this.container.appendChild(this.svg);
    this.svg.title = 'OTTO — your AI deal scout';
  }

  _bindEvents() {
    window.addEventListener('pointermove', (e) => {
      if (e.pointerType === 'touch') return;
      this.pointer = { x: e.clientX, y: e.clientY };
      this.lastInteraction = performance.now();
      if (this.sleeping) this._wake();
    });
    document.addEventListener('pointerleave', () => { this.pointer = null; });
    this.svg.addEventListener('click', () => {
      this.lastInteraction = performance.now();
      if (this.sleeping) { this._wake(); return; }
      this.triggerState('wink', 1600);
    });
  }

  _wake() {
    this.sleeping = false;
    this.engine.setState('idle', this.clock);
  }

  // OTTO's semantic event names -> bloub's animation-catalogue states.
  static STATE_MAP = {
    inspecting: 'thinking',
    thinking: 'thinking',
    searching: 'thinking',
    scraping: 'orbit',
    excited: 'wide',
    hotdeal: 'notify',
    error: 'alert',
    wink: 'wink'
  };

  // Trigger a transient state, then fall back to `idle` unless another call
  // supersedes it first. Accepts either an OTTO event name or a raw bloub state id.
  triggerState(name, holdMs = 2000) {
    const state = OttoMascot.STATE_MAP[name] ?? name;
    if (!STATE_BY_ID.has(state)) return;
    this.sleeping = false;
    this.lastInteraction = performance.now();
    this.engine.setState(state, this.clock);
    if (this._flashTimer) clearTimeout(this._flashTimer);
    this._flashTimer = setTimeout(() => {
      if (this.engine.state === state) this.engine.setState('idle', this.clock);
    }, holdMs);
  }

  // Hold a looping state until explicitly released back to idle (e.g. full scrape running).
  setBusy(name) {
    const state = OttoMascot.STATE_MAP[name] ?? name;
    if (!STATE_BY_ID.has(state)) return;
    this.sleeping = false;
    this.lastInteraction = performance.now();
    if (this._flashTimer) { clearTimeout(this._flashTimer); this._flashTimer = null; }
    this.engine.setState(state, this.clock);
  }

  idle() {
    if (this._flashTimer) { clearTimeout(this._flashTimer); this._flashTimer = null; }
    this.engine.setState('idle', this.clock);
  }

  _aim() {
    if (!STATE_BY_ID.get(this.engine.state)?.baseFace) {
      if (this.aiming) { this.engine.setLook(null, this.clock, TURN_TIME); this.aiming = false; }
      return;
    }
    const box = this.svg.getBoundingClientRect();
    if (!box || box.width === 0 || box.height === 0) return;
    if (!this.aiming) this.turnSince = this.clock;
    const halfW = Math.max(1, window.innerWidth / 2);
    const halfH = Math.max(1, window.innerHeight / 2);
    this.engine.setLook(
      lookTarget({
        nx: this.pointer ? clamp((this.pointer.x - (box.left + box.width / 2)) / halfW, -1, 1) : 0,
        ny: this.pointer ? clamp((this.pointer.y - (box.top + box.height / 2)) / halfH, -1, 1) : 0,
        tour: easings.easeOutQuint(clamp((this.clock - this.turnSince) / TURN_TIME)),
        pointer: this.pointer !== null
      }),
      this.clock
    );
    this.aiming = true;
  }

  _dotAttrs(dot) {
    const fill = dot.color ?? (dot.depth === undefined ? this.ink : mixHex(this.paper, this.ink, dot.depth));
    if (dot.d) return { fill, opacity: dot.opacity, d: dot.d, transform: `translate(${dot.x} ${dot.y}) rotate(${dot.rot ?? 0}) scale(${RAYON})` };
    return { fill, opacity: dot.opacity, cx: dot.x, cy: dot.y, r: dot.r };
  }

  _renderDots(group, dots, keyPrefix) {
    while (group.children.length > dots.length) group.removeChild(group.lastChild);
    dots.forEach((dot, i) => {
      const isPath = !!dot.d;
      let node = group.children[i];
      if (!node || node.tagName !== (isPath ? 'path' : 'circle')) {
        if (node) group.removeChild(node);
        node = el(isPath ? 'path' : 'circle');
        group.insertBefore(node, group.children[i] ?? null);
      }
      const attrs = this._dotAttrs(dot);
      for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    });
  }

  _renderArcs(group, side, arcs) {
    while (group.children.length > arcs.length) group.removeChild(group.lastChild);
    arcs.forEach((arc, i) => {
      let node = group.children[i];
      if (!node) { node = el('path'); group.appendChild(node); }
      let grad = this.gradDefs.querySelector(`#${this.uid}-${arc.id}`);
      if (!grad) {
        grad = el('linearGradient', { id: `${this.uid}-${arc.id}`, gradientUnits: 'userSpaceOnUse' });
        this.gradDefs.appendChild(grad);
      }
      grad.setAttribute('x1', arc.grad.x1);
      grad.setAttribute('y1', arc.grad.y1);
      grad.setAttribute('x2', arc.grad.x2);
      grad.setAttribute('y2', arc.grad.y2);
      grad.innerHTML = '';
      arc.grad.stops.forEach((c, si) => grad.appendChild(el('stop', { offset: si / (arc.grad.stops.length - 1), 'stop-color': c })));
      node.setAttribute('d', side === 'front' ? arc.front : arc.back);
      node.setAttribute('stroke', `url(#${this.uid}-${arc.id})`);
      node.setAttribute('stroke-width', arc.width);
      node.setAttribute('opacity', arc.opacity);
    });
  }

  _render(frame) {
    this.maskBody.setAttribute('d', frame.bodyPath);
    while (this.mask.querySelectorAll('.eye-mask').length > frame.eyes.length) {
      this.mask.removeChild(this.mask.querySelector('.eye-mask:last-of-type'));
    }
    frame.eyes.forEach((eye, i) => {
      let node = this.mask.querySelectorAll('.eye-mask')[i];
      if (!node) {
        node = el('path', { class: 'eye-mask', fill: '#000' });
        this.mask.insertBefore(node, this.maskNotch);
      }
      node.setAttribute('d', eye.d);
      node.setAttribute('transform', eye.matrix);
      node.setAttribute('opacity', eye.alpha);
    });

    if (frame.notch) {
      this.maskNotch.setAttribute('cx', frame.notch.x);
      this.maskNotch.setAttribute('cy', frame.notch.y);
      this.maskNotch.setAttribute('r', frame.notch.r);
      this.maskNotch.style.display = '';
    } else {
      this.maskNotch.style.display = 'none';
    }

    this.bodyBg.setAttribute('d', frame.bodyPath);
    this.bodyGroup.setAttribute('opacity', frame.bodyAlpha);

    this._renderDots(this.dotsBehind, frame.dotsBehind ? frame.dots : [], 'db');
    this._renderDots(this.dotsFront, frame.dotsBehind ? [] : frame.dots, 'df');

    if (frame.notif) {
      this.notifCircle.setAttribute('cx', frame.notif.x);
      this.notifCircle.setAttribute('cy', frame.notif.y);
      this.notifCircle.setAttribute('r', frame.notif.r);
      this.notifCircle.style.display = '';
    } else {
      this.notifCircle.style.display = 'none';
    }

    this._renderArcs(this.backArcs, 'back', frame.arcs);
    this._renderArcs(this.frontArcs, 'front', frame.arcs);
  }

  _tick(ms) {
    this._raf = requestAnimationFrame((t) => this._tick(t));
    const dt = this.last ? Math.min((ms - this.last) / 1000, 0.064) : 0;
    this.last = ms;
    this.clock += dt;

    if (!this.sleeping && performance.now() - this.lastInteraction > SLEEP_AFTER_MS && this.engine.state === 'idle') {
      this.sleeping = true;
      this.engine.setState('sleep', this.clock);
    }

    this._aim();
    this._render(this.engine.sample(this.clock));
  }

  destroy() {
    cancelAnimationFrame(this._raf);
    if (this._flashTimer) clearTimeout(this._flashTimer);
  }
}

// Legacy alias — old call sites used `ScoutMascot`.
export { OttoMascot as ScoutMascot };
