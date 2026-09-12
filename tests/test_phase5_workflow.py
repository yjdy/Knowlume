from __future__ import annotations

import json
import runpy
from collections.abc import Callable
from typing import Any, cast

import pytest
from test_phase5_ai import ARTIFACT_ID, NOTE_ID, NOW, ROOT, checksum, snapshot
from test_phase5_ai import vault as vault
from test_phase5_contracts import fixture, validator
from typer.testing import CliRunner

import knowlume.cli as cli
from knowlume.adapters.sqlite_projection import SQLiteProjection
from knowlume.application.ai import AIService
from knowlume.ports.vault import Vault

_workflow_module = runpy.run_path(str(ROOT / "scripts/phase5_workflow.py"))
WorkflowFailure = _workflow_module["WorkflowFailure"]
run_workflow = _workflow_module["run_workflow"]

Invoke = Callable[[list[str]], dict[str, Any]]


@pytest.fixture
def invoke(vault: Vault, monkeypatch: pytest.MonkeyPatch) -> Invoke:
    store = SQLiteProjection(
        ddl_reader=lambda _: (ROOT / "schemas/v2/sqlite-projection-v2.sql").read_text(
            encoding="utf-8"
        )
    )
    monkeypatch.setattr(cli, "_projection", lambda: store)
    monkeypatch.setattr("knowlume.cli_ai.SQLiteProjection", lambda: store)
    runner = CliRunner()
    envelope_validator = validator("cli-envelope-v1.schema.json")
    schemas = {
        name: validator(f"ai-{name}-result-v1.schema.json")
        for name in ("list", "review", "promote")
    }

    def run(arguments: list[str]) -> dict[str, Any]:
        result = runner.invoke(cli.app, ["--vault", str(vault.root), *arguments])
        document: dict[str, Any] = json.loads(result.stdout)
        assert result.exit_code == document["exit_code"], result.output
        assert not result.stderr
        envelope_validator.validate(document)
        if document["success"] and arguments[0] == "ai":
            schemas[arguments[1]].validate(document["data"])
        return document

    assert run(["index", "rebuild", "--json"])["success"]
    return run


def workflow(vault: Vault, invoke: Invoke, **changes: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "query": "Knowledge",
        "scope": "trusted-local",
        "artifact_id": ARTIFACT_ID,
        "decision": "accepted",
        "reviewer": "reviewer",
        "expected_checksum": checksum(vault, "ai/artifacts/candidate.md"),
        "note_id": NOTE_ID,
        "section_id": "sec_workflow",
        "actor": "promoter",
        "expected_note_checksum": checksum(vault, "notes/ideas/idea.md"),
    }
    return cast(dict[str, Any], run_workflow(invoke, **(arguments | changes)))


