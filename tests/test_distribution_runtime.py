from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest
from typer.testing import CliRunner

from knowlume.cli import app
from knowlume.doctor import doctor_report
from knowlume.resources import AssetError, asset
from knowlume.updates import UpdateCheckError, check_for_updates

runner = CliRunner()


def _metadata(releases: dict[str, list[dict[str, Any]]]) -> bytes:
    return json.dumps({"releases": releases}).encode()


def _fetcher(payload: bytes) -> Callable[[str, str, float], bytes]:
    def fetch(url: str, user_agent: str, timeout: float) -> bytes:
        assert url.startswith("https://")
        assert user_agent.startswith("Knowlume/")
        assert timeout > 0
        return payload

    return fetch


def test_update_check_selects_stable_release_by_default() -> None:
    payload = _metadata(
        {
            "0.1.0": [{"upload_time_iso_8601": "2026-08-01T00:00:00Z"}],
            "0.2.0b1": [{"upload_time_iso_8601": "2026-08-20T00:00:00Z"}],
            "0.1.1": [{"upload_time_iso_8601": "2026-08-10T00:00:00Z"}],
        }
    )
    result = check_for_updates(current_version="0.1.0", fetcher=_fetcher(payload))
    assert result["latest_version"] == "0.1.1"
    assert result["channel"] == "stable"
    assert result["update_available"] is True


def test_update_check_can_include_prereleases_and_ignores_yanked() -> None:
    payload = _metadata(
        {
            "0.2.0b1": [{"upload_time_iso_8601": "2026-08-20T00:00:00Z"}],
            "0.2.0b2": [{"yanked": True, "upload_time_iso_8601": "2026-08-21T00:00:00Z"}],
        }
    )
    result = check_for_updates(
        current_version="0.1.0",
        include_prereleases=True,
        fetcher=_fetcher(payload),
    )
    assert result["latest_version"] == "0.2.0b1"
    assert result["channel"] == "prerelease"


@pytest.mark.parametrize("payload", [b"not-json", b"{}", b'{"releases":[]}'])
def test_update_check_rejects_malformed_metadata(payload: bytes) -> None:
    with pytest.raises(UpdateCheckError):
        check_for_updates(current_version="0.1.0", fetcher=_fetcher(payload))


def test_update_check_rejects_network_failure() -> None:
    def failing_fetcher(url: str, user_agent: str, timeout: float) -> bytes:
        raise UpdateCheckError("offline")

    with pytest.raises(UpdateCheckError, match="offline"):
        check_for_updates(current_version="0.1.0", fetcher=failing_fetcher)


def test_version_command_reports_independent_contract_versions() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "object=2" in result.stdout
    assert "interface=1" in result.stdout
    assert "projection=2" in result.stdout


def test_doctor_json_uses_machine_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("knowlume.doctor.validate_required_assets", lambda: [])
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    document = json.loads(result.stdout)
    assert document["command"] == "doctor"
    assert document["success"] is True
    assert document["data"]["healthy"] is True
    assert set(document["data"]["user_paths"]) == {"config", "cache", "state", "logs"}


def test_update_check_json_and_error_envelopes(monkeypatch: pytest.MonkeyPatch) -> None:
    successful = {
        "result_version": 1,
        "distribution_name": "knowlume",
        "current_version": "0.1.0",
        "latest_version": "0.1.1",
        "update_available": True,
        "channel": "stable",
        "published_at": "2026-08-27T00:00:00Z",
        "release_url": "https://github.com/yjdy/Knowlume/releases/tag/v0.1.1",
    }
    monkeypatch.setattr("knowlume.cli.check_for_updates", lambda **kwargs: successful)
    result = runner.invoke(app, ["update-check", "--json"])
    assert result.exit_code == 0
    document = json.loads(result.stdout)
    assert document["command"] == "update-check"
    assert document["data"] == successful

    def fail(**kwargs: Any) -> None:
        raise UpdateCheckError("offline")

    monkeypatch.setattr("knowlume.cli.check_for_updates", fail)
    failed = runner.invoke(app, ["update-check", "--json"])
    assert failed.exit_code == 5
    error_document = json.loads(failed.stdout)
    assert error_document["errors"][0]["code"] == "UPDATE_CHECK_UNAVAILABLE"


def test_asset_names_cannot_escape_package_root() -> None:
    for name in ["../schemas/v2/objects.schema.json", "/etc/passwd", "schemas\\v2\\x"]:
        with pytest.raises(AssetError):
            asset(name)


def test_doctor_reports_missing_assets_without_creating_user_state() -> None:
    report = doctor_report()
    assert {check["name"] for check in report["checks"]} == {"python", "package-assets"}
