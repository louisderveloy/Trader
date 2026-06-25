"""
Validation tests for the run-control API request models (security review #3).

Focus: the ``study_name`` allowlist on :class:`StartOptimizationRequest`, which
becomes a ``--study-name`` argv token for the optimization subprocess. A value
argparse could read as a flag (leading dash) must be rejected at the API edge.

Run with the API deps installed; not collected by the bot ``tests/`` suite.
"""

import pytest
from pydantic import ValidationError

from api.config import Settings
from api.models.run_control import StartOptimizationRequest


# Minimal kwargs for a valid dev Settings (mirrors the OIDC test fixture).
_SETTINGS_OK = {"environment": "dev", "postgres_password": "x" * 20}


def test_empty_postgres_password_rejected() -> None:
    # security review #19: no default, must fail fast in every environment.
    with pytest.raises(ValidationError):
        Settings(**{**_SETTINGS_OK, "postgres_password": ""})


def test_postgres_password_present_passes() -> None:
    s = Settings(**_SETTINGS_OK)
    assert s.postgres_password == "x" * 20


@pytest.mark.parametrize("bad", ["--n-trials 99999", "-h", "--help", "bad;name", "name$(x)"])
def test_flag_like_study_name_rejected(bad: str) -> None:
    with pytest.raises(ValidationError):
        StartOptimizationRequest(study_name=bad)


@pytest.mark.parametrize("ok", ["btc_test", "my-study-2026", "study 1"])
def test_normal_study_name_accepted(ok: str) -> None:
    req = StartOptimizationRequest(study_name=ok)
    assert req.study_name == ok


def test_study_name_too_long_rejected() -> None:
    with pytest.raises(ValidationError):
        StartOptimizationRequest(study_name="a" * 101)


def test_study_name_is_stripped() -> None:
    req = StartOptimizationRequest(study_name="btc_test  ")
    assert req.study_name == "btc_test"
