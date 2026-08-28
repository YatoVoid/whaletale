import { signOut } from "@/lib/auth";

export function SignOutButton({ email }: { email: string }) {
  return (
    <form
      action={async () => {
        "use server";
        await signOut({ redirectTo: "/sign-in" });
      }}
      className="flex items-center gap-3 text-xs text-ink-soft"
    >
      <span className="hidden truncate sm:inline">{email}</span>
      <button
        type="submit"
        className="underline decoration-rule decoration-dotted underline-offset-2 hover:decoration-ink-soft hover:text-ink"
      >
        Sign out
      </button>
    </form>
  );
}
