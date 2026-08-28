"use server";

import { revalidatePath } from "next/cache";
import { api, ApiError } from "@/lib/api";

export async function pairBox(
  siteId: string,
  name: string,
): Promise<{ ok: true; token: string } | { ok: false; error: string }> {
  try {
    const r = await api<{ pairing_token: string }>(
      `/v1/sites/${siteId}/edge-boxes`,
      { method: "POST", body: { name: name || null } },
    );
    revalidatePath("/settings");
    return { ok: true, token: r.pairing_token };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof ApiError ? e.message : "Could not pair the box.",
    };
  }
}

export async function addCamera(
  siteId: string,
  name: string,
  resolution: string,
  fps: number,
): Promise<{ ok: boolean; error?: string }> {
  try {
    await api(`/v1/sites/${siteId}/cameras`, {
      method: "POST",
      body: { name, resolution, fps_target: fps },
    });
    revalidatePath("/settings");
    return { ok: true };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof ApiError ? e.message : "Could not add the camera.",
    };
  }
}

export async function previewBilling(
  siteId: string,
): Promise<{ ok: true; preview: import("@/lib/types").ChangePreview } | { ok: false; error: string }> {
  try {
    const preview = await api<import("@/lib/types").ChangePreview>(
      `/v1/sites/${siteId}/billing/preview`,
    );
    return { ok: true, preview };
  } catch (e) {
    return { ok: false, error: e instanceof ApiError ? e.message : "Preview failed." };
  }
}

export async function applyBilling(
  siteId: string,
): Promise<{ ok: boolean; error?: string }> {
  try {
    await api(`/v1/sites/${siteId}/billing/apply`, { method: "POST" });
    revalidatePath("/settings");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof ApiError ? e.message : "Apply failed." };
  }
}
