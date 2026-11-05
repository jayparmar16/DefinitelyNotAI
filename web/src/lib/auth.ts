/**
 * Sign-in through Cognito's managed login (authorization code with PKCE, no client secret) and
 * the headers every API call sends. Without NEXT_PUBLIC_ASKWRI_AUTH_DOMAIN and
 * NEXT_PUBLIC_ASKWRI_AUTH_CLIENT_ID (local development) there is no sign-in, and the API key in
 * NEXT_PUBLIC_ASKWRI_API_KEY is sent instead.
 */

const domain = process.env.NEXT_PUBLIC_ASKWRI_AUTH_DOMAIN?.replace(/\/$/, "");
const clientId = process.env.NEXT_PUBLIC_ASKWRI_AUTH_CLIENT_ID;
export const authEnabled = Boolean(domain && clientId);

const TOKENS = "askwri.auth";
const PENDING = "askwri.auth.pending";
const SCOPES = "openid email aws.cognito.signin.user.admin";
const EARLY_SECONDS = 60; // refresh a token this long before it expires

type Tokens = { access: string; id: string; refresh?: string; expires: number };
export type User = { email: string; admin: boolean };

export function base64Url(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** RFC 7636 S256 challenge for a PKCE verifier. */
export async function pkceChallenge(verifier: string): Promise<string> {
  return base64Url(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier))));
}

/** True while a token is usable without a refresh. */
export function stillFresh(expires: number, nowSeconds: number): boolean {
  return expires - EARLY_SECONDS > nowSeconds;
}

/** A JWT's payload (read only; the API checks tokens with Cognito). */
export function claims(token: string): Record<string, unknown> {
  const part = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
  return JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(part), (c) => c.charCodeAt(0))));
}

// Browser storage can throw (private windows, blocked site data): treat that as signed out.
function read<T>(store: Storage, key: string): T | null {
  try {
    const text = store.getItem(key);
    return text ? (JSON.parse(text) as T) : null;
  } catch {
    return null;
  }
}

function write(store: Storage, key: string, value: unknown | null) {
  try {
    if (value === null) store.removeItem(key);
    else store.setItem(key, JSON.stringify(value));
  } catch {
    // Signed in for this page only.
  }
}

const redirectUri = () => `${window.location.origin}/`;
const now = () => Math.floor(Date.now() / 1000);

async function tokenRequest(body: Record<string, string>): Promise<Tokens> {
  const response = await fetch(`${domain}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ client_id: clientId!, ...body }),
  });
  if (!response.ok) throw new Error(`Sign-in failed (${response.status})`);
  const data = await response.json();
  return { access: data.access_token, id: data.id_token, refresh: data.refresh_token ?? body.refresh_token, expires: now() + data.expires_in };
}

/** Send the person to Cognito's sign-in page; they come back to / and then to this page. */
export async function signIn(): Promise<void> {
  const verifier = base64Url(crypto.getRandomValues(new Uint8Array(32)));
  const state = base64Url(crypto.getRandomValues(new Uint8Array(16)));
  write(sessionStorage, PENDING, { verifier, state, back: window.location.pathname + window.location.search });
  const query = new URLSearchParams({
    response_type: "code", client_id: clientId!, redirect_uri: redirectUri(), scope: SCOPES, state,
    code_challenge_method: "S256", code_challenge: await pkceChallenge(verifier),
  });
  window.location.assign(`${domain}/oauth2/authorize?${query}`);
}

/** On the way back from Cognito: swap the code for tokens and return to the page that asked. */
export async function finishSignIn(): Promise<void> {
  const params = new URLSearchParams(window.location.search);
  const code = params.get("code");
  const pending = read<{ verifier: string; state: string; back: string }>(sessionStorage, PENDING);
  if (!code || !pending) return;
  write(sessionStorage, PENDING, null);
  if (params.get("state") !== pending.state) throw new Error("Sign-in was interrupted; please sign in again.");
  const tokens = await tokenRequest({ grant_type: "authorization_code", code, redirect_uri: redirectUri(), code_verifier: pending.verifier });
  write(localStorage, TOKENS, tokens);
  window.history.replaceState(null, "", pending.back || "/");
}

/** A usable access token (refreshed when close to expiry), or null when signed out. */
export async function accessToken(): Promise<string | null> {
  const tokens = read<Tokens>(localStorage, TOKENS);
  if (!tokens) return null;
  if (stillFresh(tokens.expires, now())) return tokens.access;
  if (!tokens.refresh) return null;
  try {
    const renewed = await tokenRequest({ grant_type: "refresh_token", refresh_token: tokens.refresh });
    write(localStorage, TOKENS, renewed);
    return renewed.access;
  } catch {
    write(localStorage, TOKENS, null);
    return null;
  }
}

/** Who is signed in, from the ID token. */
export function currentUser(): User | null {
  const tokens = read<Tokens>(localStorage, TOKENS);
  if (!tokens) return null;
  const id = claims(tokens.id);
  const groups = (claims(tokens.access)["cognito:groups"] as string[] | undefined) ?? [];
  return { email: String(id.email ?? ""), admin: groups.includes("askwri-admins") };
}

export function signOut(): void {
  write(localStorage, TOKENS, null);
  const query = new URLSearchParams({ client_id: clientId!, logout_uri: redirectUri() });
  window.location.assign(`${domain}/logout?${query}`);
}

/** Headers for askwri-api: the signed-in user's token, or the development key. */
export async function apiHeaders(): Promise<Record<string, string>> {
  if (!authEnabled) return { "X-AskWRI-Key": process.env.NEXT_PUBLIC_ASKWRI_API_KEY ?? "" };
  const token = await accessToken();
  if (!token) throw new Error("Your sign-in has expired. Reload the page to sign in again.");
  return { Authorization: `Bearer ${token}` };
}
