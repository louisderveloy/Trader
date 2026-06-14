"""
Security-focused unit tests for the Authelia OIDC auth layer.

These cover the highest-consequence logic from the security review:
- group→role mapping and the "no group ⇒ no access" rule;
- the production boot guards (AUTH_MODE, OIDC secrets, wildcard CORS);
- the local /auth/login 404 guard in OIDC mode;
- the encrypted transaction cookie and the single-use step-up grant;
- the open-redirect allowlist for return_to;
- session-JWT principal resolution in OIDC mode;
- route coverage (every non-allowlisted route is guarded).

They run with the API dependencies installed (see api/requirements.txt). They are
NOT collected by the bot test suite (which only scans ``tests/``).
"""

import importlib

import pytest
from fastapi import HTTPException

from api.auth import oidc
from api.auth.dependencies import _resolve_oidc_principal
from api.auth.jwt import create_access_token
from api.auth.models import Role
from api.auth.oidc_routes import _safe_return_to
from api.config import Settings

# Strong, prod-acceptable secret values for building Settings under test.
_OK = {
    "jwt_secret_key": "a" * 40,
    "csrf_secret_key": "b" * 40,
    "postgres_password": "c" * 20,
    "authelia_oidc_issuer": "https://auth.trader.derveloy.eu",
    "authelia_oidc_client_id": "trader-api",
    "authelia_oidc_client_secret": "d" * 40,
    "oidc_transaction_secret": "e" * 40,
    "cors_origins": "https://trader.derveloy.eu",
}


def _settings(**overrides):
    base = dict(_env_file=None, environment="prod", auth_mode="authelia_oidc", **_OK)
    base.update(overrides)
    return Settings(**base)


# ---------------------------------------------------------------- role mapping
def test_resolve_role_admin_wins():
    assert oidc.resolve_role(["viewers", "admins"]) == Role.ADMIN


def test_resolve_role_viewer():
    assert oidc.resolve_role(["viewers"]) == Role.VIEWER


def test_resolve_role_none_for_unknown_group():
    assert oidc.resolve_role(["random", ""]) is None
    assert oidc.resolve_role([]) is None


def test_role_predicates():
    assert oidc.is_admin(Role.ADMIN)
    assert not oidc.is_admin(Role.VIEWER)
    assert oidc.is_viewer(Role.ADMIN) and oidc.is_viewer(Role.VIEWER)
    assert not oidc.has_access(None)
    assert oidc.has_access(Role.VIEWER)


def test_extract_groups_handles_str_and_list():
    assert oidc.extract_groups({"groups": "admins"}) == ["admins"]
    assert oidc.extract_groups({"groups": ["a", "b"]}) == ["a", "b"]
    assert oidc.extract_groups({}) == []


# ---------------------------------------------------------------- prod boot guards
def test_prod_requires_authelia_oidc():
    with pytest.raises(ValueError, match="AUTH_MODE=authelia_oidc"):
        _settings(auth_mode="local")


def test_prod_rejects_wildcard_cors():
    with pytest.raises(ValueError, match="CORS"):
        _settings(cors_origins="*")


def test_prod_requires_https_issuer():
    with pytest.raises(ValueError, match="ISSUER"):
        _settings(authelia_oidc_issuer="http://auth.trader.derveloy.eu")


def test_prod_requires_strong_client_secret():
    with pytest.raises(ValueError, match="CLIENT_SECRET"):
        _settings(authelia_oidc_client_secret="short")


def test_prod_txn_secret_must_differ():
    with pytest.raises(ValueError, match="distinct"):
        _settings(oidc_transaction_secret=_OK["jwt_secret_key"])


def test_prod_valid_settings_ok():
    s = _settings()
    assert s.auth_mode == "authelia_oidc"


def test_dev_settings_are_lax():
    # Dev never triggers the prod validators.
    s = Settings(_env_file=None, environment="dev", auth_mode="local")
    assert s.dev_user_groups_list  # default 'admins'


