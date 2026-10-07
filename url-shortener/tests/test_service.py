from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from shortener.api import create_app
from shortener.config import SERVICE_ROOT, Settings
from shortener.database import check_ready, initialize, make_engine

NOW = datetime(2030, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def setup(tmp_path):
    settings = Settings(database_path=tmp_path / "nested" / "test.db")
    initialize(settings)
    clock = [NOW]
    app = create_app(settings, clock=lambda: clock[0])
    with TestClient(app) as client:
        yield settings, clock, client


def test_create_redirect_stats(setup):
    settings, clock, client = setup
    response = client.post("/api/urls", json={"destination": "https://example.com/a?q=private", "alias": "Example"}, headers={"Host": "evil.test"})
    assert response.status_code == 201
    assert response.json()["short_url"] == "http://127.0.0.1:8000/Example"
    for _ in range(2):
        response = client.get("/Example", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "https://example.com/a?q=private"
        assert response.headers["cache-control"] == "no-store"
    assert client.head("/Example").status_code == 405
    assert client.get("/api/urls/Example/stats").json()["clicks"] == 2
    assert client.get("/example", follow_redirects=False).status_code == 404
    assert client.get("/missing", follow_redirects=False).status_code == 404
    assert client.get("/api/urls/missing/stats").status_code == 404
    assert client.get("/health").json() == {"status": "ok", "database": "ready"}
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert "422" in schema["paths"]["/api/urls"]["post"]["responses"]
    assert client.post("/api/urls", json={"destination": "https://example.com"}).status_code == 201
    assert client.post("/api/urls", json={"destination": "https://example.com"}).status_code == 201


@pytest.mark.parametrize("destination", ["ftp://example.com", "javascript:alert(1)", "/relative", "https://", "not a url", "https://user:pass@example.com", "https://example.com/" + "a" * 2048])
def test_bad_urls(setup, destination):
    response = setup[2].post("/api/urls", json={"destination": destination})
    assert response.status_code == 422
    assert set(response.json()) == {"error"}
    assert destination not in response.text


@pytest.mark.parametrize("alias", ["api", "docs", "health", "redoc", "openapi.json", "ab", "a" * 33, "bad alias", "a/b", "café"])
def test_bad_alias(setup, alias):
    assert setup[2].post("/api/urls", json={"destination": "https://example.com", "alias": alias}).status_code == 422


def test_alias_conflict(setup):
    client = setup[2]
    body = {"destination": "https://example.com", "alias": "Abc_-123"}
    assert client.post("/api/urls", json=body).status_code == 201
    assert client.post("/api/urls", json=body).status_code == 409
    body["alias"] = "abc_-123"
    assert client.post("/api/urls", json=body).status_code == 201


@pytest.mark.parametrize("expiration", ["2029-12-31T23:59:59Z", "2030-01-01T00:00:00Z", "2030-01-02T00:00:00"])
def test_invalid_expiration(setup, expiration):
    assert setup[2].post("/api/urls", json={"destination": "https://example.com", "expires_at": expiration}).status_code == 422


def test_expiration_boundary(setup):
    settings, clock, client = setup
    response = client.post("/api/urls", json={"destination": "https://example.com", "alias": "expiry", "expires_at": "2030-01-01T05:30:01+05:30"})
    assert response.status_code == 201
    assert response.json()["expires_at"] == "2030-01-01T00:00:01Z"
    clock[0] = NOW + timedelta(microseconds=999999)
    assert client.get("/expiry", follow_redirects=False).status_code == 302
    clock[0] = NOW + timedelta(seconds=1)
    assert client.get("/expiry", follow_redirects=False).status_code == 410
    clock[0] += timedelta(seconds=1)
    assert client.get("/expiry", follow_redirects=False).status_code == 410
    assert client.get("/api/urls/expiry/stats").json()["clicks"] == 1


def test_nonexpiring_restart_and_repeat_init(setup):
    settings, clock, client = setup
    client.post("/api/urls", json={"destination": "https://example.com", "alias": "forever"})
    initialize(settings)
    with TestClient(create_app(settings, clock=lambda: NOW + timedelta(days=10000))) as second:
        assert second.get("/forever", follow_redirects=False).status_code == 302
        assert second.get("/api/urls/forever/stats").json()["clicks"] == 1


def test_collisions(setup):
    settings, _, client = setup
    client.post("/api/urls", json={"destination": "https://example.com", "alias": "occupied"})
    codes = iter(["occupied", "recovered"])
    with TestClient(create_app(settings, code_factory=lambda: next(codes))) as other:
        assert other.post("/api/urls", json={"destination": "https://example.com"}).json()["code"] == "recovered"
    calls = []
    def collide():
        calls.append(1)
        return "occupied"
    with TestClient(create_app(settings, code_factory=collide)) as other:
        assert other.post("/api/urls", json={"destination": "https://example.com"}).status_code == 503
    assert len(calls) == 5


def test_concurrent_alias_and_clicks(setup):
    settings, _, client = setup
    def create(_):
        return client.post("/api/urls", json={"destination": "https://example.com", "alias": "shared"}).status_code
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(create, range(16)))
    assert results.count(201) == 1
    assert results.count(409) == 15
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: client.get("/shared", follow_redirects=False).status_code, range(40)))
    assert results == [302] * 40
    assert client.get("/api/urls/shared/stats").json()["clicks"] == 40


