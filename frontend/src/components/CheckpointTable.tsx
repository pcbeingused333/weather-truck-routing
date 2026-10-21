import { clock } from "../format";
import { RISK_COLORS } from "../risk";
import type { RouteOption } from "../types";

export default function CheckpointTable({ route }: { route: RouteOption }) {
  return (
    <details className="checkpoints" open>
      <summary>
        Checkpoints <span className="muted">({route.checkpoints.length})</span>
      </summary>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Mile</th>
              <th>ETA</th>
              <th>Wind</th>
              <th>Rain</th>
              <th>Snow</th>
              <th>Risk</th>
            </tr>
          </thead>
          <tbody>
            {route.checkpoints.map((cp) => (
              <tr key={cp.mile} title={cp.risk.reasons.join(" · ")}>
                <td>{cp.mile.toFixed(0)}</td>
                <td>{clock(cp.eta)}</td>
                <td>{cp.weather.wind_mph.toFixed(0)} mph</td>
                <td>{cp.weather.rain_in_hr.toFixed(2)}</td>
                <td>{cp.weather.snow_in_hr.toFixed(2)}</td>
                <td>
                  <span className="dot" style={{ background: RISK_COLORS[cp.risk.level] }} /> {cp.risk.label}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
