export function duration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return h ? `${h} h ${m.toString().padStart(2, "0")} min` : `${m} min`;
}

const timeFmt = new Intl.DateTimeFormat(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" });

export const clock = (iso: string | Date) => timeFmt.format(typeof iso === "string" ? new Date(iso) : iso);

export const miles = (n: number) => `${n.toLocaleString(undefined, { maximumFractionDigits: 0 })} mi`;

/** Value for <input type="datetime-local"> in the browser's timezone. */
export function toLocalInput(d: Date): string {
  const off = d.getTimezoneOffset() * 60_000;
  return new Date(d.getTime() - off).toISOString().slice(0, 16);
}
