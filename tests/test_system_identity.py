"""Coverage for `bearings.system_identity` and the
`POST /api/preferences/sync_from_system` route plus the boot-time
hydrator in `server.lifespan`.

The reads are best-effort by design (a fresh install on a system
without GECOS / AccountsService / `~/.face` should still boot the
server) so each test pins exactly which sources are available via
monkeypatch / tmp_path and verifies the resolver lands the right
value or `None`.

Three layers:

* **Resolver** — `read_system_identity()` returns the right field
  given a controlled set of available sources.
* **Sync route** — `POST /api/preferences/sync_from_system` writes
  whatever the resolver finds into the prefs row, normalises the
  avatar through Pillow, and is a no-op when nothing's available.
* **Boot hydration** — when the prefs row is at seed state, server
  startup populates from the system; when the row has been touched,
  startup leaves it alone.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from bearings import system_identity
from bearings.config import Settings
from bearings.server import create_app

# Edge of synthetic system avatar fixtures — larger than 512 so the
# resize pipeline does real downscale work.
_SOURCE_EDGE_PX = 800
_EXPECTED_EDGE_PX = 512


def _png_bytes(edge: int = _SOURCE_EDGE_PX) -> bytes:
    img = Image.new("RGB", (edge, edge), (60, 140, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# --- Resolver ------------------------------------------------------


def test_resolver_prefers_gecos_over_login(monkeypatch: pytest.MonkeyPatch) -> None:
    """When GECOS is set, it wins regardless of dbus or login fallbacks.
    The "real name" convention is field 0 of the comma-separated GECOS
    tuple — anything after the first comma is room number / phone /
    etc., not the name."""
    monkeypatch.setattr(system_identity, "_read_gecos_full_name", lambda: "Dave Hennigan")
    monkeypatch.setattr(system_identity, "_read_accountsservice_realname", lambda: "Should Not Win")
    monkeypatch.setattr(system_identity, "_read_login_name", lambda: "beryndil")
    assert system_identity._resolve_display_name() == "Dave Hennigan"


def test_resolver_falls_back_through_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system_identity, "_read_gecos_full_name", lambda: None)
    monkeypatch.setattr(
        system_identity, "_read_accountsservice_realname", lambda: "Real Name From DBus"
    )
    monkeypatch.setattr(system_identity, "_read_login_name", lambda: "beryndil")
    assert system_identity._resolve_display_name() == "Real Name From DBus"


def test_resolver_returns_none_when_every_source_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(system_identity, "_read_gecos_full_name", lambda: None)
    monkeypatch.setattr(system_identity, "_read_accountsservice_realname", lambda: None)
    monkeypatch.setattr(system_identity, "_read_login_name", lambda: None)
    assert system_identity._resolve_display_name() is None


def test_resolver_finds_accountsservice_icon_first(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When both `/var/lib/AccountsService/icons/<USER>` and `~/.face`
    exist, AccountsService wins — it's the canonical desktop source."""
    icons_dir = tmp_path / "icons"
    icons_dir.mkdir()
    accounts_icon = icons_dir / "testuser"
    accounts_icon.write_bytes(_png_bytes())
    home_face = tmp_path / "home" / ".face"
    home_face.parent.mkdir()
    home_face.write_bytes(_png_bytes())

    monkeypatch.setattr(system_identity, "_ACCOUNTSSERVICE_ICONS_DIR", icons_dir)
    monkeypatch.setattr(system_identity, "_HOME_FACE", home_face)
    monkeypatch.setenv("USER", "testuser")
    assert system_identity._resolve_avatar_path() == accounts_icon


