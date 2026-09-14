from __future__ import annotations

import ast
import json
from dataclasses import replace

import pytest
from test_phase5_ai import ARTIFACT_ID, ROOT, change_artifact, promote, review, snapshot
from test_phase5_ai import vault as vault
from test_phase5_contracts import validator
from typer.testing import CliRunner

from knowlume.adapters.contract_v2 import parse_object_document, render_object_document
from knowlume.application.scanning import scan_vault
from knowlume.cli import app
from knowlume.domain.models import AIArtifact, InputRef, Source
from knowlume.domain.values import DomainError, ObjectId, RecordStatus
from knowlume.ports.vault import Vault


@pytest.mark.parametrize("unexpected", [False, True])
def test_doctor_corrupt_config_returns_aggregate_json(
    vault: Vault, monkeypatch: pytest.MonkeyPatch, unexpected: bool
) -> None:
    monkeypatch.setattr("knowlume.doctor.validate_required_assets", lambda: [])
    called: list[str] = []
    monkeypatch.setattr(
        "knowlume.adapters.diagnostic_probes._git_probe", lambda: called.append("git")
    )
    (vault.root / "knowlume.toml").write_bytes(b"\xffprivate-invalid-config")
    if unexpected:

        def fail_discovery(*args: object, **kwargs: object) -> None:
            raise RuntimeError("private-invalid-config")

        monkeypatch.setattr(
            "knowlume.adapters.diagnostic_probes.FilesystemVault.discover", fail_discovery
        )
    before = snapshot(vault)
    result = CliRunner().invoke(
        app,
        [
            "--vault",
            str(vault.root),
            "doctor",
            "--probe",
            "vault",
            "--probe",
            "sqlite",
            "--probe",
            "git",
            "--json",
        ],
    )
    assert result.exit_code == 3, (result.output, result.exception)
    envelope = json.loads(result.stdout)
    checks = {check["name"]: check for check in envelope["data"]["checks"]}
    assert envelope["success"] is False and envelope["exit_code"] == 3
    assert checks["vault"]["status"] == "failed"
    assert checks["sqlite"]["status"] == "failed"
    for name in ("vault", "sqlite"):
        assert checks[name]["code"] == ("DOCTOR_PROBE_FAILED" if unexpected else "VAULT_INVALID")
    assert checks["git"]["status"] == "passed" and called == ["git"]
    assert "private-invalid-config" not in result.output and str(vault.root) not in result.output
    assert not list(validator("cli-envelope-v1.schema.json").iter_errors(envelope))
    assert not list(validator("doctor-result-v2.schema.json").iter_errors(envelope["data"]))
    assert snapshot(vault) == before


def test_diagnostic_application_depends_only_on_domain_and_ports() -> None:
    tree = ast.parse((ROOT / "src/knowlume/application/diagnostics.py").read_text(encoding="utf-8"))
    imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)] + [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ]
    assert not any(module.startswith(("sqlite3", "subprocess")) for module in imports)
    assert all(
        not module.startswith("knowlume.")
        or module.startswith(("knowlume.domain.", "knowlume.ports."))
        for module in imports
    )


def test_diagnostic_adapter_does_not_import_application_services() -> None:
    adapter = ast.parse(
        (ROOT / "src/knowlume/adapters/diagnostic_probes.py").read_text(encoding="utf-8")
    )
    assert not any(
        isinstance(node, ast.ImportFrom) and (node.module or "").startswith("knowlume.application.")
        for node in ast.walk(adapter)
    )


def snippet_input(vault: Vault) -> None:
    for fixture, target in [
        ("oss-source.md", "sources/oss/source.md"),
        ("snippet.md", "snippets/snippet.md"),
    ]:
        (vault.root / target).write_bytes((ROOT / "tests/fixtures/v2/valid" / fixture).read_bytes())
    change_artifact(vault, input_refs=(InputRef(ObjectId("snip_01JSTAG7N9Q3V5X8Y2Z4A6B8F0")),))
    assert scan_vault(vault).healthy


@pytest.mark.parametrize("mutation", ["content", "archived"])
@pytest.mark.parametrize("apply", [False, True])
def test_snippet_source_changes_invalidate_review_without_a_relation_shard(
    vault: Vault, mutation: str, apply: bool
) -> None:
    snippet_input(vault)
    review(vault)
    path = vault.root / "sources/oss/source.md"
    document = parse_object_document(path.read_text(encoding="utf-8"))
    assert isinstance(document.object, Source)
    changed = (
        replace(document, body="Changed source metadata explanation.")
        if mutation == "content"
        else replace(document, object=replace(document.object, record_status=RecordStatus.ARCHIVED))
    )
    path.write_text(render_object_document(changed), encoding="utf-8")
    assert scan_vault(vault).healthy
    before = snapshot(vault)
    with pytest.raises(DomainError) as caught:
        promote(vault, apply=apply)
    assert caught.value.code == (
        "AI_INPUT_CHANGED" if mutation == "content" else "AI_INPUT_INVALID"
    )
    assert snapshot(vault) == before


def test_snippet_source_revision_and_absent_shard_are_bound(vault: Vault) -> None:
    snippet_input(vault)
    review(vault)
    artifact = scan_vault(vault).objects[ObjectId(ARTIFACT_ID)].document.object
    assert isinstance(artifact, AIArtifact) and artifact.review_evidence is not None
    revisions = {item.path: item.checksum for item in artifact.review_evidence.dependencies}
    assert revisions["sources/oss/source.md"] is not None
    assert revisions["relations/src_01JSTAG7N9Q3V5X8Y2Z4A6B8C3.yaml"] is None
    assert promote(vault, apply=True)["changed"] is True
    before = snapshot(vault)
    assert promote(vault, apply=True)["already_promoted"] is True
    assert snapshot(vault) == before


@pytest.mark.parametrize("operation", ["review", "preview", "apply"])
def test_old_incomplete_snippet_evidence_is_readable_but_not_authorizing(
    vault: Vault, operation: str
) -> None:
    snippet_input(vault)
    review(vault)
    artifact = scan_vault(vault).objects[ObjectId(ARTIFACT_ID)].document.object
    assert isinstance(artifact, AIArtifact) and artifact.review_evidence is not None
    evidence = replace(
        artifact.review_evidence,
        dependencies=tuple(
            item
            for item in artifact.review_evidence.dependencies
            if item.path
            not in {
                "sources/oss/source.md",
                "relations/src_01JSTAG7N9Q3V5X8Y2Z4A6B8C3.yaml",
            }
        ),
    )
    change_artifact(vault, review_evidence=evidence)
    assert scan_vault(vault).healthy
    before = snapshot(vault)
    with pytest.raises(DomainError) as caught:
        if operation == "review":
            review(vault)
        else:
            promote(vault, apply=operation == "apply")
    assert caught.value.code == "AI_INPUT_CHANGED"
    assert snapshot(vault) == before
