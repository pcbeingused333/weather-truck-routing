import { scoreColor } from "./risk";
import type { HeatCell, HeatmapResponse } from "./types";

/**
 * Rasterises the forecast grid into one small PNG per hour.
 *
 * The backend returns points on a regular lon/lat lattice inside the trip
 * corridor. We bilinearly interpolate between lattice points (fading out where
 * neighbours are missing, so the corridor has soft edges) and space the image
 * rows evenly in Web Mercator, which is how MapLibre stretches an image source.
 * Frames are built once per forecast, so moving the slider only swaps an image.
 */
export interface HeatFrames {
  /** [top-left, top-right, bottom-right, bottom-left] as MapLibre expects */
  corners: [[number, number], [number, number], [number, number], [number, number]];
  frames: string[];
  /** nearest lattice cell for hover readouts */
  cellAt: (lon: number, lat: number) => HeatCell | undefined;
}

const PX_PER_CELL = 6;

const mercY = (lat: number) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
const invMercY = (y: number) => (360 / Math.PI) * Math.atan(Math.exp(y)) - 90;

function latticeStep(cells: HeatCell[]): number {
  const lats = [...new Set(cells.map((c) => c.lat))].sort((a, b) => a - b);
  let step = Infinity;
  for (let i = 1; i < lats.length; i++) step = Math.min(step, lats[i] - lats[i - 1]);
  return Number.isFinite(step) ? step : 0.5;
}

export function buildFrames(data: HeatmapResponse): HeatFrames {
  const { cells } = data;
  const step = latticeStep(cells);
  const key = (i: number, j: number) => `${i},${j}`;
  const grid = new Map<string, HeatCell>();
  let i0 = Infinity, i1 = -Infinity, j0 = Infinity, j1 = -Infinity;
  for (const c of cells) {
    const i = Math.round(c.lon / step), j = Math.round(c.lat / step);
    grid.set(key(i, j), c);
    i0 = Math.min(i0, i); i1 = Math.max(i1, i); j0 = Math.min(j0, j); j1 = Math.max(j1, j);
  }
  // One empty lattice row/column of padding so edges fade instead of clipping.
  i0 -= 1; i1 += 1; j0 -= 1; j1 += 1;

  const west = i0 * step, east = i1 * step, south = j0 * step, north = j1 * step;
  const width = (i1 - i0) * PX_PER_CELL;
  const height = (j1 - j0) * PX_PER_CELL;
  const yTop = mercY(north), yBottom = mercY(south);

  // Precompute, per pixel, the four neighbours and their bilinear weights; this
  // is the same for every hour, so each frame is just a weighted sum.
  const n = width * height;
  const nbr: (HeatCell | undefined)[] = new Array(n * 4);
  const wts = new Float32Array(n * 4);
  for (let py = 0; py < height; py++) {
    const lat = invMercY(yTop + ((py + 0.5) / height) * (yBottom - yTop));
    const fj = lat / step - j0;
    const jj = Math.floor(fj), tj = fj - jj;
    for (let px = 0; px < width; px++) {
      const fi = (px + 0.5) / PX_PER_CELL;
      const ii = Math.floor(fi), ti = fi - ii;
      const p = (py * width + px) * 4;
      const corners: [number, number, number][] = [
        [ii, jj, (1 - ti) * (1 - tj)], [ii + 1, jj, ti * (1 - tj)],
        [ii, jj + 1, (1 - ti) * tj], [ii + 1, jj + 1, ti * tj],
      ];
      corners.forEach(([ci, cj, w], k) => {
        nbr[p + k] = grid.get(key(ci + i0, cj + j0));
        wts[p + k] = w;
      });
    }
  }

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d")!;
  const frames: string[] = [];
  for (let h = 0; h <= data.hours; h++) {
    const img = ctx.createImageData(width, height);
    for (let p = 0; p < n; p++) {
      let sum = 0, wsum = 0;
      for (let k = 0; k < 4; k++) {
        const c = nbr[p * 4 + k];
        if (c) { sum += c.score[h] * wts[p * 4 + k]; wsum += wts[p * 4 + k]; }
      }
      if (wsum === 0) continue;
      const [r, g, b, a] = scoreColor(sum / wsum);
      const o = p * 4;
      img.data[o] = r; img.data[o + 1] = g; img.data[o + 2] = b;
      img.data[o + 3] = Math.round(a * Math.min(1, wsum * 1.6) * 255);
    }
    ctx.putImageData(img, 0, 0);
    frames.push(canvas.toDataURL("image/png"));
  }

  return {
    corners: [[west, north], [east, north], [east, south], [west, south]],
    frames,
    cellAt: (lon, lat) => grid.get(key(Math.round(lon / step), Math.round(lat / step))),
  };
}
