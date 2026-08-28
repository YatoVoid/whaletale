import { Suspense } from "react";
import { SignInForm } from "./sign-in-form";

export default function SignInPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto flex min-h-dvh max-w-sm items-center px-6 text-sm text-ink-soft">
          Loading…
        </div>
      }
    >
      <SignInForm />
    </Suspense>
  );
}
