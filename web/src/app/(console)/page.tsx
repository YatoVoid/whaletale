import Link from "next/link";
import { AnomalyMark, VacantTag } from "@/components/marks";
import { api, ApiError } from "@/lib/api";
import { count, pct, rangeLabel } from "@/lib/format";
import { previousWeek, thisWeek } from "@/lib/period";
import type { Overview } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function OverviewPage() {
  const sites = await api<{ id: string; name: string }[]>("/v1/sites");
  const siteId = sites[0]?.id;
  if (!siteId) return null;

  const week = thisWeek();
  const prior = previousWeek(week);

  let now: Overview;
  let before: Overview | null = null;
  try {
    now = await api<Overview>(
      `/v1/sites/${siteId}/overview?start=${week.start}&end=${week.end}`,
    );
    before = await api<Overview>(
      `/v1/sites/${siteId}/overview?start=${prior.start}&end=${prior.end}`,
    );
  } catch (e) {
    return (
      <p className="max-w-prose text-sm text-flag">
        Could not load the overview{e instanceof ApiError ? `: ${e.message}` : ""}.
      </p>
    );
  }

  const priorEntries = new Map(before?.spaces.map((s) => [s.space_id, s.entries]));
  const siteEntriesNow = now.spaces.reduce((a, s) => a + s.entries, 0);
  const siteEntriesBefore = before?.spaces.reduce((a, s) => a + s.entries, 0) ?? 0;

  return (
    <div className="wt-settle max-w-4xl">
      <h1 className="font-serif text-2xl text-ink">Overview</h1>
      <p className="mt-1 text-sm text-ink-soft">
        {rangeLabel(now.period_start, now.period_end)} · {now.site.timezone}
      </p>

      <dl className="wt-hairline mt-6 flex flex-wrap gap-x-10 gap-y-3 border-y py-4 text-sm">
        <Fact
          term="Site entries"
          value={`${count(siteEntriesNow)} entries`}
          delta={delta(siteEntriesNow, siteEntriesBefore)}
        />
        <Fact
          term="Edge boxes"
          value={`${now.boxes_online} of ${now.boxes_total} reporting`}
          warn={now.boxes_total > 0 && now.boxes_online < now.boxes_total}
        />
        <Fact
          term="Cameras offline"
          value={
            now.cameras_offline.length === 0
              ? "none"
              : now.cameras_offline.join(", ")
          }
          warn={now.cameras_offline.length > 0}
        />
        <Fact
          term="Vacant spaces"
          value={`${now.vacant_space_ids.length} of ${now.spaces.length}`}
        />
      </dl>

      <h2 className="mt-8 font-serif text-lg text-ink">Spaces by capture rate</h2>
      <p className="mt-1 text-xs text-ink-soft">
        Capture rate separates appeal from location: a stall on a dead corridor
        with a high rate is a good tenant in a bad spot.
      </p>

      <table className="mt-3 w-full border-collapse text-sm">
        <thead>
          <tr className="wt-hairline border-b text-left text-xs text-ink-soft">
            <th className="py-2 pr-3 font-normal">Space</th>
            <th className="py-2 pr-3 font-normal">Occupant</th>
            <th className="py-2 pr-3 text-right font-normal">Entries · this week</th>
            <th className="py-2 pr-3 text-right font-normal">Capture rate</th>
            <th className="py-2 text-right font-normal">vs. prior week</th>
          </tr>
        </thead>
        <tbody>
          {now.spaces.map((s) => {
            const before = priorEntries.get(s.space_id) ?? 0;
            return (
              <tr key={s.space_id} className="wt-hairline border-b last:border-0">
                <td className="py-2 pr-3">
                  <Link
                    href={`/spaces/${s.space_id}`}
                    className="text-ink hover:underline hover:decoration-rule hover:underline-offset-2"
                  >
                    {s.name}
                  </Link>
                  <span className="ml-2 text-xs text-ink-soft">{s.kind}</span>
                </td>
                <td className="py-2 pr-3">
                  {s.is_vacant ? (
                    <VacantTag />
                  ) : (
                    <span className="text-ink">{s.occupant_name}</span>
                  )}
                </td>
                <td className="wt-num py-2 pr-3 text-right text-ink">
                  {count(s.entries)}
                </td>
                <td className="wt-num py-2 pr-3 text-right text-ink">
                  {pct(s.capture_rate)}
                </td>
                <td className="wt-num py-2 text-right text-ink-soft">
                  {delta(s.entries, before)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function delta(now: number, before: number): string {
  if (before === 0) return now === 0 ? "—" : "new";
  const d = Math.round(((now - before) / before) * 100);
  return `${d > 0 ? "+" : ""}${d}%`;
}

function Fact({
  term,
  value,
  delta,
  warn,
}: {
  term: string;
  value: string;
  delta?: string;
  warn?: boolean;
}) {
  return (
    <div>
      <dt className="text-xs text-ink-soft">{term}</dt>
      <dd className="mt-0.5 flex items-baseline gap-2">
        <span className={warn ? "text-flag" : "text-ink"}>{value}</span>
        {delta && delta !== "—" ? (
          <span className="wt-num text-xs text-ink-soft">{delta}</span>
        ) : null}
        {warn ? <AnomalyMark label="attention" /> : null}
      </dd>
    </div>
  );
}
