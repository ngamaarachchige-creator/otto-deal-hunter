// Ported from jeremy-prt/bloub (MIT License) — https://github.com/jeremy-prt/bloub
import { arcRender } from './decor.js';
import { blendExpression } from './expressions.js';
import { decalageDesYeux } from './eyefit.js';
import { blinkScale, eyePoses, liveliness } from './face.js';
import { clamp, easings, lerp, r2 } from './math.js';
import { blend, capsulePath, closedPath, radiusAtAngle, toPoints } from './shape.js';
import { STATE_BY_ID } from './states.js';

// Where the bot looks when something external drives it (the mouse pointer).
// yaw/pitch are ABSOLUTE and replace the pose's own as `mix` rises — the engine
// does that mixing since only it knows the pose at instant t. `mix` says how
// much the outside world commands the direction; `wander` is what's left of
// automatic drift, added AFTER the mix so a turned head without a pointer still
// looks alive instead of frozen. `spin` is a turn taken on the way, melting to 0
// with arrival (harmless since -360deg == 0deg on a sphere).
const NO_LOOK = { yaw: 0, pitch: 0, mix: 0, spin: 0, wander: 1 };

const lerpLook = (a, b, t) => ({
  yaw: lerp(a.yaw, b.yaw, t),
  pitch: lerp(a.pitch, b.pitch, t),
  mix: lerp(a.mix, b.mix, t),
  spin: lerp(a.spin, b.spin, t),
  wander: lerp(a.wander, b.wander, t)
});

const lerpEye = (a, b, t) => ({ w: lerp(a.w, b.w, t), h: lerp(a.h, b.h, t), open: lerp(a.open, b.open, t), tilt: lerp(a.tilt ?? 0, b.tilt ?? 0, t) });

function blendPose(a, b, t) {
  const out = 1 - t;
  return {
    sil: blend(a.sil, b.sil, t),
    offX: lerp(a.offX, b.offX, t),
    offY: lerp(a.offY, b.offY, t),
    gaze: { yaw: lerp(a.gaze.yaw, b.gaze.yaw, t), pitch: lerp(a.gaze.pitch, b.gaze.pitch, t), roll: lerp(a.gaze.roll, b.gaze.roll, t) },
    split: lerp(a.split, b.split, t),
    eyes: [lerpEye(a.eyes[0], b.eyes[0], t), lerpEye(a.eyes[1], b.eyes[1], t)],
    eyeAlpha: lerp(a.eyeAlpha, b.eyeAlpha, t),
    bodyAlpha: lerp(a.bodyAlpha, b.bodyAlpha, t),
    dots: [...a.dots.map((d) => ({ ...d, opacity: d.opacity * out })), ...b.dots.map((d) => ({ ...d, opacity: d.opacity * t }))],
    arcs: [
      ...a.arcs.map((r) => ({ ...r, id: `a${r.id}`, opacity: r.opacity * out })),
      ...b.arcs.map((r) => ({ ...r, id: `b${r.id}`, opacity: r.opacity * t }))
    ],
    notif: t < 0.5 ? a.notif : b.notif,
    dotsBehind: t < 0.5 ? a.dotsBehind : b.dotsBehind
  };
}

// Clockless engine: sample(t) is a pure function of time. Pause, resume, slow-mo
// and jumping to an arbitrary date all give exactly the same image.
export class BotEngine {
  static SHAPE_MORPH = 0.45;
  static LOOK_MORPH = 0.24;

  constructor(scale = 100, initial = 'idle', shape = null, expression = null) {
    this.scale = scale;
    this.cur = initial;
    this.prev = null;
    this.departFige = null;
    this.tCur = 0;
    this.tPrev = 0;
    this.blinkAt = -10;
    this.pts = [];
    this.shape = shape;
    this.shapePrev = null;
    this.shapeAt = -10;
    this.expr = expression;
    this.exprPrev = null;
    this.exprAt = -10;
    this.look = NO_LOOK;
    this.lookPrev = NO_LOOK;
    this.lookAt = -10;
    this.lookMorph = BotEngine.LOOK_MORPH;
  }

  setExpression(expression, now = 0) {
    if (expression === this.expr) return;
    this.exprPrev = this.expr;
    this.expr = expression;
    this.exprAt = now;
  }

