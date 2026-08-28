const DEFS: { id: string; term: string; body: string }[] = [
  {
    id: "entry",
    term: "Entry",
    body:
      "A tracked person's ground point moves outside → inside a zone polygon and stays inside for at least the dwell threshold (default 3s). The threshold suppresses boundary jitter.",
  },
  {
    id: "capture-rate",
    term: "Capture rate",
    body:
      "entries ÷ (entries + passersby). The most valuable number in the product: it separates appeal from location. A stall on a dead corridor with 40% capture is a good tenant in a bad spot.",
  },
  {
    id: "traffic-share",
    term: "Traffic share",
    body:
      "zone entries ÷ total people at the site, for the same period. The number that survives busy days and slow days.",
  },
  {
    id: "dwell",
    term: "Dwell",
    body:
      "Per-person time inside a zone, reported as the median (and p90). Never a mean — one person who left a bag in frame would ruin a mean.",
  },
  {
    id: "passerby",
    term: "Passerby",
    body:
      "A track whose ground point enters the zone's catchment (a dilation of the polygon) but never the zone itself.",
  },
  {
    id: "occupied-seconds",
    term: "Occupied seconds",
    body:
      "Wall-clock seconds during which at least one person was inside. Not a sum over people.",
  },
  {
    id: "anomalous",
    term: "Anomalous day",
    body:
      "A day more than 2 standard deviations from the trailing baseline (same weekday, same hours). Flagged, never silently excluded — a festival Saturday is real, a vendor should not claim credit for it.",
  },
  {
    id: "degraded",
    term: "Degraded bucket",
    body:
      "A 15-minute bucket where the primary camera had no data and a secondary camera stood in.",
  },
];

export default function DefinitionsPage() {
  return (
    <div className="mx-auto max-w-2xl px-6 py-10">
      <h1 className="font-serif text-2xl text-ink">Metric definitions</h1>
      <p className="mt-1 text-sm text-ink-soft">
        These are canonical (project spec §6.4). Every metric label in the console
        links here.
      </p>
      <dl className="mt-8 flex flex-col">
        {DEFS.map((d) => (
          <div key={d.id} id={d.id} className="wt-hairline border-t py-4 target:bg-[color-mix(in_srgb,var(--color-field)_8%,transparent)]">
            <dt className="font-serif text-lg text-ink">{d.term}</dt>
            <dd className="mt-1 max-w-prose text-sm text-ink-soft">{d.body}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
