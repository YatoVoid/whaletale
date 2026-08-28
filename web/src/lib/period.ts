import { addDays, isoDay } from "@/lib/format";

/** The trailing 7 days ending today (site-local is close enough for the picker;
 *  the API aligns to the site timezone). */
export function thisWeek(): { start: string; end: string } {
  const end = isoDay(new Date());
  return { start: addDays(end, -6), end };
}

export function previousWeek(week: { start: string; end: string }): {
  start: string;
  end: string;
} {
  return { start: addDays(week.start, -7), end: addDays(week.end, -7) };
}
