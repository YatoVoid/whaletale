// Every number in the console carries its unit and period (spec 13).

export function pct(x: number | null | undefined): string {
  return x == null ? "—" : `${(x * 100).toFixed(1)}%`;
}

export function count(n: number): string {
  return n.toLocaleString("en-US");
}

export function dwell(seconds: number): string {
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

const DAY = { weekday: "short", month: "short", day: "numeric" } as const;

export function dayLabel(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", DAY);
}

export function rangeLabel(startIso: string, endIso: string): string {
  return `${dayLabel(startIso)} – ${dayLabel(endIso)}`;
}

export function isoDay(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + n);
  return isoDay(d);
}
