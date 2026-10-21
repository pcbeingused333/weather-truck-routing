import type { Checkpoint, LonLat } from "./types";

const R_MI = 3958.8;
const rad = (d: number) => (d * Math.PI) / 180;

export function haversine(a: LonLat, b: LonLat): number {
  const dLat = rad(b[1] - a[1]), dLon = rad(b[0] - a[0]);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a[1])) * Math.cos(rad(b[1])) * Math.sin(dLon / 2) ** 2;
  return 2 * R_MI * Math.asin(Math.sqrt(h));
}

export function cumulative(coords: LonLat[]): number[] {
  const out = [0];
  for (let i = 1; i < coords.length; i++) out.push(out[i - 1] + haversine(coords[i - 1], coords[i]));
  return out;
}

/** Index of the first value >= x (cum is ascending). */
function lowerBound(cum: number[], x: number): number {
  let lo = 0, hi = cum.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (cum[mid] < x) lo = mid + 1; else hi = mid;
  }
  return lo;
}

export function pointAt(coords: LonLat[], cum: number[], mile: number): LonLat {
  if (mile <= 0) return coords[0];
  if (mile >= cum[cum.length - 1]) return coords[coords.length - 1];
  const i = lowerBound(cum, mile);
  const t = (mile - cum[i - 1]) / (cum[i] - cum[i - 1] || 1);
  const [x0, y0] = coords[i - 1], [x1, y1] = coords[i];
  return [x0 + t * (x1 - x0), y0 + t * (y1 - y0)];
}

/** Sub-line between two distances along the line. */
export function slice(coords: LonLat[], cum: number[], from: number, to: number): LonLat[] {
  const out = [pointAt(coords, cum, from)];
  for (let i = lowerBound(cum, from); i < coords.length && cum[i] < to; i++) if (cum[i] > from) out.push(coords[i]);
  out.push(pointAt(coords, cum, to));
  return out;
}

/** Where the truck is `elapsedS` seconds after departure, from the checkpoint ETAs. */
export function mileAtElapsed(cps: Checkpoint[], elapsedS: number): number | null {
  if (elapsedS < 0 || elapsedS > cps[cps.length - 1].elapsed_s) return null;
  for (let i = 1; i < cps.length; i++) {
    const a = cps[i - 1], b = cps[i];
    if (elapsedS <= b.elapsed_s) {
      const t = (elapsedS - a.elapsed_s) / (b.elapsed_s - a.elapsed_s || 1);
      return a.mile + t * (b.mile - a.mile);
    }
  }
  return cps[cps.length - 1].mile;
}
