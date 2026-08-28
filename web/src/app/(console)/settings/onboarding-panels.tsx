"use client";

import { useState, useTransition } from "react";
import type { Camera, EdgeBox } from "@/lib/types";
import { addCamera, pairBox } from "./actions";

export function EdgeBoxes({ siteId, boxes }: { siteId: string; boxes: EdgeBox[] }) {
  const [name, setName] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [pending, start] = useTransition();

  return (
    <section className="mt-8">
      <h2 className="font-serif text-lg text-ink">Edge boxes</h2>
      <p className="mt-1 text-sm text-ink-soft">
        Pair an on-prem box, then put its token in that box&apos;s{" "}
        <code className="wt-id">site.json</code>. The token is shown once.
      </p>

      <ul className="wt-hairline mt-3 border-t text-sm">
        {boxes.length === 0 && (
          <li className="py-2 text-ink-soft">No boxes paired.</li>
        )}
        {boxes.map((b) => (
          <li key={b.id} className="wt-hairline flex justify-between border-b py-2">
            <span className="text-ink">{b.name ?? b.id.slice(0, 8)}</span>
            <span className="text-ink-soft">
              {b.agent_version ? `v${b.agent_version}` : "not seen"} ·{" "}
              {b.last_seen_at
                ? new Date(b.last_seen_at).toLocaleString()
                : "never reported"}
            </span>
          </li>
        ))}
      </ul>

      <form
        className="mt-3 flex items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          setErr(null);
          setToken(null);
          start(async () => {
            const r = await pairBox(siteId, name.trim());
            if (r.ok) {
              setToken(r.token);
              setName("");
            } else setErr(r.error);
          });
        }}
      >
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-ink-soft">Box name (optional)</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="wt-hairline w-48 border-b bg-transparent py-1.5 text-sm outline-none focus-visible:border-ink"
          />
        </label>
        <button
          type="submit"
          disabled={pending}
          className="wt-hairline border px-4 py-1.5 text-sm text-ink hover:bg-[color-mix(in_srgb,var(--color-field)_8%,transparent)] disabled:opacity-50"
        >
          {pending ? "Pairing…" : "Pair a box"}
        </button>
      </form>

      {token && (
        <p className="wt-hairline mt-3 border bg-paper-raised p-3 text-xs">
          <span className="text-ink-soft">Pairing token (copy it now):</span>{" "}
          <span className="wt-id select-all break-all text-ink">{token}</span>
        </p>
      )}
      {err && (
        <p role="alert" className="mt-2 text-xs text-flag">
          {err}
        </p>
      )}
    </section>
  );
}

export function Cameras({ siteId, cameras }: { siteId: string; cameras: Camera[] }) {
  const [name, setName] = useState("");
  const [res, setRes] = useState("1920x1080");
  const [fps, setFps] = useState("4");
  const [err, setErr] = useState<string | null>(null);
  const [pending, start] = useTransition();

  return (
    <section className="mt-8">
      <h2 className="font-serif text-lg text-ink">Cameras</h2>
      <p className="mt-1 text-sm text-ink-soft">
        Run <code className="wt-id">whaletale-onboard --source … --emit</code> on the
        box first — it validates the stream and seals the credentials. Add the
        camera here so a zone can attach to it.
      </p>

      <ul className="wt-hairline mt-3 border-t text-sm">
        {cameras.length === 0 && (
          <li className="py-2 text-ink-soft">No cameras yet.</li>
        )}
        {cameras.map((c) => (
          <li key={c.id} className="wt-hairline flex justify-between border-b py-2">
            <span className="text-ink">{c.name}</span>
            <span className="text-ink-soft">
              {c.resolution} · {c.fps_target.toFixed(0)} fps · {c.status}
            </span>
          </li>
        ))}
      </ul>

      <form
        className="mt-3 flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          setErr(null);
          start(async () => {
            const r = await addCamera(siteId, name.trim(), res.trim(), Number(fps));
            if (r.ok) {
              setName("");
            } else setErr(r.error ?? "Could not add the camera.");
          });
        }}
      >
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-ink-soft">Name</span>
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="wt-hairline w-40 border-b bg-transparent py-1.5 text-sm outline-none focus-visible:border-ink"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-ink-soft">Resolution</span>
          <input
            value={res}
            onChange={(e) => setRes(e.target.value)}
            className="wt-hairline w-28 border-b bg-transparent py-1.5 text-sm outline-none focus-visible:border-ink"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-ink-soft">Target fps</span>
          <input
            type="number"
            min={1}
            value={fps}
            onChange={(e) => setFps(e.target.value)}
            className="wt-hairline w-20 border-b bg-transparent py-1.5 text-sm outline-none focus-visible:border-ink"
          />
        </label>
        <button
          type="submit"
          disabled={pending || !name.trim()}
          className="wt-hairline border px-4 py-1.5 text-sm text-ink hover:bg-[color-mix(in_srgb,var(--color-field)_8%,transparent)] disabled:opacity-50"
        >
          {pending ? "Adding…" : "Add camera"}
        </button>
      </form>
      {err && (
        <p role="alert" className="mt-2 text-xs text-flag">
          {err}
        </p>
      )}
    </section>
  );
}
