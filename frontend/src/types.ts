export type LonLat = [number, number];

export interface Place {
  label: string;
  lat: number;
  lon: number;
}

export interface RiskInfo {
  level: number;
  label: string;
  wind: number;
  rain: number;
  snow: number;
  reasons: string[];
}

export interface Checkpoint {
  mile: number;
  lon: number;
  lat: number;
  eta: string;
  elapsed_s: number;
  weather: { wind_mph: number; gust_mph: number; rain_in_hr: number; snow_in_hr: number };
  risk: RiskInfo;
}

export interface RouteOption {
  index: number;
  rank: number;
  recommended: boolean;
  source: string;
  distance_mi: number;
  duration_s: number;
  avg_risk: number;
  max_risk: number;
  miles_by_level: Record<string, number>;
  notes: string[];
  geometry: LonLat[];
  checkpoints: Checkpoint[];
}

export interface PlanResponse {
  departure: string;
  load_lb: number;
  interval_mi: number;
  recommended_index: number;
  recommendation_reason: string;
  warning: string | null;
  routes: RouteOption[];
}

export interface HeatCell {
  lon: number;
  lat: number;
  score: number[];
  wind: number[];
  rain: number[];
  snow: number[];
}

export interface HeatmapResponse {
  start: string;
  hours: number;
  cells: HeatCell[];
}

export interface TripInput {
  origin: Place;
  destination: Place;
  departure: string; // ISO with offset
  load_lb: number;
  interval_mi: 10 | 25 | 50;
}
