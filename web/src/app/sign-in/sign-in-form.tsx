"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { signIn } from "next-auth/react";

export function SignInForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res = await signIn("credentials", { email, token, redirect: false });
    setBusy(false);
    if (res?.error) {
      setError("That email and token did not match an operator account.");
      return;
    }
    router.replace(params.get("next") || "/");
  }

  return (
    <div className="mx-auto flex min-h-dvh max-w-sm flex-col justify-center px-6">
      <h1 className="font-serif text-2xl text-ink">WhaleTale</h1>
      <p className="mt-1 text-sm text-ink-soft">
        Sign in with your operator email and API token.
      </p>

      <form onSubmit={onSubmit} className="mt-8 flex flex-col gap-4">
        <label className="flex flex-col gap-1.5">
          <span className="text-xs text-ink-soft">Email</span>
          <input
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="wt-hairline border-b bg-transparent py-1.5 text-sm outline-none focus-visible:border-ink"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="text-xs text-ink-soft">Operator token</span>
          <input
            type="password"
            autoComplete="current-password"
            required
            value={token}
            onChange={(e) => setToken(e.target.value)}
            className="wt-hairline wt-id border-b bg-transparent py-1.5 outline-none focus-visible:border-ink"
          />
        </label>

        {error ? (
          <p role="alert" className="text-xs text-flag">
            {error}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={busy}
          className="wt-hairline mt-2 self-start border px-4 py-1.5 text-sm text-ink hover:bg-[color-mix(in_srgb,var(--color-field)_8%,transparent)] disabled:opacity-50"
        >
          {busy ? "Checking…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
