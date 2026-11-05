"use client";

/** Shows its children only to signed-in people when sign-in is configured; otherwise a sign-in card. */

import { type ReactNode, useEffect, useState } from "react";

import { accessToken, authEnabled, finishSignIn, signIn } from "@/lib/auth";

export function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<"checking" | "signed-out" | "in">(authEnabled ? "checking" : "in");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!authEnabled) return;
    finishSignIn()
      .catch((e: Error) => setError(e.message))
      .then(accessToken)
      .then((token) => setState(token ? "in" : "signed-out"));
  }, []);

  if (state === "in") return <>{children}</>;
  return (
    <div className="ad-signin">
      <div className="ad-signin-card">
        <div className="aw-logo"><span className="aw-logo-mark">WRI</span>AskWRI</div>
        {state === "checking" ? (
          <p className="aw-meta">Checking your sign-in…</p>
        ) : (
          <>
            <p>Answers from World Resources Institute research, with a citation for every claim.</p>
            {error && <p className="ad-banner bad">{error}</p>}
            <button type="button" className="aw-btn brand" onClick={() => signIn()}>Sign in</button>
            <p className="aw-meta">Access is by invitation. Ask the AskWRI team for an account.</p>
          </>
        )}
      </div>
    </div>
  );
}
