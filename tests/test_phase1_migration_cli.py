from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from typer.testing import CliRunner

from knowlume.adapters.filesystem import load_vault
from knowlume.adapters.transactions import RecoverableTransactions
from knowlume.application.migration import MigrationService
from knowlume.application.scanning import scan_vault
from knowlume.cli import app

ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "tests/fixtures/v1/valid"
CONFIG_TEXT = (ROOT / "templates/config/v1/knowlume.toml").read_text(encoding="utf-8")
PAPER_ID = "src_01JSTAG7N9Q3V5X8Y2Z4A6B8C0"
LITERATURE_ID = "note_01JSTAG7N9Q3V5X8Y2Z4A6B8D0"
CONCEPT_ID = "note_01JSTAG7N9Q3V5X8Y2Z4A6B8D2"
runner = CliRunner()


def _service(transactions: RecoverableTransactions | None = None) -> MigrationService:
    return MigrationService(
        config_reader=lambda: CONFIG_TEXT,
        transactions=transactions,
        clock=lambda: datetime(2026, 8, 27, 14, 0, tzinfo=UTC),
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _note(
    object_id: str,
    note_type: str,
    *,
    source_ids: tuple[str, ...] = (),
    related_notes: tuple[str, ...] = (),
    supersedes: tuple[str, ...] = (),
    fact: str = "",
    ai: str = "",
    ai_assisted: bool = False,
) -> str:
    sources = "\n".join(f"  - {value}" for value in source_ids)
    related = "\n".join(f"  - {value}" for value in related_notes)
    replaced = "\n".join(f"  - {value}" for value in supersedes)
    return f"""---
schema_version: 1
id: {object_id}
kind: note
note_type: {note_type}
title: Migrating {note_type}
visibility: private
record_status: active
maturity: developing
created: '2026-08-20'
updated: '2026-08-26'
source_ids:{chr(10) + sources if sources else " []"}
related_notes:{chr(10) + related if related else " []"}
tags: []
supersedes:{chr(10) + replaced if replaced else " []"}
superseded_by: null
ai_assisted: {str(ai_assisted).lower()}
---

# Migrating {note_type}

<!-- section_id: sec_original_facts -->
## Facts

{fact}

<!-- section_id: sec_my_interpretation -->
## Interpretation

Human interpretation.

<!-- section_id: sec_ai_inference -->
## AI

{ai}

<!-- section_id: sec_view_evolution -->
## Evolution
"""


def _mechanical_vault(tmp_path: Path) -> Path:
    root = tmp_path / "v1-vault"
    _write(root / "sources/papers/paper.md", (V1 / "paper-source.md").read_text(encoding="utf-8"))
    _write(
        root / "notes/literature/literature.md",
        _note(LITERATURE_ID, "literature", source_ids=(PAPER_ID,), related_notes=(CONCEPT_ID,)),
    )
    _write(
        root / "notes/concepts/concept.md",
        _note(
            CONCEPT_ID,
            "concept",
            related_notes=(LITERATURE_ID,),
            supersedes=(LITERATURE_ID,),
        ),
    )
    _write(
        root / "relations.yaml",
        f"""schema_version: 1
relations:
  - from_id: {PAPER_ID}
    to_id: {LITERATURE_ID}
    to_section_id: sec_original_facts
    relation_type: supports
    locator:
      locator_version: 1
      source_type: paper
      page: 4
    created_by: maintainer
""",
    )
    return root


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_dry_run_is_default_report_valid_and_writes_nothing(tmp_path: Path) -> None:
    root = _mechanical_vault(tmp_path)
    before = _snapshot(root)
    report = _service().run(root)
    assert report.mode == "dry-run"
    assert report.apply_allowed
    assert {finding.kind for finding in report.findings} == {"change"}
    assert _snapshot(root) == before
    schema = json.loads(
        (ROOT / "schemas/interfaces/migration-report-v1.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(report.data())


def test_apply_converts_objects_sections_and_relations_then_is_idempotent(
    tmp_path: Path,
) -> None:
    root = _mechanical_vault(tmp_path)
    report = _service().run(root, apply=True)
    assert report.apply_allowed
    assert all(finding.status == "resolved" for finding in report.findings)
    result = scan_vault(load_vault(root))
    assert result.healthy
    literature = (root / "notes/literature/literature.md").read_text(encoding="utf-8")
    assert "schema_version: 2" in literature
    assert "id=sec_original_facts role=fact" in literature
    assert "source_ids" not in literature
    assert {str(key) for key in result.relation_shards} == {
        PAPER_ID,
        LITERATURE_ID,
        CONCEPT_ID,
    }
    relation_types = {
        relation.relation_type.value
        for scanned in result.relation_shards.values()
        for relation in scanned.shard.relations
    }
    assert {"summarizes", "related_to", "supports", "supersedes"} <= relation_types
    after = _snapshot(root)
    repeated = _service().run(root, apply=True)
    assert repeated.findings[0].code == "MIGRATION_ALREADY_APPLIED"
    assert _snapshot(root) == after


def test_decisions_blockers_and_prohibited_guesses_block_apply(tmp_path: Path) -> None:
    root = tmp_path / "blocked"
    _write(root / "sources/papers/paper.md", (V1 / "paper-source.md").read_text(encoding="utf-8"))
    _write(
        root / "notes/concepts/concept.md",
        _note(
            CONCEPT_ID,
            "concept",
            source_ids=(PAPER_ID,),
            fact="Unlocated fact.",
            ai="Unaudited AI.",
            ai_assisted=True,
        ),
    )
    evergreen = _note(LITERATURE_ID, "concept").replace(
        "note_type: concept", "note_type: evergreen"
    )
    _write(root / "notes/concepts/evergreen.md", evergreen)
    before = _snapshot(root)
    report = _service().run(root, apply=True)
    codes = {finding.code for finding in report.findings}
    assert {
        "MIGRATION_EVERGREEN_CLASSIFICATION_REQUIRED",
        "MIGRATION_FACT_LOCATOR_REQUIRED",
        "MIGRATION_AI_SECTION_BLOCKED",
        "MIGRATION_AI_ASSISTED_BLOCKED",
        "MIGRATION_INFERENCE_PROHIBITED",
    } <= codes
    prohibited = next(
        finding for finding in report.findings if finding.code == "MIGRATION_INFERENCE_PROHIBITED"
    )
    assert prohibited.details and prohibited.details["inference_written"] is False
    assert not report.apply_allowed
    assert _snapshot(root) == before


def test_duplicate_and_dangling_identity_are_reported(tmp_path: Path) -> None:
    root = tmp_path / "invalid"
    concept = _note(CONCEPT_ID, "concept", related_notes=(LITERATURE_ID,))
    _write(root / "notes/concepts/one.md", concept)
    _write(root / "notes/concepts/two.md", concept)
    report = _service().run(root)
    codes = {finding.code for finding in report.findings}
    assert "MIGRATION_IDENTITY_DUPLICATE" in codes
    assert "MIGRATION_REFERENCE_BLOCKED" in codes
    assert not report.apply_allowed


class SimulatedCrash(BaseException):
    pass


class CrashingTransactions(RecoverableTransactions):
    def commit(self, vault, operation, writes, *, interrupt=None):  # type: ignore[no-untyped-def]
        def crash(point: str) -> None:
            if point == "after-replace-0":
                raise SimulatedCrash

        return super().commit(vault, operation, writes, interrupt=crash)


def test_crash_is_recovered_and_retry_succeeds(tmp_path: Path) -> None:
    root = _mechanical_vault(tmp_path)
    before = _snapshot(root)
    transactions = CrashingTransactions(process_alive=lambda _: False)
    with pytest.raises(SimulatedCrash):
        _service(transactions).run(root, apply=True)
    recovered = RecoverableTransactions(process_alive=lambda _: False)
    report = _service(recovered).run(root, apply=True)
    assert report.apply_allowed
    assert scan_vault(load_vault(root)).healthy
    assert _snapshot(root) != before
    assert list((root / ".knowlume/transactions").iterdir()) == []
    assert not (root / ".knowlume/locks/vault-write.lock").exists()


def test_cli_dry_run_blocked_apply_and_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("knowlume.cli.read_asset_text", lambda _: CONFIG_TEXT)
    root = _mechanical_vault(tmp_path)
    dry = runner.invoke(app, ["--vault", str(root), "migrate", "--from", "1", "--to", "2"])
    assert dry.exit_code == 0
    assert json.loads(dry.stdout)["mode"] == "dry-run"
    applied = runner.invoke(
        app,
        ["--vault", str(root), "migrate", "--from", "1", "--to", "2", "--apply"],
    )
    assert applied.exit_code == 0
    assert json.loads(applied.stdout)["mode"] == "apply"

    blocked_root = tmp_path / "blocked-cli"
    _write(blocked_root / "notes/concepts/concept.md", _note(CONCEPT_ID, "concept", fact="Fact"))
    blocked = runner.invoke(
        app,
        [
            "--vault",
            str(blocked_root),
            "migrate",
            "--from",
            "1",
            "--to",
            "2",
            "--apply",
        ],
    )
    assert blocked.exit_code == 3
    assert json.loads(blocked.stdout)["apply_allowed"] is False
