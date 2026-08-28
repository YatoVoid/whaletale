import Link from "next/link";
import { VacantTag } from "@/components/marks";
import { api } from "@/lib/api";
import type { Space } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function SpacesPage() {
  const sites = await api<{ id: string }[]>("/v1/sites");
  const siteId = sites[0]?.id;
  if (!siteId) return null;
  const spaces = await api<Space[]>(`/v1/sites/${siteId}/spaces`);
  const live = spaces.filter((s) => !s.archived);

  return (
    <div className="wt-settle max-w-3xl">
      <h1 className="font-serif text-2xl text-ink">Spaces</h1>
      <p className="mt-1 text-sm text-ink-soft">
        {live.length} space{live.length === 1 ? "" : "s"} at this site.
      </p>
      <table className="mt-5 w-full border-collapse text-sm">
        <thead>
          <tr className="wt-hairline border-b text-left text-xs text-ink-soft">
            <th className="py-2 pr-3 font-normal">Space</th>
            <th className="py-2 pr-3 font-normal">Kind</th>
            <th className="py-2 font-normal">Occupant today</th>
          </tr>
        </thead>
        <tbody>
          {live.map((s) => (
            <tr key={s.id} className="wt-hairline border-b last:border-0">
              <td className="py-2 pr-3">
                <Link
                  href={`/spaces/${s.id}`}
                  className="text-ink hover:underline hover:decoration-rule hover:underline-offset-2"
                >
                  {s.name}
                </Link>
              </td>
              <td className="py-2 pr-3 text-ink-soft">{s.kind}</td>
              <td className="py-2">
                {s.current_occupant ? (
                  <span className="text-ink">{s.current_occupant}</span>
                ) : (
                  <VacantTag />
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
