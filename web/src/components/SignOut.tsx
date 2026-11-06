"use client";

/** The signed-in person's email and a Sign out button (nothing when sign-in is off). */

import { useEffect, useState } from "react";

import { authEnabled, currentUser, signOut, type User } from "@/lib/auth";

export function SignOut() {
  const [user, setUser] = useState<User | null>(null);
  useEffect(() => setUser(authEnabled ? currentUser() : null), []);
  if (!user) return null;
  return (
    <span className="aw-signout">
      <span className="aw-signout-email" title={user.admin ? "Admin" : undefined}>{user.email}</span>
      {user.admin && <a className="aw-btn on-dark sm" href="/admin/">Admin</a>}
      <button type="button" className="aw-btn on-dark sm" onClick={signOut}>Sign out</button>
    </span>
  );
}
