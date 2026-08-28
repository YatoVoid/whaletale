# WhaleTale — product context

Turns a multi-tenant property's existing security cameras into per-space
foot-traffic data, so the operator can price a space, fill it, and prove its
value to a prospective tenant. Video never leaves the property; only kilobyte
aggregates reach the cloud.

## Who uses the console

A property manager at a market, food hall, antique mall, or mixed-use retail
building. Not a technician, not a security team. They think in booth numbers,
lease terms, weekend footfall, and floor plans. They will never call support.
They use it on a laptop in a back office; the schedule screen weekly, most
others occasionally.

## What the console must answer

- What is this space worth, in one glance? (traffic share, capture rate, dwell,
  all with units and the period attached)
- Who holds each space right now, and when is it vacant? (the schedule)
- Change who is in a space in two clicks.
- Which spaces are underperforming or vacant? (overview)
- Hand a prospect a one-page report. (reports)

## Non-negotiable product truths

- A *space* is permanent; its *occupant* is not. Metrics attach to the space and
  are attributed to whoever held it at that moment (a query-time join, never
  baked in).
- **Vacant is information**, not missing data — it must read as a deliberate
  state everywhere it appears.
- **Degraded** (a bucket that fell back to a secondary camera) and **anomalous**
  (>2 SD from the trailing baseline, e.g. a festival Saturday) must be visually
  distinct from clean data. If the operator can't tell Saturday's spike was a
  festival at a glance, the screen has failed.
- Every metric label links to its definition (`docs/metrics.md`, spec 6.4). The
  operator gets asked "what does capture rate mean" by tenants.
- Never facial recognition, never re-identification, never stored video. Not
  features to add later.

## Screens (spec 10.1)

Overview · Schedule (built with the most care) · Zone editor (used once per
camera; may be desktop-only) · Space detail · Occupants · Reports · Settings.

## Stack

Next.js App Router + TypeScript (strict), Tailwind, shadcn/ui primitives,
Recharts, Auth.js. Reads the operator API in `cloud/whaletale_cloud/api/operator`.
