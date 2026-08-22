// Ported from jeremy-prt/bloub (MIT License) — https://github.com/jeremy-prt/bloub
import { clamp, createRng, loopNoise } from './math.js';

// Eyes are painted on a sphere, not laid flat. Each eye gets the sphere's tangent
// frame, projected orthographically — the compression and tilt fall out naturally.

export const EYE_SPLIT = 15.46;
export const EYE_W = 0.186;
export const EYE_H = 0.412;

export const REST_GAZE = { yaw: 28.49, pitch: 28.62, roll: -13 };

const deg = (d) => (d * Math.PI) / 180;

function spin(u, v, angle) {
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  return [
    [u[0] * c + v[0] * s, u[1] * c + v[1] * s, u[2] * c + v[2] * s],
    [v[0] * c - u[0] * s, v[1] * c - u[1] * s, v[2] * c - u[2] * s]
  ];
}

// Screen space: x right, y down, z toward viewer. Index 0 = inner eye, 1 = outer.
export function eyePoses(gaze, scale, split = EYE_SPLIT) {
  let f = [0, 0, 1];
  let right = [1, 0, 0];
  let down = [0, 1, 0];

  [f, right] = spin(f, right, deg(gaze.yaw));
  [down, f] = spin(down, f, deg(gaze.pitch));
  [right, down] = spin(right, down, deg(gaze.roll));

  const build = (side) => {
    const [ef, er] = spin(f, right, deg(split * side));
    return { x: ef[0] * scale, y: ef[1] * scale, a: er[0], b: er[1], c: down[0], d: down[1], depth: ef[2] };
  };

  return [build(-1), build(1)];
}

const BLINK_RNG = createRng(0x5eed);
const BLINKS = (() => {
  const out = [];
  let t = 1.4;
  while (t < 900) {
    out.push(t);
    t += 1.9 + BLINK_RNG() * 2.7;
    if (BLINK_RNG() < 0.18) {
      out.push(t);
      t += 0.24;
    }
  }
  return out;
})();

const BLINK_DUR = 0.18;

function blinkLid(t) {
  for (let i = 0; i < BLINKS.length; i++) {
    const start = BLINKS[i];
    if (t < start) break;
    const k = (t - start) / BLINK_DUR;
    if (k >= 0 && k <= 1) {
      return k < 0.45 ? 1 - k / 0.45 : (k - 0.45) / 0.55;
    }
  }
  return 1;
}

export function liveliness(t, opt = {}) {
  const { wander = 1, blink = true, float = true } = opt;
  return {
    dYaw: (loopNoise(t, 11.3, 0.4) * 5.5 + loopNoise(t, 3.7, 2.1) * 1.6) * wander,
    dPitch: (loopNoise(t, 9.1, 1.3) * 4.2 + loopNoise(t, 4.3, 0.7) * 1.3) * wander,
    dRoll: loopNoise(t, 13.7, 3.2) * 2.2 * wander,
    lid: blink ? blinkLid(t) : 1,
    driftX: float ? loopNoise(t, 7.9, 1.9) * 0.006 : 0,
    driftY: float ? loopNoise(t, 5.3, 0.3) * 0.007 : 0,
    breath: float ? 1 + Math.sin((t / 3.4) * Math.PI * 2) * 0.005 : 1
  };
}

// Blink is a vertical squash in screen space around the eye's center, applied
// after the tangent matrix — not a shrink along the capsule's own tilted axis.
export function blinkScale(lid) {
  return 0.06 + 0.94 * clamp(lid);
}