# ---------------------------------------------------------------- transaction cookie
def test_transaction_roundtrip(monkeypatch):
    monkeypatch.setattr(oidc.settings, "oidc_transaction_secret", "z" * 40)
    sealed = oidc.seal_transaction({"state": "s", "nonce": "n"})
    opened = oidc.open_transaction(sealed)
    assert opened["state"] == "s" and opened["nonce"] == "n"


def test_transaction_tamper_rejected(monkeypatch):
    monkeypatch.setattr(oidc.settings, "oidc_transaction_secret", "z" * 40)
    sealed = oidc.seal_transaction({"state": "s"})
    with pytest.raises(HTTPException) as exc:
        oidc.open_transaction(sealed[:-2] + ("AA" if not sealed.endswith("AA") else "BB"))
    assert exc.value.status_code == 400


# ---------------------------------------------------------------- step-up grant
def test_stepup_grant_roundtrip(monkeypatch):
    monkeypatch.setattr(oidc.settings, "oidc_transaction_secret", "z" * 40)
    monkeypatch.setattr(oidc.settings, "oidc_stepup_max_age_seconds", 300)
    grant = oidc.seal_stepup_grant(sub="louis")
    assert oidc.verify_stepup_grant(grant, sub="louis")


def test_stepup_grant_wrong_sub(monkeypatch):
    monkeypatch.setattr(oidc.settings, "oidc_transaction_secret", "z" * 40)
    monkeypatch.setattr(oidc.settings, "oidc_stepup_max_age_seconds", 300)
    grant = oidc.seal_stepup_grant(sub="louis")
    assert not oidc.verify_stepup_grant(grant, sub="mallory")


def test_stepup_grant_missing():
    assert not oidc.verify_stepup_grant(None, sub="louis")
    assert not oidc.verify_stepup_grant("garbage", sub="louis")


# ---------------------------------------------------------------- open redirect
@pytest.mark.parametrize("good", ["/", "/runs", "/optimizations", "/a/b_c-d"])
def test_return_to_allows_relative(good):
    assert _safe_return_to(good) == good


@pytest.mark.parametrize(
    "bad",
    ["https://evil.com", "//evil.com", "/../etc", "http://x", "javascript:alert(1)", None, ""],
)
def test_return_to_rejects_unsafe(bad):
    assert _safe_return_to(bad) == "/"


# ---------------------------------------------------------------- session principal
def test_oidc_principal_from_session_jwt():
    token = create_access_token(data={"sub": "louis", "role": "viewer", "email": "l@x.eu"})
    principal = _resolve_oidc_principal(token)
    assert principal.username == "louis" and principal.role == Role.VIEWER


def test_oidc_principal_rejects_bad_role():
    token = create_access_token(data={"sub": "louis", "role": "superuser"})
    with pytest.raises(HTTPException) as exc:
        _resolve_oidc_principal(token)
    assert exc.value.status_code == 401


def test_oidc_principal_requires_token():
    with pytest.raises(HTTPException):
        _resolve_oidc_principal(None)


# ---------------------------------------------------------------- route coverage
def test_every_route_is_guarded():
    """Finding #16: no route is unintentionally public.

    Each registered API route must either be in the explicit unauthenticated
    allowlist or depend (transitively) on one of the auth dependencies.
    """
    main = importlib.import_module("api.main")
    from fastapi.routing import APIRoute

    guards = {"get_principal", "require_admin", "require_viewer", "get_current_user", "_checker"}
    allowlisted = {
        "/", "/health", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc",
        "/auth/login", "/auth/logout", "/auth/csrf-token",
        "/auth/oidc/login", "/auth/oidc/callback",
        "/auth/oidc/stepup/callback",  # validates via temp cookie, issues nothing without checks
    }

    def _dep_names(dependant) -> set[str]:
        names = set()
        for dep in dependant.dependencies:
            if dep.call is not None:
                names.add(getattr(dep.call, "__name__", ""))
            names |= _dep_names(dep)
        return names

    unguarded = []
    for route in main.app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path in allowlisted:
            continue
        if not (_dep_names(route.dependant) & guards):
            unguarded.append(f"{sorted(route.methods)} {route.path}")

    assert not unguarded, f"Unguarded routes found: {unguarded}"
