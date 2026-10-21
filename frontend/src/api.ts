import type { HeatmapResponse, LonLat, Place, PlanResponse, TripInput } from "./types";

/** What the backend asks for when Open-Meteo rate-limits the server (HTTP 503, code "weather_from_browser"). */
interface WeatherRequest {
  url: string;
  params: Record<string, string>;
  points: { key: string; lon: number; lat: number }[];
  per_request: number;
}

class NeedBrowserWeather extends Error {
  constructor(readonly weatherRequest: WeatherRequest) {
    super("The weather service is rate-limiting the server.");
  }
}

async function request<T>(url: string, init?: RequestInit, signal?: AbortSignal): Promise<T> {
  const resp = await fetch(url, {
    ...init,
    signal,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    if (body?.code === "weather_from_browser" && body.weather_request) throw new NeedBrowserWeather(body.weather_request);
    throw new Error(formatError(body) || `Request failed (${resp.status})`);
  }
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

/**
 * Fetch the forecasts the backend couldn't get, from this browser (the user's own IP),
 * keyed the way the backend expects. Only the first timestamp is kept: the backend
 * uses it to check the window, and the values are hourly from there.
 */
async function fetchBrowserWeather(req: WeatherRequest, signal?: AbortSignal): Promise<Record<string, unknown>> {
  const chunks: WeatherRequest["points"][] = [];
  for (let i = 0; i < req.points.length; i += req.per_request) chunks.push(req.points.slice(i, i + req.per_request));
  const out: Record<string, unknown> = {};
  await Promise.all(
    chunks.map(async (chunk) => {
      const qs = new URLSearchParams({
        ...req.params,
        latitude: chunk.map((p) => p.lat).join(","),
        longitude: chunk.map((p) => p.lon).join(","),
      });
      const resp = await fetch(`${req.url}?${qs}`, { signal });
      if (!resp.ok) throw new Error("The weather service is unavailable right now. Please try again later.");
      const data = await resp.json();
      const items: { hourly: Record<string, unknown[]> }[] = Array.isArray(data) ? data : [data];
      if (items.length !== chunk.length) throw new Error("The weather service returned an unexpected response.");
      chunk.forEach((p, i) => {
        const hourly = items[i].hourly;
        out[p.key] = { hourly: { ...hourly, time: hourly.time.slice(0, 1) } };
      });
    }),
  );
  return out;
}

/** POST to the backend; if it asks for browser-fetched weather, fetch it and retry once. */
async function postWithWeather<T>(url: string, payload: object, signal?: AbortSignal): Promise<T> {
  const post = (body: object) => request<T>(url, { method: "POST", body: JSON.stringify(body) }, signal);
  try {
    return await post(payload);
  } catch (e) {
    if (!(e instanceof NeedBrowserWeather)) throw e;
    const weather = await fetchBrowserWeather(e.weatherRequest, signal);
    return post({ ...payload, weather });
  }
}

export const geocode = (q: string, signal?: AbortSignal) =>
  request<Place[]>(`/api/geocode?q=${encodeURIComponent(q)}`, undefined, signal);

export const planTrip = (trip: TripInput, signal?: AbortSignal) =>
  postWithWeather<PlanResponse>(
    "/api/plan",
    {
      origin: { lat: trip.origin.lat, lon: trip.origin.lon },
      destination: { lat: trip.destination.lat, lon: trip.destination.lon },
      departure: trip.departure,
      load_lb: trip.load_lb,
      interval_mi: trip.interval_mi,
    },
    signal,
  );

export const fetchHeatmap = (routes: LonLat[][], start: string, load_lb: number, signal?: AbortSignal) =>
  postWithWeather<HeatmapResponse>("/api/heatmap", { routes, start, load_lb }, signal);