def test_resolver_falls_back_to_home_face(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home_face = tmp_path / "home" / ".face"
    home_face.parent.mkdir()
    home_face.write_bytes(_png_bytes())

    monkeypatch.setattr(system_identity, "_ACCOUNTSSERVICE_ICONS_DIR", tmp_path / "missing")
    monkeypatch.setattr(system_identity, "_HOME_FACE", home_face)
    monkeypatch.setenv("USER", "testuser")
    assert system_identity._resolve_avatar_path() == home_face


def test_resolver_returns_none_when_no_avatar_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(system_identity, "_ACCOUNTSSERVICE_ICONS_DIR", tmp_path / "missing")
    monkeypatch.setattr(system_identity, "_HOME_FACE", tmp_path / "no-face")
    monkeypatch.setenv("USER", "testuser")
    assert system_identity._resolve_avatar_path() is None


# --- Sync route ----------------------------------------------------


@pytest.fixture
def sync_settings(tmp_settings: Settings, tmp_path: Path) -> Settings:
    tmp_settings.storage.avatar_path = tmp_path / "avatar.png"
    tmp_settings.storage.avatar_max_size_mb = 1
    return tmp_settings


@pytest.fixture
def sync_app(sync_settings: Settings) -> FastAPI:
    return create_app(sync_settings)


@pytest.fixture
def sync_client(sync_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(sync_app) as c:
        c.headers["origin"] = "http://testserver"
        yield c


def test_sync_route_applies_name_and_avatar(
    sync_client: TestClient,
    sync_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_avatar = tmp_path / "system-avatar.png"
    fake_avatar.write_bytes(_png_bytes())
    monkeypatch.setattr(
        "bearings.api.routes_preferences_avatar.read_system_identity",
        lambda: system_identity.SystemIdentity(
            display_name="Dave Hennigan", avatar_path=fake_avatar
        ),
    )

    res = sync_client.post("/api/preferences/sync_from_system")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["display_name"] == "Dave Hennigan"
    assert body["avatar_uploaded_at"] is not None

    # Avatar landed on disk normalised to 512×512 PNG, just like a
    # user upload.
    saved = sync_settings.storage.avatar_path
    with Image.open(saved) as img:
        assert img.format == "PNG"
        assert img.size == (_EXPECTED_EDGE_PX, _EXPECTED_EDGE_PX)


def test_sync_route_overwrites_existing_name(
    sync_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Manual sync is explicit user intent — it must overwrite even
    when the row already has a display_name. (Boot hydration takes
    the opposite stance; see the boot-hydration tests below.)"""
    sync_client.patch("/api/preferences", json={"display_name": "Manual Choice"})
    monkeypatch.setattr(
        "bearings.api.routes_preferences_avatar.read_system_identity",
        lambda: system_identity.SystemIdentity(display_name="System Name", avatar_path=None),
    )
    res = sync_client.post("/api/preferences/sync_from_system")
    assert res.json()["display_name"] == "System Name"


def test_sync_route_is_noop_when_nothing_available(
    sync_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty system → unchanged row, NOT an error. The button on the
    Settings panel should always succeed even on a system without
    GECOS / accountsservice / ~/.face."""
    monkeypatch.setattr(
        "bearings.api.routes_preferences_avatar.read_system_identity",
        lambda: system_identity.SystemIdentity(display_name=None, avatar_path=None),
    )
    res = sync_client.post("/api/preferences/sync_from_system")
    assert res.status_code == 200
    assert res.json()["display_name"] is None
    assert res.json()["avatar_uploaded_at"] is None


# --- Boot hydration ------------------------------------------------


def test_boot_hydrates_seed_state_row(
    sync_settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_avatar = tmp_path / "system-avatar.png"
    fake_avatar.write_bytes(_png_bytes())
    monkeypatch.setattr(
        "bearings.system_identity.read_system_identity",
        lambda: system_identity.SystemIdentity(
            display_name="Boot Hydration Name", avatar_path=fake_avatar
        ),
    )
    # Flip hydration on for this test — `tmp_settings` defaults it off
    # so the dev's real GECOS values don't bleed into the unrelated
    # tests; we explicitly want it on here to exercise the boot path.
    sync_settings.storage.system_identity_hydrate = True

    app = create_app(sync_settings)
    with TestClient(app) as c:
        c.headers["origin"] = "http://testserver"
        body = c.get("/api/preferences").json()
    assert body["display_name"] == "Boot Hydration Name"
    assert body["avatar_uploaded_at"] is not None


def test_boot_skips_hydration_when_row_has_been_touched(
    sync_settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Manual edits always win — boot must never clobber a name the
    user has typed. Pre-seed the row with a manual display_name, then
    verify the boot path leaves it alone."""
    sync_settings.storage.system_identity_hydrate = True
    # First boot: pre-seed via the normal PATCH path so the row has
    # a non-NULL display_name.
    monkeypatch.setattr(
        "bearings.system_identity.read_system_identity",
        lambda: system_identity.SystemIdentity(display_name=None, avatar_path=None),
    )
    app = create_app(sync_settings)
    with TestClient(app) as c:
        c.headers["origin"] = "http://testserver"
        c.patch("/api/preferences", json={"display_name": "Manually Set"})

    # Second boot: now system has a name — must be ignored because the
    # row carries a manual value.
    monkeypatch.setattr(
        "bearings.system_identity.read_system_identity",
        lambda: system_identity.SystemIdentity(
            display_name="System Name (should be ignored)", avatar_path=None
        ),
    )
    app2 = create_app(sync_settings)
    with TestClient(app2) as c:
        c.headers["origin"] = "http://testserver"
        body = c.get("/api/preferences").json()
    assert body["display_name"] == "Manually Set"
