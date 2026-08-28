"use server";

import { revalidatePath } from "next/cache";
import { api, ApiError } from "@/lib/api";

export type AssignInput = {
  spaceIds: string[];
  occupantId: string;
  kind: "permanent" | "recurring" | "one_off";
  startsOn: string;
  endsOn?: string | null;
  weekdays?: string[]; // ["MO","SA"] for recurring
  dailyStart?: string | null; // "HH:MM"
  dailyEnd?: string | null;
};

export type AssignResult =
  | { ok: true; assigned: number }
  | { ok: false; error: string; conflicts?: string[] };

export async function assignTenancy(input: AssignInput): Promise<AssignResult> {
  if (input.spaceIds.length === 0) return { ok: false, error: "No cells selected." };

  const body: Record<string, unknown> = {
    occupant_id: input.occupantId,
    kind: input.kind,
    starts_on: input.startsOn,
    ends_on: input.kind === "one_off" ? input.startsOn : (input.endsOn ?? null),
  };
  if (input.kind === "recurring") {
    const days = (input.weekdays ?? []).join(",");
    if (!days) return { ok: false, error: "Pick at least one weekday." };
    body.recurrence_rule = `FREQ=WEEKLY;BYDAY=${days}`;
    body.daily_start_time = input.dailyStart || null;
    body.daily_end_time = input.dailyEnd || null;
  }

  let assigned = 0;
  for (const spaceId of input.spaceIds) {
    try {
      await api(`/v1/spaces/${spaceId}/tenancies`, { method: "POST", body });
      assigned += 1;
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        let conflicts: string[] | undefined;
        try {
          const parsed = JSON.parse(e.message) as { conflicting_tenancy_ids?: string[] };
          conflicts = parsed.conflicting_tenancy_ids;
        } catch {
          /* message was plain */
        }
        return {
          ok: false,
          error:
            assigned > 0
              ? `Assigned ${assigned}, then hit a conflict — this space already has an overlapping tenancy.`
              : "This space already has an overlapping tenancy for that period.",
          conflicts,
        };
      }
      return {
        ok: false,
        error: e instanceof ApiError ? e.message : "Could not save the assignment.",
      };
    }
  }
  revalidatePath("/schedule");
  revalidatePath("/");
  return { ok: true, assigned };
}

export async function removeTenancy(tenancyId: string): Promise<AssignResult> {
  try {
    await api(`/v1/tenancies/${tenancyId}`, { method: "DELETE" });
  } catch (e) {
    return {
      ok: false,
      error: e instanceof ApiError ? e.message : "Could not remove the tenancy.",
    };
  }
  revalidatePath("/schedule");
  revalidatePath("/");
  return { ok: true, assigned: 0 };
}
