import { useState } from "react";
import { toLocalInput } from "../format";
import type { Place, TripInput } from "../types";
import PlaceInput from "./PlaceInput";

const EXAMPLES: [Place, Place][] = [
  [
    { label: "Chicago, Illinois, United States", lat: 41.8756, lon: -87.6244 },
    { label: "Denver, Colorado, United States", lat: 39.7392, lon: -104.9849 },
  ],
  [
    { label: "Dallas, Texas, United States", lat: 32.7763, lon: -96.7969 },
    { label: "Atlanta, Georgia, United States", lat: 33.749, lon: -84.3902 },
  ],
];

interface Props {
  busy: boolean;
  onSubmit: (trip: TripInput) => void;
}

function defaultDeparture(): string {
  const d = new Date(Date.now() + 60 * 60 * 1000);
  d.setMinutes(0, 0, 0);
  return toLocalInput(d);
}

export default function TripForm({ busy, onSubmit }: Props) {
  const [origin, setOrigin] = useState<Place | null>(EXAMPLES[0][0]);
  const [destination, setDestination] = useState<Place | null>(EXAMPLES[0][1]);
  const [departure, setDeparture] = useState(defaultDeparture);
  const [load, setLoad] = useState("38000");
  const [interval, setInterval] = useState<TripInput["interval_mi"]>(25);

  const loadLb = Number(load);
  const valid = origin && destination && departure && Number.isFinite(loadLb) && loadLb >= 0 && loadLb <= 120000;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    onSubmit({
      origin: origin!,
      destination: destination!,
      departure: new Date(departure).toISOString(),
      load_lb: loadLb,
      interval_mi: interval,
    });
  };

  return (
    <form className="trip-form" onSubmit={submit}>
      <PlaceInput label="Origin" value={origin} onChange={setOrigin} placeholder="City or address" />
      <PlaceInput label="Destination" value={destination} onChange={setDestination} placeholder="City or address" />
      <div className="row">
        <label className="field">
          <span>Departure</span>
          <input type="datetime-local" value={departure} min={toLocalInput(new Date())} onChange={(e) => setDeparture(e.target.value)} required />
        </label>
        <label className="field narrow">
          <span>Load (lb)</span>
          <input type="number" min={0} max={120000} step={500} value={load} onChange={(e) => setLoad(e.target.value)} required />
        </label>
      </div>
      <div className="row between">
        <div className="field">
          <span>Weather every</span>
          <div className="segmented" role="radiogroup">
            {([10, 25, 50] as const).map((v) => (
              <button type="button" key={v} role="radio" aria-checked={interval === v} className={interval === v ? "on" : ""} onClick={() => setInterval(v)}>
                {v} mi
              </button>
            ))}
          </div>
        </div>
        <button className="primary" type="submit" disabled={!valid || busy}>
          {busy ? "Planning…" : "Plan routes"}
        </button>
      </div>
      <div className="examples">
        Try:{" "}
        {EXAMPLES.map(([o, d]) => (
          <button type="button" className="link" key={o.label} onClick={() => { setOrigin(o); setDestination(d); }}>
            {o.label.split(",")[0]} → {d.label.split(",")[0]}
          </button>
        ))}
      </div>
    </form>
  );
}
