import base64
import json

from askwri.api.auth import CACHE_SECONDS, Verifier, token_claims


def token(**claims) -> str:
    def part(data):
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")

    return f"{part({'alg': 'RS256'})}.{part(claims)}.signature"


class NotAuthorized(Exception):
    pass


class FakeCognito:
    class exceptions:
        NotAuthorizedException = NotAuthorized

    def __init__(self, valid):
        self.valid, self.calls = valid, 0

    def get_user(self, AccessToken):
        self.calls += 1
        if AccessToken not in self.valid:
            raise NotAuthorized
        return {"Username": "u1", "UserAttributes": [{"Name": "email", "Value": "a@wri.org"}]}


GOOD = token(
    token_use="access", client_id="ui", exp=10_000, **{"cognito:groups": ["askwri-admins"]}
)
USER = token(token_use="access", client_id="ui", exp=10_000)


def test_claims_decode_without_padding():
    assert token_claims(USER)["client_id"] == "ui"


def test_cognito_decides_and_the_group_makes_an_admin():
    cognito = FakeCognito({GOOD, USER})
    verifier = Verifier(cognito, "ui", now=lambda: 1_000)
    assert verifier.caller(GOOD).admin and verifier.caller(GOOD).name == "a@wri.org"
    assert not verifier.caller(USER).admin
    assert Verifier(FakeCognito(set()), "ui", now=lambda: 1_000).caller(GOOD) is None


def test_tokens_for_another_client_or_id_tokens_never_reach_cognito():
    cognito = FakeCognito({GOOD})
    verifier = Verifier(cognito, "ui", now=lambda: 1_000)
    assert verifier.caller(token(token_use="access", client_id="other", exp=10_000)) is None
    assert verifier.caller(token(token_use="id", client_id="ui", exp=10_000)) is None
    assert verifier.caller("not-a-jwt") is None
    assert cognito.calls == 0


def test_an_accepted_token_is_rechecked_after_the_cache_window_or_its_expiry():
    clock = [1_000]
    cognito = FakeCognito({GOOD})
    verifier = Verifier(cognito, "ui", now=lambda: clock[0])
    verifier.caller(GOOD)
    verifier.caller(GOOD)
    assert cognito.calls == 1
    clock[0] += CACHE_SECONDS + 1
    verifier.caller(GOOD)
    assert cognito.calls == 2
    short = token(token_use="access", client_id="ui", exp=clock[0] + 10)
    cognito.valid.add(short)
    verifier.caller(short)
    clock[0] += 11
    cognito.valid.discard(short)
    assert verifier.caller(short) is None
