"""Core test: the anonymous 2-download limit and admin's unlimited access.

Uses an in-memory Mongo (mongomock) and stubs the real yt-dlp download so
the test is fast, deterministic, and offline.
"""
import os
import sys

import mongomock
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import db  # noqa: E402
import downloader  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    # In-memory DB with a default database name so get_default_database() works.
    db.init_db(client=mongomock.MongoClient("mongodb://localhost/ytdltest"))

    # Stub the real download: immediately mark "complete" by invoking the
    # success callback (which records quota usage), no network involved.
    def fake_start_job(url, fmt, mode, on_success=None):
        if on_success:
            on_success()
        return "job-test"

    monkeypatch.setattr(downloader, "start_job", fake_start_job)

    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _download(client, headers=None):
    return client.post(
        "/api/download",
        json={"url": "https://youtu.be/x", "format_id": "18", "mode": "progressive"},
        headers=headers or {},
    )


def test_anonymous_limited_to_two_then_blocked(client):
    dev = {"X-Device-Id": "device-aaa"}

    # Starts with 2 free downloads.
    assert client.get("/api/me", headers=dev).get_json()["remaining"] == 2

    assert _download(client, dev).status_code == 200          # 1st
    assert _download(client, dev).status_code == 200          # 2nd
    assert client.get("/api/me", headers=dev).get_json()["remaining"] == 0

    blocked = _download(client, dev)                          # 3rd -> blocked
    assert blocked.status_code == 401
    assert blocked.get_json()["code"] == "register_required"

    # A different device is unaffected (independent quota).
    assert _download(client, {"X-Device-Id": "device-bbb"}).status_code == 200


def test_admin_is_unlimited(client):
    login = client.post("/api/auth/login",
                        json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200
    token = login.get_json()["token"]
    auth = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/me", headers=auth).get_json()["remaining"] is None
    for _ in range(5):
        assert _download(client, auth).status_code == 200
