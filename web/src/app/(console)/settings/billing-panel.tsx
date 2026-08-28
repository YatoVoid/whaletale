"use client";

import { useState, useTransition } from "react";
import type { BillingStatus, ChangePreview } from "@/lib/types";
import { applyBilling, previewBilling } from "./actions";

function money(cents: number, currency: string): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency.toUpperCase(),
  }).format(cents / 100);
}

export function BillingPanel({
  siteId,
  status,
}: {
  siteId: string;
  status: BillingStatus;
}) {
  const [preview, setPreview] = useState<ChangePreview | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const changed = status.camera_quantity !== status.billed_cameras;

  if (status.status === "none") {
    return (
      <section className="mt-8">
        <h2 className="font-serif text-lg text-ink">Billing</h2>
        <p className="mt-1 text-sm text-ink-soft">
          No subscription on file yet. Billing is set up when the account goes
          live.
        </p>
      </section>
    );
  }

  return (
    <section className="mt-8">
      <h2 className="font-serif text-lg text-ink">Billing</h2>
      <dl className="wt-hairline mt-2 border-t py-3 text-sm">
        <Row term="Status">
          <span className={status.read_only ? "text-flag" : "text-ink"}>
            {status.status}
            {status.read_only ? " · console read-only" : ""}
          </span>
        </Row>
        <Row term="Cameras billed">
          <span className="wt-num text-ink">
            {status.billed_cameras}
            {changed ? (
              <span className="text-ink-soft"> → {status.camera_quantity} live</span>
            ) : null}
          </span>
        </Row>
        {status.current_period_end ? (
          <Row term="Renews">
            <span className="text-ink-soft">
              {new Date(status.current_period_end).toLocaleDateString()}
            </span>
          </Row>
        ) : null}
        {status.grace_until ? (
          <Row term="Grace period ends">
            <span className="text-flag">
              {new Date(status.grace_until).toLocaleString()}
            </span>
          </Row>
        ) : null}
      </dl>

      {changed && (
        <div className="mt-3">
          <button
            onClick={() =>
              start(async () => {
                setErr(null);
                const r = await previewBilling(siteId);
                if (r.ok) setPreview(r.preview);
                else setErr(r.error);
              })
            }
            disabled={pending}
            className="wt-hairline border px-4 py-1.5 text-sm text-ink hover:bg-[color-mix(in_srgb,var(--color-field)_8%,transparent)] disabled:opacity-50"
          >
            {pending ? "Checking…" : "Preview camera-count change"}
          </button>

          {preview && (
            <div className="wt-hairline mt-3 border bg-paper-raised p-3 text-sm">
              <p className="text-ink">
                {preview.current_cameras} → {preview.new_cameras} cameras.{" "}
                {preview.prorated_amount_cents > 0
                  ? `Charged now: ${money(preview.prorated_amount_cents, preview.currency)} (prorated).`
                  : preview.prorated_amount_cents < 0
                    ? `Credit applied: ${money(-preview.prorated_amount_cents, preview.currency)} at the next period.`
                    : "No immediate change."}
              </p>
              <p className="mt-1 text-xs text-ink-soft">
                Next invoice: {money(preview.next_invoice_total_cents, preview.currency)} ·
                effective {new Date(preview.effective).toLocaleDateString()}
              </p>
              <button
                onClick={() =>
                  start(async () => {
                    setErr(null);
                    const r = await applyBilling(siteId);
                    if (r.ok) setPreview(null);
                    else setErr(r.error ?? "Could not apply the change.");
                  })
                }
                disabled={pending}
                className="wt-hairline mt-3 border px-4 py-1.5 text-sm text-ink hover:bg-[color-mix(in_srgb,var(--color-field)_8%,transparent)] disabled:opacity-50"
              >
                Confirm and apply
              </button>
            </div>
          )}
        </div>
      )}
      {err && (
        <p role="alert" className="mt-2 text-xs text-flag">
          {err}
        </p>
      )}
    </section>
  );
}

function Row({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-4 py-1">
      <dt className="w-40 text-ink-soft">{term}</dt>
      <dd>{children}</dd>
    </div>
  );
}
