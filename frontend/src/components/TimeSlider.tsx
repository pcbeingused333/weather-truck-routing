import { useEffect } from "react";
import { clock } from "../format";
import { RISK_COLORS, RISK_LEVELS } from "../risk";
import type { HeatCell } from "../types";

interface Props {
  start: string | null;
  hours: number;
  hour: number;
  onHour: (h: number) => void;
  playing: boolean;
  onPlaying: (p: boolean) => void;
  showHeat: boolean;
  onShowHeat: (v: boolean) => void;
  loading: boolean;
  hover: HeatCell | undefined;
}

export default function TimeSlider({ start, hours, hour, onHour, playing, onPlaying, showHeat, onShowHeat, loading, hover }: Props) {
  useEffect(() => {
    if (!playing) return;
    const t = setInterval(() => onHour((hour + 1) % (hours + 1)), 350);
    return () => clearInterval(t);
  }, [playing, hour, hours, onHour]);

  const at = start ? new Date(new Date(start).getTime() + hour * 3600_000) : null;
  return (
    <div className="time-panel">
      <div className="time-row">
        <button className="icon" onClick={() => onPlaying(!playing)} disabled={!start} aria-label={playing ? "Pause" : "Play"}>
          {playing ? "❚❚" : "▶"}
        </button>
        <input
          type="range"
          min={0}
          max={hours}
          value={hour}
          disabled={!start}
          onChange={(e) => onHour(Number(e.target.value))}
          aria-label="Forecast hour"
        />
        <div className="time-label">
          <b>+{hour} h</b>
          <span className="muted">{at ? clock(at) : loading ? "loading forecast…" : "—"}</span>
        </div>
      </div>
      <div className="time-row small">
        <label className="toggle">
          <input type="checkbox" checked={showHeat} onChange={(e) => onShowHeat(e.target.checked)} /> Weather risk heatmap
        </label>
        <div className="legend">
          {RISK_LEVELS.map((l, i) => (
            <span key={l}>
              <i style={{ background: RISK_COLORS[i] }} />
              {l}
            </span>
          ))}
        </div>
        {hover && (
          <div className="hover-readout">
            {hover.wind[hour]} mph · rain {hover.rain[hour].toFixed(2)} · snow {hover.snow[hour].toFixed(2)} in/hr
          </div>
        )}
      </div>
    </div>
  );
}
