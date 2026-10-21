import { useCallback, useMemo, useRef, useState } from "react";
import { fetchHeatmap, planTrip } from "./api";
import CheckpointTable from "./components/CheckpointTable";
import MapView from "./components/MapView";
import RouteCards from "./components/RouteCards";
import TimeSlider from "./components/TimeSlider";
import TripForm from "./components/TripForm";
import { cumulative, mileAtElapsed, pointAt } from "./geo";
import { buildFrames, type HeatFrames } from "./heatmap";
import type { HeatCell, LonLat, PlanResponse, TripInput } from "./types";

export default function App() {
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [selected, setSelected] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [heat, setHeat] = useState<HeatFrames | null>(null);
  const [heatStart, setHeatStart] = useState<string | null>(null);
  const [heatHours, setHeatHours] = useState(48);
  const [heatLoading, setHeatLoading] = useState(false);
  const [hour, setHour] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [showHeat, setShowHeat] = useState(true);
  const [hover, setHover] = useState<HeatCell | undefined>();
  const inflight = useRef<AbortController | null>(null);

  const submit = useCallback(async (trip: TripInput) => {
    inflight.current?.abort();
    const ctrl = new AbortController();
    inflight.current = ctrl;
    setBusy(true);
    setError(null);
    setPlaying(false);
    try {
      const result = await planTrip(trip, ctrl.signal);
      setPlan(result);
      setSelected(result.recommended_index);
      setHeat(null);
      setHeatStart(null);
      setHour(0);
      setBusy(false);

      // The heatmap is a second request so the routes appear as soon as possible.
      setHeatLoading(true);
      const thinned = result.routes.map((r) => r.geometry.filter((_, i, a) => i % 10 === 0 || i === a.length - 1));
      const grid = await fetchHeatmap(thinned, result.departure, result.load_lb, ctrl.signal);
      setHeat(buildFrames(grid));
      setHeatStart(grid.start);
      setHeatHours(grid.hours);
    } catch (e) {
      if (!ctrl.signal.aborted) {
        // Don't leave a previous plan on screen without its heatmap.
        setPlan(null);
        setHeat(null);
        setHeatStart(null);
        setError((e as Error).message);
      }
    } finally {
      if (inflight.current === ctrl) {
        setBusy(false);
        setHeatLoading(false);
      }
    }
  }, []);

  const route = plan?.routes.find((r) => r.index === selected) ?? null;

  // Truck position on the selected route at the slider's forecast hour.
  const truckAt = useMemo<LonLat | null>(() => {
    if (!route || !heatStart || !plan) return null;
    const elapsed = (new Date(heatStart).getTime() + hour * 3600_000 - new Date(plan.departure).getTime()) / 1000;
    const mile = mileAtElapsed(route.checkpoints, elapsed); // null before departure / after arrival
    if (mile === null) return null;
    const cum = cumulative(route.geometry);
    return pointAt(route.geometry, cum, (mile * cum[cum.length - 1]) / route.distance_mi);
  }, [route, heatStart, hour, plan]);

  return (
    <div className="app">
      <aside className="panel">
        <header>
          <h1>Weather-Aware Truck Routing</h1>
          <p className="muted">Three truck routes, checked against the forecast at the time you'll actually be there.</p>
        </header>
        <TripForm busy={busy} onSubmit={submit} />
        {error && <div className="banner error">{error}</div>}
        {plan && <RouteCards plan={plan} selected={selected} onSelect={setSelected} />}
        {route && <CheckpointTable route={route} />}
        <footer className="muted small">
          Routing: Valhalla truck profile (OSM). Weather: Open-Meteo. Geocoding: Nominatim. Map © OpenFreeMap, OpenStreetMap.
        </footer>
      </aside>
      <main className="map-wrap">
        <MapView
          plan={plan}
          selected={selected}
          onSelect={setSelected}
          heat={heat}
          hour={hour}
          showHeat={showHeat}
          truckAt={truckAt}
          onHeatHover={setHover}
        />
        {plan && (
          <TimeSlider
            start={heatStart}
            hours={heatHours}
            hour={hour}
            onHour={setHour}
            playing={playing}
            onPlaying={setPlaying}
            showHeat={showHeat}
            onShowHeat={setShowHeat}
            loading={heatLoading}
            hover={hover}
          />
        )}
      </main>
    </div>
  );
}