def test_migration_and_config(tmp_path, monkeypatch):
    settings = Settings(database_path=tmp_path / "fresh.db")
    engine = make_engine(settings)
    with pytest.raises(RuntimeError, match="init-db"):
        check_ready(engine, settings)
    assert not settings.database_path.exists()
    with pytest.raises(RuntimeError, match="init-db"):
        with TestClient(create_app(settings)):
            pass
    assert not settings.database_path.exists()
    initialize(settings)
    check_ready(engine, settings)
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "0001"
        assert {row[1] for row in conn.execute(text("PRAGMA table_info(links)"))} == {"code", "destination", "created_at", "expires_at", "clicks"}
    monkeypatch.chdir(tmp_path)
    assert Settings().database_path == SERVICE_ROOT / "data" / "shortener.db"
    assert Settings(database_path=Path("relative.db")).database_path == SERVICE_ROOT / "relative.db"
    monkeypatch.setenv("SHORTENER_DB_PATH", str(tmp_path / "override.db"))
    assert Settings.from_env().database_path == tmp_path / "override.db"
    for base in ["ftp://example.com", "https://example.com/path", "https://example.com/?x=y", "https://user:pass@example.com"]:
        with pytest.raises(ValueError):
            Settings(public_base_url=base)
    engine.dispose()


def test_locked_database_and_recovery(tmp_path):
    settings = Settings(database_path=tmp_path / "locks.db", lock_timeout=0.05)
    initialize(settings)
    with TestClient(create_app(settings)) as client:
        client.post("/api/urls", json={"destination": "https://example.com", "alias": "locked"})
        with sqlite3.connect(settings.database_path) as lock:
            lock.execute("BEGIN EXCLUSIVE")
            response = client.get("/locked", follow_redirects=False)
            assert response.status_code == 503
            assert "sqlite" not in response.text.lower()
            assert client.get("/health").status_code == 503
        assert client.get("/api/urls/locked/stats").json()["clicks"] == 0
        assert client.get("/locked", follow_redirects=False).status_code == 302


def test_cli_init_from_other_directory(tmp_path):
    import os
    env = {**os.environ, "SHORTENER_DB_PATH": str(tmp_path / "cli.db")}
    for _ in range(2):
        result = subprocess.run([sys.executable, "-m", "shortener", "init-db"], cwd=tmp_path, env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    assert (tmp_path / "cli.db").is_file()


def test_missing_revision_and_schema(tmp_path):
    settings = Settings(database_path=tmp_path / "missing.db")
    initialize(settings)
    with sqlite3.connect(settings.database_path) as conn:
        conn.execute("DELETE FROM alembic_version")
    with pytest.raises(RuntimeError, match="migrations"):
        check_ready(make_engine(settings), settings)


def test_database_timestamps_are_explicit_utc(setup):
    settings, _, client = setup
    client.post("/api/urls", json={"destination": "https://example.com", "alias": "timecheck"})
    with sqlite3.connect(settings.database_path) as conn:
        assert conn.execute("SELECT created_at FROM links").fetchone()[0] == "2030-01-01T00:00:00.000000Z"


def test_generated_code_and_error_contract(setup):
    client = setup[2]
    import re
    response = client.post("/api/urls", json={"destination": "http://example.com"})
    assert response.status_code == 201
    assert re.fullmatch(r"[A-Za-z0-9]{8}", response.json()["code"])
    for response in [
        client.post("/api/urls", json={"destination": "http://example.com", "unknown": 1}),
        client.post("/api/urls", content="{", headers={"Content-Type": "application/json"}),
        client.get("/unknown/path"),
        client.head("/missing"),
    ]:
        assert response.status_code in (404, 405, 422)
        if response.request.method != "HEAD":
            assert set(response.json()["error"]) == {"code", "message"}


def test_schema_drift_is_not_ready(setup):
    settings, _, client = setup
    with sqlite3.connect(settings.database_path) as conn:
        conn.execute("ALTER TABLE links RENAME TO broken_links")
    assert client.get("/health").status_code == 503
    with pytest.raises(RuntimeError, match="init-db"):
        with TestClient(create_app(settings)):
            pass


def test_ui_assets_and_api_coexist(setup):
    client = setup[2]
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'id="create-form"' in response.text
    assert 'id="stats-form"' in response.text
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    for path, content_type in [("/api/ui/app.css", "text/css"), ("/api/ui/app.js", "javascript")]:
        response = client.get(path)
        assert response.status_code == 200
        assert content_type in response.headers["content-type"]
        assert response.headers["x-content-type-options"] == "nosniff"
    assert client.post("/api/urls", json={"destination": "https://example.com", "alias": "app"}).status_code == 201
    assert client.get("/app", follow_redirects=False).status_code == 302
