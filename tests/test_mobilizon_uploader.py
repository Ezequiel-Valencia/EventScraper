"""Which Mobilizon instance and account MobilizonUploader connects to."""

import json
from unittest.mock import patch

import pytest

from calendar_event_engine.publishers.mobilizon.uploader import MobilizonUploader

API = "calendar_event_engine.publishers.mobilizon.uploader.MobilizonAPI"


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("MOBILIZON_ENDPOINT", "https://env.example/api")
    monkeypatch.setenv("MOBILIZON_EMAIL", "env@example.com")
    monkeypatch.setenv("MOBILIZON_PASSWORD", "env-password")
    monkeypatch.delenv("MOBILIZON_LOGIN_FILE", raising=False)
    return monkeypatch


def test_explicit_values_override_the_environment(env, cache_db):
    uploader = MobilizonUploader(
        False,
        cache_db,
        endpoint="https://family.example/api",
        email="family@example.com",
        password="family-password",
    )
    with patch(API) as api:
        uploader.connect()
    api.assert_called_once_with(
        "https://family.example/api", "family@example.com", "family-password"
    )


def test_missing_values_fall_back_to_the_environment(env, cache_db):
    uploader = MobilizonUploader(False, cache_db, endpoint="https://other.example/api")
    with patch(API) as api:
        uploader.connect()
    api.assert_called_once_with(
        "https://other.example/api", "env@example.com", "env-password"
    )


def test_no_values_uses_the_environment_as_before(env, cache_db):
    with patch(API) as api:
        MobilizonUploader(False, cache_db).connect()
    api.assert_called_once_with(
        "https://env.example/api", "env@example.com", "env-password"
    )


def test_login_file_is_used_without_email_and_password(env, cache_db, tmp_path):
    env.delenv("MOBILIZON_EMAIL")
    env.delenv("MOBILIZON_PASSWORD")
    login = tmp_path / "login.json"
    login.write_text(json.dumps({"email": "file@example.com", "password": "file-pw"}))
    env.setenv("MOBILIZON_LOGIN_FILE", str(login))
    with patch(API) as api:
        MobilizonUploader(False, cache_db, endpoint="https://x.example/api").connect()
    api.assert_called_once_with("https://x.example/api", "file@example.com", "file-pw")
