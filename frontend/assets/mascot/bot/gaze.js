// Ported from jeremy-prt/bloub (MIT License) — https://github.com/jeremy-prt/bloub
import { clamp, easings } from './math.js';

export const YAW_MAX = 16;
export const PITCH_MAX = 13;
export const PITCH = 10;
export const TURN = 26;
export const SPIN = 360;
export const TURN_TIME = 1.1;

export const tourLook = (t) => ({
  yaw: 0,
  pitch: 0,
  mix: 0,
  spin: SPIN * (1 - easings.easeInOutCubic(clamp(t / 1.5))),
  wander: 1
});

// tour goes 0 -> 1: raises `mix` (how much the pointer commands direction) while
// melting `spin` (the turn taken on arrival) at the same time.
export function lookTarget({ nx, ny, tour, pointer }) {
  return {
    yaw: -TURN + nx * YAW_MAX,
    pitch: PITCH - ny * PITCH_MAX,
    mix: tour,
    spin: SPIN * (1 - tour),
    wander: pointer ? 0 : 1
  };
}
