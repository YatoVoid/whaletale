import { api } from "@/lib/api";
import { auth } from "@/lib/auth";
import type { Site } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const [sites, session] = await Promise.all([api<Site[]>("/v1/sites"), auth()]);

  return (
    <div className="wt-settle max-w-2xl">
      <h1 className="font-serif text-2xl text-ink">Settings</h1>

      <h2 className="mt-6 font-serif text-lg text-ink">Account</h2>
      <dl className="wt-hairline mt-2 border-t py-3 text-sm">
        <div className="flex gap-4 py-1">
          <dt className="w-28 text-ink-soft">Signed in as</dt>
          <dd className="text-ink">{session?.user?.email ?? "unknown"}</dd>
        </div>
      </dl>

      <h2 className="mt-6 font-serif text-lg text-ink">Sites</h2>
      <ul className="wt-hairline mt-2 border-t text-sm">
        {sites.map((s) => (
          <li key={s.id} className="wt-hairline flex justify-between border-b py-2">
            <span className="text-ink">{s.name}</span>
            <span className="text-ink-soft">{s.timezone}</span>
          </li>
        ))}
      </ul>

      <p className="mt-6 max-w-prose text-sm text-ink-soft">
        Camera onboarding, operating hours, user management, and billing land in
        M7–M9. Edge boxes are paired on the cloud with
        <code className="wt-id"> pair_edge_box()</code> for now.
      </p>
    </div>
  );
}
