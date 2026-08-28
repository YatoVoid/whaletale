import Link from "next/link";
import { FileText } from "lucide-react";
import { api } from "@/lib/api";
import type { Space } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function ReportsPage() {
  const sites = await api<{ id: string }[]>("/v1/sites");
  const siteId = sites[0]?.id;
  if (!siteId) return null;
  const spaces = (await api<Space[]>(`/v1/sites/${siteId}/spaces`)).filter(
    (s) => !s.archived,
  );

  return (
    <div className="wt-settle max-w-2xl">
      <h1 className="font-serif text-2xl text-ink">Reports</h1>
      <p className="mt-1 text-sm text-ink-soft">
        The one-page space report a leasing agent hands to a prospective tenant.
        It covers the trailing week; a period picker is next.
      </p>
      <ul className="mt-5 flex flex-col">
        {spaces.map((s) => (
          <li
            key={s.id}
            className="wt-hairline flex items-center justify-between border-t py-2.5 text-sm last:border-b"
          >
            <span className="text-ink">
              {s.name} <span className="text-ink-soft">{s.kind}</span>
            </span>
            <Link
              href={`/spaces/${s.id}/report`}
              prefetch={false}
              className="inline-flex items-center gap-1.5 text-ink-soft underline decoration-rule decoration-dotted underline-offset-2 hover:text-ink"
            >
              <FileText size={14} strokeWidth={1.5} />
              PDF
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