  exprAtTime(now) {
    const to = this.expr;
    const from = this.exprPrev;
    if (!to || !from) return to;
    const k = (now - this.exprAt) / BotEngine.SHAPE_MORPH;
    if (k >= 1) return to;
    return blendExpression(from, to, easings.easeOutQuint(clamp(k)));
  }

  setShape(radii, now = 0) {
    if (radii === this.shape) return;
    this.shapePrev = this.shape;
    this.shape = radii;
    this.shapeAt = now;
  }

  shapeAtTime(now) {
    const to = this.shape;
    const from = this.shapePrev;
    if (!to || !from) return to;
    const k = (now - this.shapeAt) / BotEngine.SHAPE_MORPH;
    if (k >= 1) return to;
    const t = easings.easeOutQuint(clamp(k));
    return to.map((r, i) => lerp(from[i] ?? r, r, t));
  }

  // Refuses a non-finite target — the engine KEEPS the last one, since a single
  // NaN would propagate every frame and the bot would never rest again.
  setLook(look, now, morph = BotEngine.LOOK_MORPH) {
    if (look && !Number.isFinite(look.yaw + look.pitch + look.mix + look.spin + look.wander)) return;
    this.lookPrev = this.lookAtTime(now);
    this.look = look ?? NO_LOOK;
    this.lookAt = now;
    this.lookMorph = morph;
  }

  lookAtTime(now) {
    const k = (now - this.lookAt) / this.lookMorph;
    if (k >= 1) return this.look;
    return lerpLook(this.lookPrev, this.look, easings.easeOutQuint(clamp(k)));
  }

  posed(def, t, shape, expr) {
    let pose = def.pose(t);
    if (def.baseBody && shape) {
      pose = { ...pose, sil: { ...pose.sil, radii: shape } };
    }
    if (def.baseFace && expr) {
      pose = { ...pose, gaze: expr.gaze, split: expr.split, eyes: expr.eyes };
    }
    return pose;
  }

  decalageAtTime(now, state) {
    const surAxe = (debut, duree, a, b) => {
      if (a === b) return b;
      const k = (now - debut) / duree;
      if (k >= 1) return b;
      const t = easings.easeOutQuint(clamp(k));
      return { x: lerp(a.x, b.x, t), y: lerp(a.y, b.y, t) };
    };
    const parForme = (radii) =>
      surAxe(this.exprAt, BotEngine.SHAPE_MORPH, decalageDesYeux(radii, state, this.exprPrev?.id ?? null), decalageDesYeux(radii, state, this.expr?.id ?? null));
    return surAxe(this.shapeAt, BotEngine.SHAPE_MORPH, parForme(this.shapePrev), parForme(this.shape));
  }

  get state() {
    return this.cur;
  }

  // Restart on `id` with NO previous state, as if the engine were fresh.
  reset(id, now) {
    this.cur = id;
    this.prev = null;
    this.departFige = null;
    this.tCur = now;
    this.tPrev = now;
    this.blinkAt = -10;
  }

  origine(now, shape, expr) {
    if (this.departFige) return this.departFige;
    if (!this.prev) return null;
    const prevDef = STATE_BY_ID.get(this.prev);
    return this.posed(prevDef, Math.max(0, now - this.tPrev), shape, expr);
  }

  poseComposee(now) {
    const def = STATE_BY_ID.get(this.cur);
    const shape = this.shapeAtTime(now);
    const expr = this.exprAtTime(now);
    const pose = this.posed(def, Math.max(0, now - this.tCur), shape, expr);
    const since = now - this.tCur;
    if (since >= def.morph) return pose;
    const origine = this.origine(now, shape, expr);
    if (!origine) return pose;
    return blendPose(origine, pose, easings.easeOutQuint(clamp(since / def.morph)));
  }

  // State change, dated. The engine keeps only one slot of history, so a change
  // landing mid-fade freezes the composite pose actually on screen and blends
  // from THAT — otherwise the fade origin snaps to the outgoing state's full
  // pose instead of the partially-blended frame that was displayed.
  setState(id, now) {
    if (id === this.cur) return;
    const morph = STATE_BY_ID.get(this.cur).morph;
    const enPleinFondu = this.prev !== null && now - this.tCur < morph;
    this.departFige = enPleinFondu ? this.poseComposee(now) : null;
    this.prev = this.cur;
    this.tPrev = this.tCur;
    this.cur = id;
    this.tCur = now;
    if (STATE_BY_ID.get(id)?.blinkIn) this.blinkAt = now;
  }

