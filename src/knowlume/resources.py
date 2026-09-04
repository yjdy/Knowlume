from __future__ import annotations

from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import PurePosixPath


class AssetError(ValueError):
    """Raised when a bundled asset name is unsafe or unavailable."""


def asset_root() -> Traversable:
    return files("knowlume").joinpath("_assets")


def asset(relative_name: str) -> Traversable:
    if not relative_name or "\\" in relative_name:
        raise AssetError("asset name must be a non-empty POSIX relative path")
    path = PurePosixPath(relative_name)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != relative_name:
        raise AssetError("asset name escapes the package resource root")
    target = asset_root().joinpath(*path.parts)
    if not target.is_file():
        raise AssetError(f"bundled asset does not exist: {relative_name}")
    return target


def read_asset_text(relative_name: str) -> str:
    return asset(relative_name).read_text(encoding="utf-8")


def read_asset_bytes(relative_name: str) -> bytes:
    return asset(relative_name).read_bytes()


REQUIRED_ASSETS = (
    "schemas/v1/objects.schema.json",
    "schemas/v2/objects.schema.json",
    "schemas/v2/note-body.schema.json",
    "schemas/interfaces/cli-envelope-v1.schema.json",
    "schemas/interfaces/update-check-result-v1.schema.json",
    "schemas/interfaces/source-list-result-v1.schema.json",
    "schemas/interfaces/source-show-result-v1.schema.json",
    "schemas/interfaces/source-sync-result-v1.schema.json",
    "schemas/interfaces/source-workflow-result-v1.schema.json",
    "schemas/interfaces/grep-result-v1.schema.json",
    "schemas/interfaces/get-result-v1.schema.json",
    "schemas/interfaces/index-result-v1.schema.json",
    "schemas/interfaces/search-result-v1.schema.json",
    "schemas/interfaces/context-result-v1.schema.json",
    "schemas/v2/sqlite-projection-v2.sql",
    "templates/v1/notes/literature.md",
    "templates/v2/notes/idea.md",
    "templates/config/v1/knowlume.toml",
    "templates/web/base.html",
    "templates/web/dashboard.html",
    "templates/web/error.html",
    "templates/web/health.html",
    "templates/web/note-detail.html",
    "templates/web/notes.html",
    "templates/web/README.md",
    "templates/web/search.html",
    "templates/web/source-detail.html",
    "templates/web/sources.html",
    "templates/web/assets/app.css",
    "templates/web/assets/htmx.min.js",
    "templates/web/fragments/catalog-list.html",
    "templates/web/fragments/search-results.html",
    "templates/web/partials/metadata.html",
    "templates/web/partials/recent-list.html",
    "templates/web/partials/relations.html",
    "templates/web/vendor/HTMX-LICENSE.txt",
    "templates/web/vendor/htmx-2.0.10.integrity.txt",
)


def validate_required_assets() -> list[str]:
    errors: list[str] = []
    for relative_name in REQUIRED_ASSETS:
        try:
            asset(relative_name)
        except AssetError as error:
            errors.append(str(error))
    return errors
