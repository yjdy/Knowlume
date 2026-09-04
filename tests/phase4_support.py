from __future__ import annotations

import shutil
from pathlib import Path

from knowlume.adapters.filesystem import FilesystemVault
from knowlume.adapters.sqlite_projection import SQLiteProjection
from knowlume.ports.vault import Vault

ROOT = Path(__file__).resolve().parents[1]


def empty_vault(tmp_path: Path, name: str = "vault") -> Vault:
    return FilesystemVault(environment={}).initialize(
        tmp_path / name,
        (ROOT / "templates/config/v1/knowlume.toml").read_text(encoding="utf-8"),
    )


def copy_fixture(vault: Vault, filename: str) -> Path:
    source = ROOT / "tests" / "fixtures" / "v2" / "valid" / filename
    text = source.read_text(encoding="utf-8")
    if "kind: source" in text:
        subtype = next(
            value
            for value in ("paper", "web", "book", "oss")
            if f"source_type: {value}" in text
        )
        folder = {"paper": "papers", "web": "web", "book": "books", "oss": "oss"}[subtype]
        target = vault.path("sources") / folder / filename
    elif "kind: note" in text:
        subtype = next(
            value
            for value in ("idea", "literature", "concept", "synthesis")
            if f"note_type: {value}" in text
        )
        folder = {
            "idea": "ideas",
            "literature": "literature",
            "concept": "concepts",
            "synthesis": "syntheses",
        }[subtype]
        target = vault.path("notes") / folder / filename
    elif "kind: ai_artifact" in text:
        target = vault.path("ai_artifacts") / filename
    else:
        target = vault.path("snippets") / filename
    shutil.copyfile(source, target)
    return target


def rich_vault(tmp_path: Path) -> Vault:
    vault = empty_vault(tmp_path)
    for filename in (
        "paper-source.md",
        "web-source.md",
        "book-source.md",
        "oss-source.md",
        "idea-note.md",
        "literature-note.md",
        "promoted-concept-note.md",
        "synthesis-note.md",
        "promoted-ai-artifact.md",
        "unreviewed-ai-artifact.md",
        "snippet.md",
    ):
        copy_fixture(vault, filename)
    for source in sorted((ROOT / "tests/fixtures/v2/valid/relations").glob("*.yaml")):
        shutil.copyfile(source, vault.path("relations") / source.name)
    return vault


def projection() -> SQLiteProjection:
    return SQLiteProjection(
        ddl_reader=lambda _name: (ROOT / "schemas/v2/sqlite-projection-v2.sql").read_text(
            encoding="utf-8"
        )
    )