  sample(now) {
    const R = this.scale;
    const def = STATE_BY_ID.get(this.cur);
    const shape = this.shapeAtTime(now);
    const expr = this.exprAtTime(now);
    let pose = this.posed(def, Math.max(0, now - this.tCur), shape, expr);
    let decalage = this.decalageAtTime(now, this.cur);

    const since = now - this.tCur;
    const origine = since < def.morph ? this.origine(now, shape, expr) : null;
    if (origine) {
      const ratio = easings.easeOutQuint(clamp(since / def.morph));
      pose = blendPose(origine, pose, ratio);
      const quitte = this.prev;
      if (quitte) {
        const avant = this.decalageAtTime(now, quitte);
        decalage = { x: lerp(avant.x, decalage.x, ratio), y: lerp(avant.y, decalage.y, ratio) };
      }
    }

    const alive = pose.eyeAlpha > 0.01;
    const look = this.lookAtTime(now);
    const life = liveliness(now, { wander: alive ? look.wander : 0, blink: alive });

    const gaze = {
      yaw: lerp(pose.gaze.yaw, look.yaw, look.mix) + life.dYaw - look.spin,
      pitch: lerp(pose.gaze.pitch, look.pitch, look.mix) + life.dPitch,
      roll: pose.gaze.roll + life.dRoll
    };

    const forced = clamp((now - this.blinkAt) / 0.2);
    const forcedLid = forced < 1 ? Math.abs(forced * 2 - 1) : 1;
    const lid = Math.min(life.lid, forcedLid);

    const offX = pose.offX + life.driftX;
    const offY = pose.offY + life.driftY;

    const sil = { ...pose.sil, cx: pose.sil.cx + offX, cy: pose.sil.cy + offY, sy: pose.sil.sy * life.breath };
    const bodyPath = closedPath(toPoints(sil, R, this.pts));

    const bodyRadius = (x, y) => radiusAtAngle(pose.sil.radii, Math.atan2(y, x) - pose.sil.rot);

    const eyes = [];
    if (pose.eyeAlpha > 0.01) {
      const poses = eyePoses(gaze, R, pose.split);
      for (let i = 0; i < 2; i++) {
        const e = poses[i];
        if (e.depth <= 0.02) continue;
        const cfg = pose.eyes[i];
        const fit = bodyRadius(e.x, e.y);
        const phi = ((cfg.tilt ?? 0) * Math.PI) / 180;
        const cp = Math.cos(phi);
        const sp = Math.sin(phi);
        const ax = e.a * cp + e.c * sp;
        const ay = e.b * cp + e.d * sp;
        const cx2 = -e.a * sp + e.c * cp;
        const cy2 = -e.b * sp + e.d * cp;
        const k = blinkScale(Math.min(lid, cfg.open));
        eyes.push({
          d: capsulePath(cfg.w * R, cfg.h * R),
          matrix: `matrix(${r2(ax)},${r2(ay * k)},${r2(cx2)},${r2(cy2 * k)},${r2(e.x * fit + (offX + decalage.x) * R)},${r2(e.y * fit + (offY + decalage.y) * R)})`,
          alpha: pose.eyeAlpha * clamp(e.depth / 0.12)
        });
      }
    }

    const dots = pose.dots.filter((p) => p.opacity > 0.01 && p.r > 0.0005).map((p) => ({ ...p, x: (p.x + offX) * R, y: (p.y + offY) * R, r: p.r * R }));

    const nFit = pose.notif ? bodyRadius(pose.notif.x, pose.notif.y) : 1;
    const nx = pose.notif ? (pose.notif.x * nFit + offX) * R : 0;
    const ny = pose.notif ? (pose.notif.y * nFit + offY) * R : 0;
    const notif = pose.notif ? { x: nx, y: ny, r: pose.notif.r * R } : null;
    const notch = pose.notif ? { x: nx, y: ny, r: pose.notif.notch * R } : null;

    return {
      bodyPath,
      bodyAlpha: pose.bodyAlpha,
      eyes,
      dots,
      dotsBehind: pose.dotsBehind,
      arcs: pose.arcs.filter((a) => a.opacity > 0.01).map((a) => arcRender(a.seed, a.t, R, a.id, a.opacity)),
      notif,
      notch
    };
  }
}
