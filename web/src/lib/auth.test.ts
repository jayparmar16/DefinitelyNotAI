import assert from "node:assert/strict";
import { test } from "node:test";

import { claims, pkceChallenge, stillFresh } from "./auth.ts";

test("PKCE challenge matches RFC 7636's example", async () => {
  assert.equal(
    await pkceChallenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"),
    "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
  );
});

test("a token is refreshed a minute before it expires", () => {
  assert.equal(stillFresh(1000, 900), true);
  assert.equal(stillFresh(1000, 940), false);
  assert.equal(stillFresh(1000, 1200), false);
});

test("claims decode base64url payloads with groups", () => {
  const payload = Buffer.from(JSON.stringify({ email: "a@wri.org", "cognito:groups": ["askwri-admins"] })).toString("base64url");
  assert.deepEqual(claims(`x.${payload}.y`), { email: "a@wri.org", "cognito:groups": ["askwri-admins"] });
});
