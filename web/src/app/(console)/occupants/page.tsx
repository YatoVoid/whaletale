import { revalidatePath } from "next/cache";
import { api } from "@/lib/api";
import type { Occupant } from "@/lib/types";
import { NewOccupant } from "./new-occupant";

export const dynamic = "force-dynamic";

export default async function OccupantsPage() {
  const sites = await api<{ id: string }[]>("/v1/sites");
  const siteId = sites[0]?.id;
  if (!siteId) return null;
  const occupants = await api<Occupant[]>(`/v1/sites/${siteId}/occupants`);
  const live = occupants.filter((o) => !o.archived);

  async function create(name: string, email: string, phone: string) {
    "use server";
    await api(`/v1/sites/${siteId}/occupants`, {
      method: "POST",
      body: {
        name,
        contact_email: email || null,
        contact_phone: phone || null,
      },
    });
    revalidatePath("/occupants");
  }

  return (
    <div className="wt-settle max-w-3xl">
      <h1 className="font-serif text-2xl text-ink">Occupants</h1>
      <p className="mt-1 text-sm text-ink-soft">
        The vendors and tenants who hold spaces. Renaming one updates its history
        everywhere.
      </p>

      <table className="mt-5 w-full border-collapse text-sm">
        <thead>
          <tr className="wt-hairline border-b text-left text-xs text-ink-soft">
            <th className="py-2 pr-3 font-normal">Name</th>
            <th className="py-2 pr-3 font-normal">Contact</th>
            <th className="py-2 font-normal">Spaces held</th>
          </tr>
        </thead>
        <tbody>
          {live.length === 0 && (
            <tr>
              <td colSpan={3} className="py-3 text-sm text-ink-soft">
                No occupants yet.
              </td>
            </tr>
          )}
          {live.map((o) => (
            <tr key={o.id} className="wt-hairline border-b last:border-0">
              <td className="py-2 pr-3 text-ink">{o.name}</td>
              <td className="py-2 pr-3 text-ink-soft">
                {o.contact_email ?? o.contact_phone ?? "—"}
              </td>
              <td className="py-2 text-ink-soft">
                {o.space_names.length ? o.space_names.join(", ") : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <NewOccupant action={create} />
    </div>
  );
}
