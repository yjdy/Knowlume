from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from phase4_support import projection, rich_vault, web_app
from test_phase4_web import BASE_URL, _tree_state

from knowlume.adapters.filesystem import FilesystemVault
from knowlume.application.catalog import CatalogQueryService
from knowlume.application.query import get_object
from knowlume.application.relations import RelationService
from knowlume.application.scanning import scan_vault

IDEA = "note_01JSTAG7N9Q3V5X8Y2Z4A6B8D0"
LITERATURE = "note_01JSTAG7N9Q3V5X8Y2Z4A6B8D2"
SECTION = "sec_attention_interpretation"


def test_reading_order_relation_direction_search_and_zero_writes(tmp_path: Path) -> None:
    vault = rich_vault(tmp_path)
    RelationService(filesystem=FilesystemVault(environment={})).add(
        vault, IDEA, LITERATURE, "related_to", to_section_value=SECTION
    )
    store = projection()
    store.build(vault)
    before = _tree_state(vault.root)
    with TestClient(web_app(vault, store), base_url=BASE_URL) as client:
        text = client.get(f"/notes/{LITERATURE}").text
        assert (
            text.index('id="note-sections"')
            < text.index('id="relations-outgoing"')
            < text.index("<details")
        )
        assert "<summary>" in text and "规范化字段" in text
        assert f'href="/notes/{LITERATURE}#{SECTION}"' in text
        assert f'href="/notes/{IDEA}#{SECTION}"' not in text
        assert "Source-free idea" in text
        outgoing = client.get(f"/notes/{IDEA}").text
        assert f'href="/notes/{LITERATURE}#{SECTION}"' in outgoing
        assert "Transformer reading note" in outgoing
        promoted = client.get("/notes/note_01JSTAG7N9Q3V5X8Y2Z4A6B8D4").text
        assert "Reviewed candidate wording" in promoted
        assert '/ai_artifacts/' not in promoted
        for headers in ({}, {"HX-Request": "true"}):
            response = client.get("/search", params={"q": "subspaces"}, headers=headers)
            assert response.status_code == 200
            assert f'href="/notes/{LITERATURE}#{SECTION}"' in response.text
    assert before == _tree_state(vault.root)


def test_relation_metadata_uses_one_snapshot_without_changing_get(tmp_path: Path) -> None:
    vault = rich_vault(tmp_path)
    scan = scan_vault(vault)
    calls = []

    def scanner(selected):  # type: ignore[no-untyped-def]
        calls.append(selected)
        return scan

    service = CatalogQueryService(scanner=scanner, index_status=lambda _v, _s: {})
    detail = service.detail(vault, LITERATURE, expected_kind="note")
    assert len(calls) == 1
    related = cast(dict[str, Any], detail["related_objects"])
    assert related[LITERATURE]["section_ids"] == ["sec_attention_facts", SECTION]
    assert "related_objects" not in get_object(vault, LITERATURE, scan=scan)


@pytest.mark.parametrize(
    ("code", "command"),
    [
        ("INDEX_NOT_FOUND", "build"),
        ("INDEX_SOURCE_CHANGED", "build"),
        ("INDEX_INCOMPATIBLE", "rebuild"),
        ("INDEX_CORRUPT", "rebuild"),
        ("INDEX_SOURCE_INVALID", "lint"),
    ],
)
def test_recovery_selects_same_vault_without_absolute_path(code: str, command: str) -> None:
    from knowlume.domain.values import DomainError
    from knowlume.web.app import _domain_web_error

    error = _domain_web_error(DomainError(code, "private-path-body"))
    assert (
        f"kb --vault <VAULT_ROOT> {'lint' if command == 'lint' else 'index ' + command}"
        in error.recovery
    )
    assert "private" not in error.message + error.recovery
