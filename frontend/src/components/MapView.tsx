import maplibregl, { type GeoJSONSource, type ImageSource, type MapLayerMouseEvent } from "maplibre-gl";
import { useEffect, useMemo, useRef } from "react";
import { clock } from "../format";
import { cumulative, pointAt, slice } from "../geo";
import type { HeatFrames } from "../heatmap";
import { RISK_COLORS, ROUTE_NAMES } from "../risk";
import type { Checkpoint, HeatCell, LonLat, PlanResponse } from "../types";

const STYLE_URL = "https://tiles.openfreemap.org/styles/positron";
const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };
const BLANK_PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=";

interface Props {
  plan: PlanResponse | null;
  selected: number;
  onSelect: (index: number) => void;
  heat: HeatFrames | null;
  hour: number;
  showHeat: boolean;
  truckAt: LonLat | null;
  onHeatHover: (cell: HeatCell | undefined) => void;
}

const colorByLevel: maplibregl.ExpressionSpecification = [
  "match", ["get", "level"], 0, RISK_COLORS[0], 1, RISK_COLORS[1], 2, RISK_COLORS[2], 3, RISK_COLORS[3], RISK_COLORS[4],
];

function checkpointHtml(cp: Checkpoint, route: number): string {
  const w = cp.weather;
  const reasons = cp.risk.reasons.length ? `<div class="pop-reason">${cp.risk.reasons.join(" · ")}</div>` : "";
  return `<div class="pop">
    <div class="pop-head"><span class="dot" style="background:${RISK_COLORS[cp.risk.level]}"></span>
      <b>${cp.risk.label}</b><span class="muted">${ROUTE_NAMES[route]} · mile ${cp.mile.toFixed(0)}</span></div>
    <div>ETA <b>${clock(cp.eta)}</b></div>
    <div class="pop-grid">
      <span>Wind</span><b>${w.wind_mph.toFixed(0)} mph</b><span class="muted">gusts ${w.gust_mph.toFixed(0)}</span>
      <span>Rain</span><b>${w.rain_in_hr.toFixed(2)} in/hr</b><span></span>
      <span>Snow</span><b>${w.snow_in_hr.toFixed(2)} in/hr</b><span></span>
    </div>${reasons}</div>`;
}

