import type { OccupancySpan } from "@/lib/types";
import { dayLabel } from "@/lib/format";

/** Contiguous occupant runs over the report period. Vacant spans are hatched —
 *  a state, not a gap (spec 13). Carries the M3 report's flat-ink chart style. */
export function OccupancyTimeline({ spans }: { spans: OccupancySpan[] }) {
  if (spans.length === 0) {
    return <p className="text-sm text-ink-soft">No observed days in this period.</p>;
  }
  const start = new Date(`${spans[0]!.start}T00:00:00`).getTime();
  const end = new Date(`${spans[spans.length - 1]!.end}T00:00:00`).getTime();
  const totalDays = Math.max(1, (end - start) / 86_400_000 + 1);

  return (
    <div>
      <div className="wt-hairline flex h-8 w-full overflow-hidden border">
        {spans.map((s, i) => {
          const days =
            (new Date(`${s.end}T00:00:00`).getTime() -
              new Date(`${s.start}T00:00:00`).getTime()) /
              86_400_000 +
            1;
          const pct = (days / totalDays) * 100;
          return (
            <div
              key={i}
              style={{ width: `${pct}%` }}
              className={
                s.occupant_name
                  ? "flex items-center justify-center border-r border-[var(--color-paper)] bg-field text-[11px] text-paper last:border-0"
                  : "wt-vacant flex items-center justify-center border-r border-[var(--color-paper)] text-[11px] text-ink-soft last:border-0"
              }
              title={s.occupant_name ?? "vacant"}
            >
              <span className="line-clamp-1 px-1">
                {s.occupant_name ?? "vacant"}
              </span>
            </div>
          );
        })}
      </div>
      <div className="mt-1 flex justify-between text-xs text-ink-soft">
        <span>{dayLabel(spans[0]!.start)}</span>
        <span>{dayLabel(spans[spans.length - 1]!.end)}</span>
      </div>
    </div>
  );
}
