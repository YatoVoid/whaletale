"use server";

import { revalidatePath } from "next/cache";
import { api, ApiError } from "@/lib/api";
import type { ReshapeOut } from "@/lib/types";

type OverlapSpace = { space_id: string; space_name: string; iou: number };

export type SaveZoneResult =
  | { ok: true; message: string; versionNumber: number }
  | { ok: false; error: string }
  | { ok: false; overlap: OverlapSpace[]; message: string };

function overlapDetail(e: ApiError): { message: string; overlap: OverlapSpace[] } | null {
  const d = e.detail;
  if (
    d &&
    typeof d === "object" &&
    "error" in d &&
    (d as { error: unknown }).error === "zone_overlap"
  ) {
    const { message, overlapping_spaces } = d as unknown as {
      message: string;
      overlapping_spaces: OverlapSpace[];
    };
    return { message, overlap: overlapping_spaces };
  }
  return null;
}

export async function saveZone(
  spaceId: string,
  polygon: [number, number][],
  createdBy: string,
  baseVersionId: string | null,
  acknowledgeOverlap = false,
): Promise<SaveZoneResult> {
  if (polygon.length < 3) {
    return { ok: false, error: "A zone needs at least three points." };
  }
  try {
    const out = await api<ReshapeOut>(`/v1/spaces/${spaceId}/zone-versions/reshape`, {
      method: "POST",
      body: {
        polygon,
        created_by: createdBy,
        base_version_id: baseVersionId,
        acknowledge_overlap: acknowledgeOverlap,
      },
    });
    revalidatePath(`/spaces/${spaceId}`);
    return { ok: true, message: out.message, versionNumber: out.version_number };
  } catch (e) {
    if (e instanceof ApiError) {
      const ov = overlapDetail(e);
      if (ov) return { ok: false, ...ov };
      return { ok: false, error: e.message };
    }
    return { ok: false, error: "Could not save the zone. Try again." };
  }
}
