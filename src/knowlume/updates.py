from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, TypedDict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from packaging.version import InvalidVersion, Version

from knowlume.constants import DISTRIBUTION_NAME, PYPI_JSON_URL, REPOSITORY_URL
from knowlume.versioning import package_version

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 10.0


class UpdateCheckResult(TypedDict):
    result_version: int
    distribution_name: str
    current_version: str
    latest_version: str
    update_available: bool
    channel: str
    published_at: str | None
    release_url: str


class UpdateCheckError(RuntimeError):
    pass


Fetcher = Callable[[str, str, float], bytes]


def _fetch(url: str, user_agent: str, timeout: float) -> bytes:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": user_agent,
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            content_length = response.headers.get("Content-Length")
            if content_length is not None and int(content_length) > MAX_RESPONSE_BYTES:
                raise UpdateCheckError("package metadata response is too large")
            payload = bytes(response.read(MAX_RESPONSE_BYTES + 1))
    except (HTTPError, URLError, OSError, ValueError) as error:
        raise UpdateCheckError(f"package metadata is unavailable: {error}") from error
    if len(payload) > MAX_RESPONSE_BYTES:
        raise UpdateCheckError("package metadata response is too large")
    return payload


def _published_at(files: list[dict[str, Any]]) -> str | None:
    timestamps = [
        item.get("upload_time_iso_8601") or item.get("upload_time")
        for item in files
        if not item.get("yanked", False)
    ]
    values = [value for value in timestamps if isinstance(value, str) and value]
    if not values:
        return None
    return min(values)


def check_for_updates(
    *,
    include_prereleases: bool = False,
    current_version: str | None = None,
    endpoint: str = PYPI_JSON_URL,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    fetcher: Fetcher = _fetch,
) -> UpdateCheckResult:
    installed = current_version or package_version()
    try:
        installed_version = Version(installed)
    except InvalidVersion as error:
        raise UpdateCheckError(f"installed package version is invalid: {installed}") from error

    payload = fetcher(endpoint, f"Knowlume/{installed}", timeout)
    try:
        document = json.loads(payload)
        releases = document["releases"]
        if not isinstance(releases, dict):
            raise TypeError("releases is not an object")
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise UpdateCheckError("package metadata response is malformed") from error

    candidates: list[tuple[Version, str, list[dict[str, Any]]]] = []
    for version_text, raw_files in releases.items():
        if not isinstance(version_text, str) or not isinstance(raw_files, list):
            continue
        try:
            candidate = Version(version_text)
        except InvalidVersion:
            continue
        if candidate.is_devrelease or (candidate.is_prerelease and not include_prereleases):
            continue
        files = [item for item in raw_files if isinstance(item, dict)]
        if not files or all(item.get("yanked", False) for item in files):
            continue
        candidates.append((candidate, version_text, files))
    if not candidates:
        channel = "including prereleases" if include_prereleases else "stable"
        raise UpdateCheckError(f"package metadata contains no eligible {channel} release")

    latest, latest_text, latest_files = max(candidates, key=lambda item: item[0])
    return {
        "result_version": 1,
        "distribution_name": DISTRIBUTION_NAME,
        "current_version": installed,
        "latest_version": latest_text,
        "update_available": latest > installed_version,
        "channel": "prerelease" if latest.is_prerelease else "stable",
        "published_at": _published_at(latest_files),
        "release_url": f"{REPOSITORY_URL}/releases/tag/v{latest_text}",
    }