def test_actual_cli_results_match_frozen_goldens(
    vault: Vault, invoke: Invoke, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("knowlume.cli_ai.AIService", lambda: AIService(clock=lambda: NOW))
    for relative in ("ai/artifacts/candidate.md", "notes/ideas/idea.md"):
        path = vault.root / relative
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
    assert invoke(["index", "rebuild", "--json"])["success"]
    assert invoke(["ai", "list", "--json"]) == fixture("golden-ai-list.json")
    reviewed = invoke(
        [
            "ai",
            "review",
            ARTIFACT_ID,
            "--decision",
            "accepted",
            "--reviewer",
            "reviewer",
            "--expect-checksum",
            checksum(vault, "ai/artifacts/candidate.md"),
            "--json",
        ]
    )
    assert reviewed == fixture("golden-ai-review.json")
    promoted = invoke(
        [
            "ai",
            "promote",
            ARTIFACT_ID,
            "--into",
            NOTE_ID,
            "--section",
            "sec_reviewed_ai",
            "--actor",
            "promoter",
            "--expect-artifact-checksum",
            reviewed["data"]["checksum"],
            "--expect-note-checksum",
            checksum(vault, "notes/ideas/idea.md"),
            "--json",
        ]
    )
    assert promoted == fixture("golden-ai-promote.json")


def test_script_preview_apply_and_completed_retry(vault: Vault, invoke: Invoke) -> None:
    preview = workflow(vault, invoke)
    assert preview["data"]["mode"] == "dry-run"
    assert preview["data"]["changed"] is False
    assert invoke(["get", ARTIFACT_ID, "--json"])["data"]["object"]["review_status"] == "accepted"
    applied = workflow(vault, invoke, apply=True)
    assert applied["data"]["changed"] is True
    complete = snapshot(vault)
    retry = workflow(vault, invoke, apply=True)
    assert retry["data"]["already_promoted"] and not retry["data"]["changed"]
    assert snapshot(vault) == complete


def test_script_rejects_only_with_explicit_decision(vault: Vault, invoke: Invoke) -> None:
    before = (vault.root / "notes/ideas/idea.md").read_bytes()
    result = workflow(vault, invoke, decision="rejected")
    assert result["data"]["review_status"] == "rejected"
    assert (vault.root / "notes/ideas/idea.md").read_bytes() == before
    assert not list(vault.path("relations").glob("*.yaml"))


@pytest.mark.parametrize(
    "changes",
    [
        {"scope": ""},
        {"decision": ""},
        {"decision": "rejected", "apply": True},
        {"note_id": None},
        {"expected_checksum": "sha256:" + "0" * 64},
    ],
)
def test_script_refuses_missing_decisions_and_stale_inspection(
    vault: Vault, invoke: Invoke, changes: dict[str, Any]
) -> None:
    before = snapshot(vault)
    with pytest.raises(ValueError):
        workflow(vault, invoke, **changes)
    assert snapshot(vault) == before


def test_script_does_not_replay_a_preview_after_concurrent_edit(
    vault: Vault, invoke: Invoke
) -> None:
    edited: bytes | None = None

    def interrupt(arguments: list[str]) -> dict[str, Any]:
        nonlocal edited
        result = invoke(arguments)
        if "--dry-run" in arguments:
            path = vault.root / "notes/ideas/idea.md"
            edited = path.read_bytes() + b"\nConcurrent human edit.\n"
            path.write_bytes(edited)
        return result

    with pytest.raises(WorkflowFailure) as caught:
        workflow(vault, interrupt, apply=True)
    assert caught.value.envelope["errors"][0]["code"] == "VAULT_WRITE_CONFLICT"
    assert (vault.root / "notes/ideas/idea.md").read_bytes() == edited
    assert not list(vault.path("relations").glob("*.yaml"))


def test_script_checks_persisted_note_after_successful_apply(vault: Vault, invoke: Invoke) -> None:
    applied = False

    def edit_after_apply(arguments: list[str]) -> dict[str, Any]:
        nonlocal applied
        result = invoke(arguments)
        if "--apply" in arguments:
            applied = True
            path = vault.root / "notes/ideas/idea.md"
            path.write_bytes(path.read_bytes() + b"\nSubsequent human edit.\n")
        return result

    with pytest.raises(ValueError, match="persisted Note"):
        workflow(vault, edit_after_apply, apply=True)
    assert applied
    assert invoke(["get", ARTIFACT_ID, "--json"])["data"]["object"]["review_status"] == "promoted"
    assert b"Subsequent human edit." in (vault.root / "notes/ideas/idea.md").read_bytes()


def test_script_stops_on_context_failure_before_review(vault: Vault, invoke: Invoke) -> None:
    path = vault.root / "notes/ideas/idea.md"
    path.write_bytes(path.read_bytes() + b"\nNew human content.\n")
    before = snapshot(vault)
    with pytest.raises(WorkflowFailure) as caught:
        workflow(vault, invoke, apply=True)
    assert caught.value.envelope["errors"][0]["code"] == "INDEX_SOURCE_CHANGED"
    assert snapshot(vault) == before


def test_promotion_keeps_default_search_and_context_ai_exclusions(
    vault: Vault, invoke: Invoke
) -> None:
    workflow(vault, invoke, apply=True)
    assert invoke(["index", "status", "--json"])["data"]["state"] == "fresh"
    for scope in ("trusted-local", "public-safe"):
        context = invoke(["context", "candidate", "--scope", scope, "--json"])
        assert context["success"]
        assert not any(context["data"]["groups"].values())
        validator("context-result-v1.schema.json").validate(context["data"])
    assert invoke(["search", "candidate", "--json"])["data"]["count"] == 0
    explicit = invoke(["search", "candidate", "--role", "ai", "--json"])
    assert explicit["success"] and explicit["data"]["count"] > 0
    private = invoke(["context", "Knowledge", "--scope", "public-safe", "--json"])
    assert not any(private["data"]["groups"].values())
    limited = invoke(
        ["context", "Knowledge", "--scope", "trusted-local", "--max-chars", "1", "--json"]
    )
    assert limited["data"]["character_count"] <= 1
    missing_scope = CliRunner().invoke(
        cli.app, ["--vault", str(vault.root), "context", "Knowledge", "--json"]
    )
    assert missing_scope.exit_code == 2


def test_index_refresh_failure_does_not_turn_promotion_into_failure(
    vault: Vault, invoke: Invoke, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow(vault, invoke)

    def fail(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("private diagnostic must not leak")

    monkeypatch.setattr(SQLiteProjection, "refresh_if_present", fail)
    result = workflow(vault, invoke, apply=True)
    assert result["success"] and result["data"]["changed"]
    assert result["warnings"][0]["code"] == "INDEX_REFRESH_FAILED"
    assert "private diagnostic" not in json.dumps(result)
    assert invoke(["get", ARTIFACT_ID, "--json"])["data"]["object"]["review_status"] == "promoted"
    assert invoke(["search", "Knowledge", "--json"])["errors"][0]["code"] == "INDEX_SOURCE_CHANGED"


def test_phase4_renders_new_promotion_safely_without_writes(vault: Vault, invoke: Invoke) -> None:
    from fastapi.testclient import TestClient
    from phase4_support import web_app

    path = vault.root / "ai/artifacts/candidate.md"
    path.write_bytes(path.read_bytes() + b"\n<script>alert('xss')</script>\n")
    assert invoke(["index", "rebuild", "--json"])["success"]
    workflow(vault, invoke, apply=True)
    before = snapshot(vault)
    with TestClient(web_app(vault), base_url="http://127.0.0.1:8765") as client:
        for route in ("/", "/notes", f"/notes/{NOTE_ID}", "/health"):
            response = client.get(route)
            assert response.status_code == 200
            assert "<script>alert('xss')</script>" not in response.text
            if route == f"/notes/{NOTE_ID}":
                assert ARTIFACT_ID in response.text and "Reviewed AI" in response.text
        assert client.post(f"/notes/{NOTE_ID}").status_code == 405
    assert snapshot(vault) == before
