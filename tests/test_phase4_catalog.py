from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from phase4_support import copy_fixture, empty_vault, projection, rich_vault

from knowlume.application.catalog import CATALOG_PAGE_SIZE, CatalogPage, CatalogQueryService
from knowlume.application.rendering import SafeMarkdownRenderer, safe_external_url
from knowlume.application.scanning import Finding, ScanResult, scan_vault
from knowlume.domain.values import DomainError
from knowlume.ids import new_ulid


def _catalog() -> CatalogQueryService:
    store = projection()
    return CatalogQueryService(
        index_status=lambda vault, scan: store.status(vault, scan=scan)
    )


def test_dashboard_empty_vault_and_unhealthy_vault_remain_browsable(tmp_path: Path) -> None:
    vault = empty_vault(tmp_path)
    empty = _catalog().dashboard(vault)
    assert empty["object_counts"] == {
        "source": 0,
        "note": 0,
        "snippet": 0,
        "ai_artifact": 0,
    }
    assert empty["index"]["state"] == "missing"

    copy_fixture(vault, "idea-note.md")
    invalid = vault.path("notes") / "ideas" / "invalid.md"
    invalid.write_text("---\nkind: note\n---\n<script>alert(1)</script>\n", encoding="utf-8")
    unhealthy = _catalog().dashboard(vault)
    assert unhealthy["object_counts"]["note"] == 1
    assert unhealthy["finding_counts"]["error"] >= 1


def test_dashboard_and_health_use_one_scanner_snapshot_per_request(tmp_path: Path) -> None:
    vault = rich_vault(tmp_path)
    snapshot = scan_vault(vault)
    calls: list[str] = []
    status_snapshots: list[ScanResult] = []

    def scanner(_vault: object) -> ScanResult:
        calls.append("scan")
        return snapshot

    def status(_vault: object, scan: ScanResult) -> dict[str, object]:
        status_snapshots.append(scan)
        return {"state": "missing", "counts": {"objects": 0, "segments": 0}}

    service = CatalogQueryService(scanner=scanner, index_status=status)
    dashboard = service.dashboard(vault)
    assert dashboard["object_counts"] == {
        "source": 4,
        "note": 4,
        "snippet": 1,
        "ai_artifact": 2,
    }
    assert dashboard["visibility_counts"] == {"private": 8, "public": 3}
    assert dashboard["source_type_counts"] == {
        "paper": 1,
        "web": 1,
        "book": 1,
        "oss": 1,
    }
    assert dashboard["note_type_counts"] == {
        "idea": 1,
        "literature": 1,
        "concept": 1,
        "synthesis": 1,
    }
    assert dashboard["workflow_counts"] == {
        "inbox": 1,
        "reading": 1,
        "processed": 2,
        "integrated": 0,
    }
    assert dashboard["review_counts"] == {
        "unreviewed": 1,
        "accepted": 0,
        "rejected": 0,
        "promoted": 1,
    }
    assert dashboard["finding_counts"] == {"error": 0, "warning": 0}
    assert calls == ["scan"]
    assert status_snapshots == [snapshot]

    calls.clear()
    status_snapshots.clear()
    health = service.health(vault)
    assert health["healthy"] is True
    assert calls == ["scan"]
    assert status_snapshots == [snapshot]


def test_dashboard_does_not_mix_vault_states_when_files_change_mid_request(
    tmp_path: Path,
) -> None:
    vault = rich_vault(tmp_path)
    changed = vault.path("notes") / "ideas" / "idea-note.md"
    calls = 0

    def mutate_after_scan(_vault: object, _scan: ScanResult) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if changed.exists():
            changed.unlink()
        return {"state": "missing", "counts": {"objects": 0, "segments": 0}}

    service = CatalogQueryService(index_status=mutate_after_scan)
    first = service.dashboard(vault)
    second = service.dashboard(vault)
    assert first["object_counts"]["note"] == 4
    assert second["object_counts"]["note"] == 3
    assert calls == 2

def test_catalog_filters_tags_sort_and_detail_reuse_the_snapshot(tmp_path: Path) -> None:
    vault = rich_vault(tmp_path)
    paper = vault.path("sources") / "papers" / "paper-source.md"
    paper.write_text(
        paper.read_text(encoding="utf-8").replace("tags: [transformer]", "tags: [transformer, ml]"),
        encoding="utf-8",
    )
    idea = vault.path("notes") / "ideas" / "idea-note.md"
    idea.write_text(
        idea.read_text(encoding="utf-8").replace(
            'updated: "2026-08-26"', 'updated: "2026-08-27"'
        ),
        encoding="utf-8",
    )
    service = _catalog()
    page = service.sources(
        vault,
        source_type="paper",
        visibility="public",
        tags=("transformer", "ml"),
    )
    assert page.total == 1
    assert page.items[0]["object_id"] == "src_01JSTAG7N9Q3V5X8Y2Z4A6B8C0"
    note_ids = [item["object_id"] for item in service.notes(vault).items]
    assert note_ids[0] == "note_01JSTAG7N9Q3V5X8Y2Z4A6B8D0"
    assert note_ids[1:] == sorted(note_ids[1:])

    snapshot = scan_vault(vault)
    calls = 0

    def scanner(_vault: object) -> ScanResult:
        nonlocal calls
        calls += 1
        return snapshot

    detail_service = CatalogQueryService(
        scanner=scanner,
        index_status=lambda _vault, _scan: {},
    )
    detail = detail_service.detail(
        vault, "src_01JSTAG7N9Q3V5X8Y2Z4A6B8C0", expected_kind="source"
    )
    assert detail["path"] == "sources/papers/paper-source.md"
    assert calls == 1
    with pytest.raises(DomainError) as wrong_kind:
        detail_service.detail(
            vault, "src_01JSTAG7N9Q3V5X8Y2Z4A6B8C0", expected_kind="note"
        )
    assert wrong_kind.value.code == "OBJECT_NOT_FOUND"


