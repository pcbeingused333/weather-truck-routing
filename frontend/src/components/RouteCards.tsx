import { clock, duration, miles } from "../format";
import { RISK_COLORS, RISK_LEVELS, ROUTE_NAMES } from "../risk";
import type { PlanResponse } from "../types";

interface Props {
  plan: PlanResponse;
  selected: number;
  onSelect: (i: number) => void;
}

export default function RouteCards({ plan, selected, onSelect }: Props) {
  const depart = new Date(plan.departure).getTime();
  return (
    <div className="cards">
      {plan.warning && <div className="banner warn">{plan.warning}</div>}
      <div className="banner rec">
        <b>Recommended: {ROUTE_NAMES[plan.recommended_index]}.</b> {plan.recommendation_reason}
      </div>
      {[...plan.routes]
        .sort((a, b) => a.rank - b.rank)
        .map((r) => (
          <button key={r.index} className={`card ${r.index === selected ? "selected" : ""}`} onClick={() => onSelect(r.index)}>
            <div className="card-head">
              <b>{ROUTE_NAMES[r.index]}</b>
              {r.recommended && <span className="badge">Recommended</span>}
              <span className="badge level" style={{ background: RISK_COLORS[r.max_risk] }}>
                max {RISK_LEVELS[r.max_risk]}
              </span>
            </div>
            <div className="stats">
              <span>{miles(r.distance_mi)}</span>
              <span>{duration(r.duration_s)}</span>
              <span>arrive {clock(new Date(depart + r.duration_s * 1000))}</span>
              <span>avg risk {r.avg_risk.toFixed(2)}</span>
            </div>
            <div className="bar" aria-label="Miles by risk level">
              {RISK_LEVELS.map((lvl, i) => {
                const m = r.miles_by_level[lvl] ?? 0;
                return m > 0 ? (
                  <span key={lvl} style={{ flexGrow: m, background: RISK_COLORS[i] }} title={`${lvl}: ${miles(m)}`} />
                ) : null;
              })}
            </div>
            <div className="bar-legend">
              {RISK_LEVELS.filter((l) => (r.miles_by_level[l] ?? 0) > 0).map((l) => (
                <span key={l}>
                  {l} {miles(r.miles_by_level[l])}
                </span>
              ))}
            </div>
            {r.notes.length > 0 && <div className="muted small">{r.notes.join(" · ")}</div>}
          </button>
        ))}
    </div>
  );
}
