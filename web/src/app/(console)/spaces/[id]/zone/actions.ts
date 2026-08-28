"use server";

import { revalidatePath } from "next/cache";
import { api, ApiError } from "@/lib/api";
import type { ReshapeOut } from "@/lib/types";

export type SaveZoneResult =
  | { ok: true; message: string; versionNumber: number }
  | { ok: false; error: string };

export async function saveZone(
  spaceId: string,
  polygon: [number, number][],
  createdBy: string,
): Promise<SaveZoneResult> {
  if (polygon.length < 3) {
    return { ok: false, error: "A zone needs at least three points." };
  }
  try {
    const out = await api<ReshapeOut>(`/v1/spaces/${spaceId}/zone-versions/reshape`, {
      method: "POST",
      body: { polygon, created_by: createdBy },
    });
    revalidatePath(`/spaces/${spaceId}`);
    return { ok: true, message: out.message, versionNumber: out.version_number };
  } catch (e) {
    return {
      ok: false,
      error:
        e instanceof ApiError
          ? e.message
          : "Could not save the zone. Try again.",
    };
  }
}
