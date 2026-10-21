export const RISK_LEVELS = ["Low", "Moderate", "High", "Severe", "No Travel"] as const;

export const RISK_COLORS = ["#2e9d5b", "#e3b505", "#f07c1b", "#d7263d", "#6a1b9a"];

/** RGBA for a continuous 0-4 heatmap score: band color, more opaque as risk rises. */
const STOPS: [number, [number, number, number, number]][] = [
  [0, [46, 157, 91, 0.0]],
  [0.6, [46, 157, 91, 0.18]],
  [1, [227, 181, 5, 0.45]],
  [2, [240, 124, 27, 0.6]],
  [3, [215, 38, 61, 0.7]],
  [4, [106, 27, 154, 0.8]],
];

export function scoreColor(score: number): [number, number, number, number] {
  if (score <= STOPS[0][0]) return STOPS[0][1];
  for (let i = 1; i < STOPS.length; i++) {
    const [x1, c1] = STOPS[i];
    if (score <= x1) {
      const [x0, c0] = STOPS[i - 1];
      const t = (score - x0) / (x1 - x0);
      return c0.map((v, k) => v + t * (c1[k] - v)) as [number, number, number, number];
    }
  }
  return STOPS[STOPS.length - 1][1];
}

export const ROUTE_NAMES = ["Route A", "Route B", "Route C"];