def test_catalog_fixed_pagination_is_deterministic(tmp_path: Path) -> None:
    vault = empty_vault(tmp_path)
    fixture = (Path(__file__).parent / "fixtures/v2/valid/idea-note.md").read_text(encoding="utf-8")
    ids: list[str] = []
    for index in range(CATALOG_PAGE_SIZE + 1):
        object_id = "note_" + new_ulid(
            timestamp_ms=1_800_000_000_000, randomness=index.to_bytes(10)
        )
        ids.append(object_id)
        text = fixture.replace("note_01JSTAG7N9Q3V5X8Y2Z4A6B8D0", object_id)
        (vault.path("notes") / "ideas" / f"note-{index:02}.md").write_text(text, encoding="utf-8")
    first = _catalog().notes(vault, page=1)
    second = _catalog().notes(vault, page=2)
    assert first.page_size == CATALOG_PAGE_SIZE
    assert [item["object_id"] for item in first.items] == sorted(ids)[:CATALOG_PAGE_SIZE]
    assert [item["object_id"] for item in second.items] == sorted(ids)[CATALOG_PAGE_SIZE:]
    assert first.has_next and second.has_previous
    recent = _catalog().dashboard(vault)["recent_notes"]
    assert len(recent) == 5
    assert [item["object_id"] for item in recent] == sorted(ids)[:5]
    with pytest.raises(DomainError):
        _catalog().notes(vault, page=0)


def test_health_findings_have_stable_sorting_and_fixed_pagination(tmp_path: Path) -> None:
    vault = empty_vault(tmp_path)
    findings = tuple(
        Finding(
            code=f"TEST_{index:03}",
            severity="error",
            category="contract",
            message=f"finding {index}",
            path=f"notes/{50 - index:03}.md",
        )
        for index in range(CATALOG_PAGE_SIZE + 1)
    )
    snapshot = ScanResult({}, {}, findings, len(findings))
    service = CatalogQueryService(
        scanner=lambda _vault: snapshot,
        index_status=lambda _vault, _scan: {
            "state": "missing",
            "counts": {"objects": 0, "segments": 0},
        },
    )
    expected = [finding.as_dict() for finding in sorted(findings)]
    first = cast(CatalogPage, service.health(vault, page=1)["findings"])
    second = cast(CatalogPage, service.health(vault, page=2)["findings"])
    assert first.items == tuple(expected[:CATALOG_PAGE_SIZE])
    assert second.items == tuple(expected[CATALOG_PAGE_SIZE:])
    assert first.has_next and second.has_previous


@pytest.mark.parametrize(
    "tags",
    [("",), ("same", "same")],
)
def test_catalog_rejects_invalid_filters_and_tags(tmp_path: Path, tags: tuple[str, ...]) -> None:
    vault = empty_vault(tmp_path)
    with pytest.raises(DomainError) as error:
        _catalog().sources(vault, tags=tags)
    assert error.value.code == "CATALOG_QUERY_INVALID"
    with pytest.raises(DomainError):
        _catalog().notes(vault, maturity="invented")


def test_safe_markdown_and_external_url_policy_fail_closed() -> None:
    renderer = SafeMarkdownRenderer()
    rendered = renderer.render(
        "# 标题\n\n<script>alert(1)</script>\n\n"
        "> quote with **strong**, *emphasis*, and `code`\n\n"
        "- first\n- second\n\n```text\ncode block\n```\n\n"
        "[ok](https://example.com/a) [js](javascript:alert(1)) "
        "[data](data:text/html,x) [file](file:///etc/passwd) "
        "[unknown](custom:thing) ![bad](https://example.com/x.svg) [unterminated"
    ).value
    assert "<h1>标题</h1>" in rendered
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert 'href="https://example.com/a"' in rendered
    assert 'rel="noopener noreferrer"' in rendered
    assert 'href="javascript:' not in rendered
    assert 'href="data:' not in rendered
    assert 'href="file:' not in rendered
    assert 'href="custom:' not in rendered
    assert "<img" not in rendered
    assert "<blockquote>" in rendered
    assert "<strong>strong</strong>" in rendered
    assert "<em>emphasis</em>" in rendered
    assert "<code>code</code>" in rendered
    assert "<pre><code class=\"language-text\">code block" in rendered
    assert "<ul>" in rendered
    assert safe_external_url("https://example.com/path") == "https://example.com/path"
    for unsafe in (
        "javascript:alert(1)",
        "data:text/html,x",
        "file:///tmp/x",
        "/relative",
        "custom:x",
        "https://u:p@example.com",
    ):
        assert safe_external_url(unsafe) is None
