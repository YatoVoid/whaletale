import { auth } from "@/lib/auth";

export const dynamic = "force-dynamic";

const BASE = process.env.WHALETALE_API_URL ?? "http://127.0.0.1:8000";

/** Streams the space's one-pager PDF (M3), fetched server-side so the operator
 *  token never reaches the browser. */
export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const token = (await auth())?.apiToken;
  if (!token) return new Response("Not signed in", { status: 401 });

  const upstream = await fetch(`${BASE}/v1/spaces/${id}/report.pdf`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!upstream.ok || !upstream.body) {
    return new Response("Report unavailable", { status: upstream.status || 502 });
  }
  return new Response(upstream.body, {
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition":
        upstream.headers.get("content-disposition") ?? 'inline; filename="report.pdf"',
    },
  });
}
