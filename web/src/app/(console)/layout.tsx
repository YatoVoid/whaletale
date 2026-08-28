import { redirect } from "next/navigation";
import { NavRail } from "@/components/nav-rail";
import { SignOutButton } from "@/components/sign-out-button";
import { api } from "@/lib/api";
import { auth } from "@/lib/auth";
import type { Site } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function ConsoleLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();
  if (!session?.apiToken) redirect("/sign-in");

  let sites: Site[] = [];
  try {
    sites = await api<Site[]>("/v1/sites");
  } catch {
    sites = [];
  }
  const site = sites[0];

  return (
    <div className="flex min-h-dvh">
      <NavRail siteName={site?.name ?? "No site"} />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="wt-hairline flex items-center justify-between border-b px-6 py-3">
          <span className="text-xs text-ink-soft">
            {site ? `${site.name} · ${site.timezone}` : "Not linked to a site"}
          </span>
          <SignOutButton email={session.user?.email ?? ""} />
        </header>
        <main className="min-w-0 flex-1 px-6 py-7">
          {site ? (
            children
          ) : (
            <p className="max-w-prose text-sm text-ink-soft">
              This account is not linked to a site yet. Ask an administrator to add
              you in Settings once that screen ships, or link the account directly
              in <code className="wt-id">operator_user_sites</code>.
            </p>
          )}
        </main>
      </div>
    </div>
  );
}
