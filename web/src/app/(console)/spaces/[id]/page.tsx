import Link from "next/link";
import { notFound } from "next/navigation";
import { Download, Pencil } from "lucide-react";
import { AnomalyMark, DegradedMark, VacantTag } from "@/components/marks";
import { Metric } from "@/components/metric";
import { OccupancyTimeline } from "@/components/occupancy-timeline";
import { api, ApiError } from "@/lib/api";
import { count, dwell, pct, rangeLabel } from "@/lib/format";
import type { SpaceDetail } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function SpaceDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let detail: SpaceDetail;
  try {
    detail = await api<SpaceDetail>(`/v1/spaces/${id}`);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 403)) notFound();
    throw e;
  }
  const { space, metrics: m, occupancy } = detail;
  const period = rangeLabel(m.period_start, m.period_end);

  return (
    <div className="wt-settle max-w-3xl">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="font-serif text-2xl text-ink">{space.name}</h1>
          <p className="mt-1 text-sm text-ink-soft">
            {space.kind} ·{" "}
            {space.current_occupant ? (
              space.current_occupant
            ) : (
              <VacantTag className="align-middle" />
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href={`/spaces/${id}/zone`}
            className="wt-hairline inline-flex items-center gap-1.5 border px-3 py-1.5 text-sm text-ink-soft hover:text-ink"
          >
            <Pencil size={15} strokeWidth={1.5} />
            Edit zone
          </Link>
          <Link
            href={`/spaces/${id}/report`}
            prefetch={false}
            className="wt-hairline inline-flex items-center gap-1.5 border px-3 py-1.5 text-sm text-ink hover:bg-[color-mix(in_srgb,var(--color-field)_8%,transparent)]"
          >
            <Download size={15} strokeWidth={1.5} />
            Report (PDF)
          </Link>
        </div>
      </div>

      <p className="mt-4 text-xs text-ink-soft">
        {period} · {space.kind} · <DegradedMark count={m.degraded_bucket_count} />
      </p>

      <div className="wt-hairline mt-4 grid grid-cols-2 gap-x-10 gap-y-5 border-y py-5 sm:grid-cols-4">
        <Metric
          label="entries"
          definition="entry"
          value={`${count(m.entries)}`}
          period={period}
          flag={m.entries_is_anomaly ? <AnomalyMark /> : undefined}
        />
        <Metric
          label="traffic share"
          definition="traffic-share"
          value={pct(m.traffic_share)}
          period={period}
        />
        <Metric
          label="capture rate"
          definition="capture-rate"
          value={pct(m.capture_rate)}
          period={
            m.peer_rank != null
              ? `rank ${m.peer_rank} of ${m.peer_count} ${space.kind}s`
              : period
          }
        />
        <Metric
          label="median dwell"
          definition="dwell"
          value={dwell(m.median_dwell_seconds)}
          period={period}
        />
      </div>

      <h2 className="mt-8 font-serif text-lg text-ink">Who held this space</h2>
      <div className="mt-3">
        <OccupancyTimeline spans={occupancy} />
      </div>
    </div>
  );
}
