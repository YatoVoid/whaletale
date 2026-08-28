"use client";

import { useState, useTransition } from "react";

export function NewOccupant({
  action,
}: {
  action: (name: string, email: string, phone: string) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [pending, start] = useTransition();

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setErr(null);
    start(async () => {
      try {
        await action(name.trim(), email.trim(), phone.trim());
        setName("");
        setEmail("");
        setPhone("");
      } catch {
        setErr("Could not add the occupant.");
      }
    });
  }

  return (
    <form onSubmit={submit} className="wt-hairline mt-6 border-t pt-5">
      <div className="font-serif text-base text-ink">Add an occupant</div>
      <div className="mt-3 flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-ink-soft">Name</span>
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="wt-hairline w-52 border-b bg-transparent py-1.5 text-sm outline-none focus-visible:border-ink"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-ink-soft">Email</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="wt-hairline w-52 border-b bg-transparent py-1.5 text-sm outline-none focus-visible:border-ink"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-ink-soft">Phone</span>
          <input
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            className="wt-hairline w-40 border-b bg-transparent py-1.5 text-sm outline-none focus-visible:border-ink"
          />
        </label>
        <button
          type="submit"
          disabled={pending || !name.trim()}
          className="wt-hairline border px-4 py-1.5 text-sm text-ink hover:bg-[color-mix(in_srgb,var(--color-field)_8%,transparent)] disabled:opacity-50"
        >
          {pending ? "Adding…" : "Add"}
        </button>
      </div>
      {err ? (
        <p role="alert" className="mt-2 text-xs text-flag">
          {err}
        </p>
      ) : null}
    </form>
  );
}
