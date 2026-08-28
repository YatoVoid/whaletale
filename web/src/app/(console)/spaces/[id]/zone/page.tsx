import { notFound } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { auth } from "@/lib/auth";
import type { SpaceDetail } from "@/lib/types";
import { ZoneEditor } from "./zone-editor";

export const dynamic = "force-dynamic";

export default async function ZonePage({
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
  const email = (await auth())?.user?.email ?? "operator";

  return (
    <ZoneEditor
      spaceId={id}
      spaceName={detail.space.name}
      initial={[]}
      createdBy={email}
    />
  );
}
