import { redirect } from "next/navigation";
import { api } from "@/lib/api";
import { addDays, isoDay } from "@/lib/format";
import type { Occupant, ScheduleGrid } from "@/lib/types";
import { ScheduleBoard } from "./schedule-board";

export const dynamic = "force-dynamic";

function mondayOf(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  const back = (d.getDay() + 6) % 7; // 0 = Monday
  return addDays(iso, -back);
}

export default async function SchedulePage({
  searchParams,
}: {
  searchParams: Promise<{ from?: string }>;
}) {
  const sites = await api<{ id: string; name: string }[]>("/v1/sites");
  const siteId = sites[0]?.id;
  if (!siteId) redirect("/");

  const params = await searchParams;
  const from = mondayOf(params.from ?? isoDay(new Date()));
  const to = addDays(from, 13); // two weeks

  const [grid, occupants] = await Promise.all([
    api<ScheduleGrid>(`/v1/sites/${siteId}/schedule?start=${from}&end=${to}`),
    api<Occupant[]>(`/v1/sites/${siteId}/occupants`),
  ]);

  return (
    <ScheduleBoard
      grid={grid}
      occupants={occupants.filter((o) => !o.archived)}
      from={from}
      prev={addDays(from, -14)}
      next={addDays(from, 14)}
    />
  );
}
