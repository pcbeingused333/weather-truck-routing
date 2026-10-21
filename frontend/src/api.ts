import type { HeatmapResponse, LonLat, Place, PlanResponse, TripInput } from "./types";

async function request<T>(url: string, init?: RequestInit, signal?: AbortSignal): Promise<T> {
  const resp = await fetch(url, {
    ...init,
    signal,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(formatError(body) || `Request failed (${resp.status})`);
  return body as T;
}

/** DRF validation errors are {field: [messages]}; flatten them into one line. */
function formatError(body: unknown): string {
  if (!body || typeof body !== "object") return "";
  return Object.entries(body as Record<string, unknown>)
    .map(([k, v]) => {
      const msg = Array.isArray(v) ? v.join(" ") : typeof v === "object" ? formatError(v) : String(v);
      return k === "detail" || k === "non_field_errors" ? msg : `${k}: ${msg}`;
    })
    .join(" ");
}

export const geocode = (q: string, signal?: AbortSignal) =>
  request<Place[]>(`/api/geocode?q=${encodeURIComponent(q)}`, undefined, signal);

export const planTrip = (trip: TripInput, signal?: AbortSignal) =>
  request<PlanResponse>(
    "/api/plan",
    {
      method: "POST",
      body: JSON.stringify({
        origin: { lat: trip.origin.lat, lon: trip.origin.lon },
        destination: { lat: trip.destination.lat, lon: trip.destination.lon },
        departure: trip.departure,
        load_lb: trip.load_lb,
        interval_mi: trip.interval_mi,
      }),
    },
    signal,
  );

export const fetchHeatmap = (routes: LonLat[][], start: string, load_lb: number, signal?: AbortSignal) =>
  request<HeatmapResponse>("/api/heatmap", { method: "POST", body: JSON.stringify({ routes, start, load_lb }) }, signal);