export default function MapView({ plan, selected, onSelect, heat, hour, showHeat, truckAt, onHeatHover }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const ready = useRef<Promise<maplibregl.Map> | null>(null);
  const truck = useRef<maplibregl.Marker | null>(null);
  const handlers = useRef({ onSelect, onHeatHover, heat });
  handlers.current = { onSelect, onHeatHover, heat };

  // Create the map once.
  useEffect(() => {
    const map = new maplibregl.Map({ container: container.current!, style: STYLE_URL, center: [-96, 38.5], zoom: 3.6, attributionControl: { compact: true } });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "imperial" }), "bottom-right");
    mapRef.current = map;
    ready.current = new Promise((resolve) =>
      map.on("load", () => {
        map.addSource("heat", { type: "image", url: BLANK_PNG, coordinates: [[-1, 1], [1, 1], [1, -1], [-1, -1]] });
        map.addLayer({ id: "heat", type: "raster", source: "heat", paint: { "raster-opacity": 0.85, "raster-resampling": "linear", "raster-fade-duration": 0 } });
        map.addSource("routes", { type: "geojson", data: EMPTY });
        map.addSource("segments", { type: "geojson", data: EMPTY });
        map.addSource("checkpoints", { type: "geojson", data: EMPTY });
        map.addLayer({
          id: "routes-alt", type: "line", source: "routes", filter: ["!=", ["get", "selected"], true],
          layout: { "line-cap": "round", "line-join": "round" },
          paint: { "line-color": "#6b7280", "line-width": 4, "line-opacity": 0.55, "line-dasharray": [2, 1.5] },
        });
        map.addLayer({
          id: "routes-casing", type: "line", source: "routes", filter: ["==", ["get", "selected"], true],
          layout: { "line-cap": "round", "line-join": "round" },
          paint: { "line-color": "#1f2937", "line-width": 9, "line-opacity": 0.9 },
        });
        map.addLayer({
          id: "segments", type: "line", source: "segments",
          layout: { "line-cap": "round", "line-join": "round" },
          paint: { "line-color": colorByLevel, "line-width": 5 },
        });
        map.addLayer({
          id: "checkpoints", type: "circle", source: "checkpoints",
          paint: {
            "circle-color": colorByLevel,
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, 4, 9, 8],
            "circle-stroke-color": "#fff",
            "circle-stroke-width": 1.5,
          },
        });
        resolve(map);
      }),
    );

    const popup = new maplibregl.Popup({ closeButton: false, offset: 10, maxWidth: "280px" });
    map.on("mouseenter", "checkpoints", (e: MapLayerMouseEvent) => {
      map.getCanvas().style.cursor = "pointer";
      const f = e.features![0];
      const cp: Checkpoint = JSON.parse(f.properties.cp);
      popup.setLngLat([cp.lon, cp.lat]).setHTML(checkpointHtml(cp, f.properties.route)).addTo(map);
    });
    map.on("mouseleave", "checkpoints", () => {
      map.getCanvas().style.cursor = "";
      popup.remove();
    });
    map.on("click", "routes-alt", (e) => handlers.current.onSelect(e.features![0].properties.index));
    map.on("mouseenter", "routes-alt", () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", "routes-alt", () => (map.getCanvas().style.cursor = ""));
    map.on("mousemove", (e) => handlers.current.onHeatHover(handlers.current.heat?.cellAt(e.lngLat.lng, e.lngLat.lat)));
    map.on("mouseout", () => handlers.current.onHeatHover(undefined));

    return () => map.remove();
  }, []);

  // Selected route split into checkpoint-to-checkpoint stretches, coloured by risk.
  const layers = useMemo(() => {
    if (!plan) return null;
    const routes: GeoJSON.Feature[] = plan.routes.map((r) => ({
      type: "Feature",
      properties: { index: r.index, selected: r.index === selected },
      geometry: { type: "LineString", coordinates: r.geometry },
    }));
    const r = plan.routes.find((x) => x.index === selected)!;
    const cum = cumulative(r.geometry);
    const scale = cum[cum.length - 1] / r.distance_mi;
    const cps = r.checkpoints;
    const segments: GeoJSON.Feature[] = cps.slice(1).map((b, i) => ({
      type: "Feature",
      properties: { level: Math.max(cps[i].risk.level, b.risk.level) },
      geometry: { type: "LineString", coordinates: slice(r.geometry, cum, cps[i].mile * scale, b.mile * scale) },
    }));
    const points: GeoJSON.Feature[] = cps.map((cp) => ({
      type: "Feature",
      properties: { level: cp.risk.level, route: r.index, cp: JSON.stringify(cp) },
      geometry: { type: "Point", coordinates: pointAt(r.geometry, cum, cp.mile * scale) },
    }));
    const fc = (features: GeoJSON.Feature[]): GeoJSON.FeatureCollection => ({ type: "FeatureCollection", features });
    return { routes: fc(routes), segments: fc(segments), points: fc(points) };
  }, [plan, selected]);

  useEffect(() => {
    ready.current?.then((map) => {
      (map.getSource("routes") as GeoJSONSource).setData(layers?.routes ?? EMPTY);
      (map.getSource("segments") as GeoJSONSource).setData(layers?.segments ?? EMPTY);
      (map.getSource("checkpoints") as GeoJSONSource).setData(layers?.points ?? EMPTY);
    });
  }, [layers]);

  // Fit the view to a new plan (not on every route selection).
  useEffect(() => {
    if (!plan) return;
    ready.current?.then((map) => {
      const b = new maplibregl.LngLatBounds();
      plan.routes.forEach((r) => r.geometry.forEach((c) => b.extend(c)));
      map.fitBounds(b, { padding: { top: 60, bottom: 140, left: 60, right: 60 }, duration: 800 });
    });
  }, [plan]);

  // Heatmap frame for the current hour: only an image swap.
  useEffect(() => {
    ready.current?.then((map) => {
      const src = map.getSource("heat") as ImageSource;
      if (heat && showHeat) src.updateImage({ url: heat.frames[hour], coordinates: heat.corners });
      map.setLayoutProperty("heat", "visibility", heat && showHeat ? "visible" : "none");
    });
  }, [heat, hour, showHeat]);

  useEffect(() => {
    ready.current?.then((map) => {
      if (!truckAt) {
        truck.current?.remove();
        truck.current = null;
        return;
      }
      if (!truck.current) {
        const el = document.createElement("div");
        el.className = "truck-marker";
        el.textContent = "🚚";
        truck.current = new maplibregl.Marker({ element: el }).setLngLat(truckAt).addTo(map);
      } else truck.current.setLngLat(truckAt);
    });
  }, [truckAt]);

  return <div ref={container} className="map" />;
}
