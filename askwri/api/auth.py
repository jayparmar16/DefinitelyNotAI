"""Who is calling the API: a user signed in through Cognito (the UI) or a server holding the
shared key (the evaluation runner and scripts). Admin routes also need the askwri-admins group."""

import base64
import hashlib
import json
import time
from dataclasses import dataclass

ADMIN_GROUP = "askwri-admins"
CACHE_SECONDS = 300  # how long an accepted token skips the Cognito check
CACHE_SIZE = 1000


@dataclass(frozen=True)
class Caller:
    """An authenticated caller: a name for the logs and whether it may open the admin routes."""

    name: str
    admin: bool


SERVICE = Caller("service", admin=True)  # sent the shared key
LOCAL = Caller("local", admin=True)  # no key and no user pool configured (local runs)


def token_claims(token: str) -> dict:
    """A JWT's payload, unverified: trust it only after Cognito has accepted the token."""
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


class Verifier:
    """Checks Cognito access tokens with GetUser, which rejects forged, expired and revoked
    tokens, and remembers accepted ones for a few minutes so each request doesn't call Cognito."""

    def __init__(self, cognito, client_id: str, now=time.time):
        self.cognito = cognito
        self.client_id = client_id
        self.now = now
        self.accepted: dict[str, tuple[float, Caller]] = {}

    def caller(self, token: str) -> Caller | None:
        """The signed-in user behind the token, or None when the token isn't valid for AskWRI."""
        digest = hashlib.sha256(token.encode()).hexdigest()
        now = self.now()
        hit = self.accepted.get(digest)
        if hit and hit[0] > now:
            return hit[1]
        try:
            claims = token_claims(token)
        except (IndexError, ValueError):
            return None
        if claims.get("token_use") != "access" or claims.get("client_id") != self.client_id:
            return None
        try:
            user = self.cognito.get_user(AccessToken=token)
        except self.cognito.exceptions.NotAuthorizedException:
            return None
        attributes = {a["Name"]: a["Value"] for a in user.get("UserAttributes", [])}
        found = Caller(
            attributes.get("email", user["Username"]),
            admin=ADMIN_GROUP in claims.get("cognito:groups", []),
        )
        if len(self.accepted) >= CACHE_SIZE:
            self.accepted = {k: v for k, v in self.accepted.items() if v[0] > now}
        self.accepted[digest] = (min(now + CACHE_SECONDS, claims["exp"]), found)
        return found
