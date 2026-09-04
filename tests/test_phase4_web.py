from __future__ import annotations

import asyncio
import builtins
import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from html import unescape
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from phase4_support import (
    ROOT,
    WEB_ROOT,
    asset_reader,
    copy_fixture,
    empty_vault,
    projection,
    rich_vault,
    template_reader,
    web_app,
)
from typer.testing import CliRunner

import knowlume.cli as cli
from knowlume.application.catalog import CATALOG_PAGE_SIZE, CatalogQueryService
from knowlume.application.query import QueryService, get_object
from knowlume.application.scanning import Finding, ScanResult, scan_vault
from knowlume.domain.search import ContextScope, SearchFilters
from knowlume.domain.values import DomainError
from knowlume.ids import new_ulid
from knowlume.resources import REQUIRED_ASSETS
from knowlume.web.app import SECURITY_HEADERS, create_app
from knowlume.web.server import run_server

RUNNER = CliRunner()
BASE_URL = "http://127.0.0.1:8765"


def _client(app: Any) -> TestClient:
    return TestClient(app, base_url=BASE_URL)


def _tree_state(root: Path) -> dict[str, tuple[int, str]]:
    return {
        path.relative_to(root).as_posix(): (
            path.stat().st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _assert_security_headers(response: Any) -> None:
    for name, value in SECURITY_HEADERS.items():
        assert response.headers[name] == value
    assert "access-control-allow-origin" not in response.headers
    assert "set-cookie" not in response.headers


def test_every_web_resource_is_required_and_htmx_integrity_is_fixed() -> None:
    authoritative = {
        f"templates/web/{path.relative_to(WEB_ROOT).as_posix()}"
        for path in WEB_ROOT.rglob("*")
        if path.is_file()
    }
    assert {name for name in REQUIRED_ASSETS if name.startswith("templates/web/")} == authoritative
    integrity = dict(
        line.split(": ", 1)
        for line in template_reader("templates/web/vendor/htmx-2.0.10.integrity.txt").splitlines()
    )
    assert integrity["version"] == "2.0.10"
    asset_digest = hashlib.sha256(asset_reader("templates/web/assets/htmx.min.js")).hexdigest()
    assert asset_digest == integrity["asset_sha256"]
    assert hashlib.sha256(asset_reader("templates/web/vendor/HTMX-LICENSE.txt")).hexdigest() == (
        integrity["license_sha256"]
    )


def test_route_surface_is_exactly_the_frozen_read_only_html_interface(tmp_path: Path) -> None:
    app = web_app(empty_vault(tmp_path))
    surface = {
        cast(str, cast(Any, route).path): set(cast(Any, route).methods)
        for route in app.routes
    }
    assert surface == {
        "/": {"GET", "HEAD"},
        "/sources": {"GET", "HEAD"},
        "/sources/{source_id}": {"GET", "HEAD"},
        "/notes": {"GET", "HEAD"},
        "/notes/{note_id}": {"GET", "HEAD"},
        "/search": {"GET", "HEAD"},
        "/health": {"GET", "HEAD"},
        "/assets/app.css": {"GET", "HEAD"},
        "/assets/htmx.min.js": {"GET", "HEAD"},
    }


def test_dashboard_catalog_details_health_and_assets_without_index(tmp_path: Path) -> None:
    vault = rich_vault(tmp_path)
    before = _tree_state(vault.root)
    with _client(web_app(vault)) as client:
        routes = {
            "/": "知识库概览",
            "/sources": "Sources",
            "/sources/src_01JSTAG7N9Q3V5X8Y2Z4A6B8C0": "Attention Is All You Need",
            "/sources/src_01JSTAG7N9Q3V5X8Y2Z4A6B8C1": "Captured architecture article",
            "/sources/src_01JSTAG7N9Q3V5X8Y2Z4A6B8C2": "Designing Data-Intensive Applications",
            "/sources/src_01JSTAG7N9Q3V5X8Y2Z4A6B8C3": "Nested GitLab Project",
            "/notes": "Notes",
            "/notes/note_01JSTAG7N9Q3V5X8Y2Z4A6B8D0": "Source-free idea",
            "/notes/note_01JSTAG7N9Q3V5X8Y2Z4A6B8D2": "Transformer reading note",
            "/notes/note_01JSTAG7N9Q3V5X8Y2Z4A6B8D3": "Knowledge provenance synthesis",
            "/notes/note_01JSTAG7N9Q3V5X8Y2Z4A6B8D4": "Promoted AI-assisted concept",
            "/search": "搜索",
            "/health": "Knowledge Health",
        }
        for route, expected in routes.items():
            response = client.get(route)
            assert response.status_code == 200
            assert expected in response.text
            assert '"allowEval":false' in response.text
            assert '"allowScriptTags":false' in response.text
            assert '"includeIndicatorStyles":false' in response.text
            assert str(vault.root) not in response.text
            _assert_security_headers(response)
        css = client.get("/assets/app.css")
        js = client.get("/assets/htmx.min.js")
        assert css.status_code == js.status_code == 200
        assert css.content == asset_reader("templates/web/assets/app.css")
        assert js.content == asset_reader("templates/web/assets/htmx.min.js")
        _assert_security_headers(css)
        _assert_security_headers(js)
        css_text = css.text
        assert ":focus-visible" in css_text
        assert "@media (max-width: 34rem)" in css_text
        assert "@media (prefers-color-scheme: dark)" in css_text
        assert "@media (prefers-reduced-motion: reduce)" in css_text
        head = client.head("/sources")
        assert head.status_code == 200
        assert head.content == b""
        _assert_security_headers(head)
        for route in ("/docs", "/redoc", "/openapi.json"):
            unavailable = client.get(route)
            assert unavailable.status_code == 404
            _assert_security_headers(unavailable)
    assert _tree_state(vault.root) == before


def test_source_note_filters_invalid_queries_ids_and_fragments(tmp_path: Path) -> None:
    vault = rich_vault(tmp_path)
    paper = vault.path("sources") / "papers" / "paper-source.md"
    paper.write_text(
        paper.read_text(encoding="utf-8").replace(
            "tags: [transformer]", "tags: [transformer, ml]"
        ),
        encoding="utf-8",
    )
    literature = vault.path("notes") / "literature" / "literature-note.md"
    literature.write_text(
        literature.read_text(encoding="utf-8").replace(
            "tags: [transformer]", "tags: [transformer, reading]"
        ),
        encoding="utf-8",
    )
    with _client(web_app(vault)) as client:
        filtered = client.get(
            "/sources?source_type=paper&workflow_stage=processed&record_status=active"
            "&visibility=public&tag=transformer&tag=ml"
        )
        assert filtered.status_code == 200
        assert "src_01JSTAG7N9Q3V5X8Y2Z4A6B8C0" in filtered.text
        assert "src_01JSTAG7N9Q3V5X8Y2Z4A6B8C1" not in filtered.text
        filtered_notes = client.get(
            "/notes?note_type=literature&maturity=developing&record_status=active"
            "&visibility=public&tag=transformer&tag=reading"
        )
        assert filtered_notes.status_code == 200
        assert "note_01JSTAG7N9Q3V5X8Y2Z4A6B8D2" in filtered_notes.text
        assert "note_01JSTAG7N9Q3V5X8Y2Z4A6B8D0" not in filtered_notes.text
        fragment = client.get("/notes", headers={"HX-Request": "true"})
        assert fragment.status_code == 200
        assert '<section id="catalog-results"' in fragment.text
        assert "<!doctype html>" not in fragment.text
        _assert_security_headers(fragment)
        ordinary_form = client.get(
            "/sources?source_type=&workflow_stage=&record_status=&visibility=&tag="
        )
        assert ordinary_form.status_code == 200
        for route in (
            "/sources?page=0",
            "/sources?source_type=unknown",
            "/notes?maturity=unknown",
            "/notes?tag=same&tag=same",
            "/notes?unexpected=value",
        ):
            response = client.get(route)
            assert response.status_code == 400
            _assert_security_headers(response)
            assert any(
                code in response.text
                for code in ("WEB_QUERY_INVALID", "CATALOG_QUERY_INVALID", "FIELD_INVALID")
            )
        for route in (
            "/sources/not-an-id",
            "/notes/src_01JSTAG7N9Q3V5X8Y2Z4A6B8C0",
            "/ai_artifacts/ai_01JSTAG7N9Q3V5X8Y2Z4A6B8E0",
            "/attachments/private.pdf",
            "/snapshots/private.html",
            "/files/notes/ideas/idea-note.md",
            "/assets/%2e%2e/source-detail.html",
        ):
            missing = client.get(route)
            assert missing.status_code == 404
            _assert_security_headers(missing)


@pytest.mark.parametrize("state", ["missing", "fresh", "stale", "incompatible", "corrupt"])
def test_dashboard_and_health_render_every_index_state(tmp_path: Path, state: str) -> None:
    vault = empty_vault(tmp_path)
    store = projection()
    catalog = CatalogQueryService(
        index_status=lambda _vault, _scan: {
            "state": state,
            "counts": {"objects": 7, "segments": 11},
        }
    )
    app = create_app(
        vault=vault,
        catalog=catalog,
        query=QueryService(store),
        projection=store,
        template_reader=template_reader,
        asset_reader=asset_reader,
    )
    with _client(app) as client:
        for route in ("/", "/health"):
            response = client.get(route)
            assert response.status_code == 200
            assert state in response.text
            assert "objects 7" in response.text
            assert "segments 11" in response.text


def test_empty_and_unhealthy_vaults_have_direct_page_evidence(tmp_path: Path) -> None:
    vault = empty_vault(tmp_path)
    app = web_app(vault)
    with _client(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/health").status_code == 200

    copy_fixture(vault, "idea-note.md")
    invalid = vault.path("notes") / "ideas" / "invalid.md"
    invalid.write_text("---\nkind: note\n---\nunsafe\n", encoding="utf-8")
    with _client(app) as client:
        dashboard = client.get("/")
        health = client.get("/health")
        assert dashboard.status_code == health.status_code == 200
        assert "1" in dashboard.text
        assert scan_vault(vault).findings[0].code in health.text


def test_health_renders_complete_escaped_finding_data(tmp_path: Path) -> None:
    vault = empty_vault(tmp_path)
    finding = Finding(
        code="TEST_FINDING",
        severity="error",
        category="security",
        message="<script>alert(1)</script>",
        path="notes/example.md",
        object_id="note_01JSTAG7N9Q3V5X8Y2Z4A6B8D0",
        section_id="sec_example",
        details={"payload": "<img src=x onerror=alert(2)>"},
    )
    snapshot = ScanResult({}, {}, (finding,), 1)
    store = projection()
    catalog = CatalogQueryService(
        scanner=lambda _vault: snapshot,
        index_status=lambda _vault, _scan: {
            "state": "missing",
            "counts": {"objects": 0, "segments": 0},
        },
    )
    app = create_app(
        vault=vault,
        catalog=catalog,
        query=QueryService(store),
        projection=store,
        template_reader=template_reader,
        asset_reader=asset_reader,
    )
    with _client(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    for expected in (
        "TEST_FINDING",
        "notes/example.md",
        "note_01JSTAG7N9Q3V5X8Y2Z4A6B8D0",
        "sec_example",
        "payload",
    ):
        assert expected in response.text
    assert "<script>" not in response.text
    assert "<img" not in response.text


def test_detail_pages_preserve_attachment_metadata_citation_order_and_roles(
    tmp_path: Path,
) -> None:
    vault = rich_vault(tmp_path)
    attachment = copy_fixture(vault, "phase2a-paper-source.md")
    assert attachment.exists()
    literature = vault.path("notes") / "literature" / "literature-note.md"
    literature.write_text(
        literature.read_text(encoding="utf-8").replace(
            '      section: "3.2"',
            '      section: "3.2"\n'
            "  - source_id: src_01JSTAG7N9Q3V5X8Y2Z4A6B8C0\n"
            "    locator:\n"
            "      locator_version: 2\n"
            "      source_type: paper\n"
            "      page: 5",
        ),
        encoding="utf-8",
    )
    idea = vault.path("notes") / "ideas" / "idea-note.md"
    idea.write_text(
        idea.read_text(encoding="utf-8")
        + "\n<!-- knowlume:section id=sec_history role=evolution -->\n"
        "## 观点演化\n\nEarlier wording was refined.\n",
        encoding="utf-8",
    )
    with _client(web_app(vault)) as client:
        source = client.get("/sources/src_01JSTAG7N9Q3V5X8Y2Z4A6B8E0")
        assert source.status_code == 200
        for expected in (
            "paper.pdf",
            "application/pdf",
            "2048",
            "sha256:2222222222222222222222222222222222222222222222222222222222222222",
        ):
            assert expected in source.text
        assert "已记录附件：<strong>present</strong>" in source.text

        fact = client.get("/notes/note_01JSTAG7N9Q3V5X8Y2Z4A6B8D2")
        assert fact.status_code == 200
        visible_fact = unescape(fact.text)
        assert visible_fact.index('"page": 4') < visible_fact.index('"page": 5')
        role_pages = {
            "/notes/note_01JSTAG7N9Q3V5X8Y2Z4A6B8D0": "role=evolution",
            "/notes/note_01JSTAG7N9Q3V5X8Y2Z4A6B8D2": "role=fact",
            "/notes/note_01JSTAG7N9Q3V5X8Y2Z4A6B8D4": "role=ai",
        }
        for route, role in role_pages.items():
            response = client.get(route)
            assert response.status_code == 200
            assert role in response.text
        assert "role=human" in client.get(
            "/notes/note_01JSTAG7N9Q3V5X8Y2Z4A6B8D0"
        ).text
        expected_detail = get_object(vault, "note_01JSTAG7N9Q3V5X8Y2Z4A6B8D2")
        expected_relations = cast(
            dict[str, list[dict[str, object]]], expected_detail["relations"]
        )
        for direction in ("outgoing", "incoming"):
            for relation in expected_relations[direction]:
                related_id = relation["to_id"] if direction == "outgoing" else relation["from_id"]
                assert cast(str, related_id) in fact.text
                assert cast(str, relation["relation_type"]) in fact.text


def test_note_catalog_route_uses_fixed_pagination(tmp_path: Path) -> None:
    vault = empty_vault(tmp_path)
    fixture = (ROOT / "tests/fixtures/v2/valid/idea-note.md").read_text(encoding="utf-8")
    ids: list[str] = []
    for index in range(CATALOG_PAGE_SIZE + 1):
        object_id = "note_" + new_ulid(
            timestamp_ms=1_800_000_000_000, randomness=index.to_bytes(10)
        )
        ids.append(object_id)
        document = fixture.replace("note_01JSTAG7N9Q3V5X8Y2Z4A6B8D0", object_id)
        (vault.path("notes") / "ideas" / f"note-{index:02}.md").write_text(
            document, encoding="utf-8"
        )
    ordered = sorted(ids)
    with _client(web_app(vault)) as client:
        first = client.get("/notes?page=1")
        second = client.get("/notes?page=2")
        assert first.status_code == second.status_code == 200
        assert all(object_id in first.text for object_id in ordered[:CATALOG_PAGE_SIZE])
        assert ordered[CATALOG_PAGE_SIZE] not in first.text
        assert ordered[CATALOG_PAGE_SIZE] in second.text
        assert "/notes?page=2" in first.text
        assert "/notes?page=1" in second.text


def test_search_empty_missing_fresh_filters_and_htmx_match_query_service(tmp_path: Path) -> None:
    vault = rich_vault(tmp_path)
    store = projection()
    app = web_app(vault, store)
    with _client(app) as client:
        empty = client.get("/search")
        assert empty.status_code == 200
        assert "空查询不会访问索引" in empty.text
        assert 'hx-swap="outerHTML"' in empty.text
        missing = client.get("/search?q=Knowledge")
        assert missing.status_code == 503
        assert "INDEX_NOT_FOUND" in missing.text
        assert "kb index build" in missing.text
        _assert_security_headers(missing)

    store.build(vault, rebuild=True)
    expected = QueryService(store).search(
        vault,
        "Knowledge",
        SearchFilters(kind="note", role="human"),
        ContextScope.TRUSTED_LOCAL,
        20,
    )
    with _client(app) as client:
        query = "/search?q=Knowledge&kind=note&role=human&scope=trusted-local&limit=20"
        full = client.get(query)
        fragment = client.get(query, headers={"HX-Request": "true"})
        assert full.status_code == fragment.status_code == 200
        for hit in cast(list[dict[str, object]], expected["hits"]):
            assert hit["object_id"] in full.text
            assert hit["object_id"] in fragment.text
        assert "<!doctype html>" in full.text
        assert "<!doctype html>" not in fragment.text
        _assert_security_headers(fragment)
        browser_form = client.get(
            "/search?q=Transformer&scope=trusted-local&kind=&subtype=&visibility="
            "&record_status=&workflow_stage=&maturity=&review_status=&role=&tag=&limit=20"
        )
        assert browser_form.status_code == 200
        assert client.get("/search?q=Knowledge&limit=201").status_code == 400
        assert client.get("/search?q=Knowledge&scope=unknown").status_code == 400
        assert (
            client.get("/search?q=Knowledge&scope=public-safe&role=ai").status_code == 400
        )


def test_search_routes_cover_chinese_all_filters_ai_and_public_safe(tmp_path: Path) -> None:
    vault = rich_vault(tmp_path)
    paper = vault.path("sources") / "papers" / "paper-source.md"
    paper.write_text(
        paper.read_text(encoding="utf-8").replace(
            "tags: [transformer]", "tags: [transformer, ml]"
        ),
        encoding="utf-8",
    )
    idea = vault.path("notes") / "ideas" / "idea-note.md"
    idea.write_text(
        idea.read_text(encoding="utf-8") + "\n知识系统支持中文检索。\n",
        encoding="utf-8",
    )
    store = projection()
    store.build(vault, rebuild=True)
    with _client(web_app(vault, store)) as client:
        source = client.get(
            "/search",
            params=[
                ("q", "Attention"),
                ("scope", "trusted-local"),
                ("kind", "source"),
                ("subtype", "paper"),
                ("visibility", "public"),
                ("record_status", "active"),
                ("workflow_stage", "processed"),
                ("tag", "transformer"),
                ("tag", "ml"),
                ("limit", "20"),
            ],
        )
        assert source.status_code == 200
        assert "src_01JSTAG7N9Q3V5X8Y2Z4A6B8C0" in source.text
        assert 'class="tag-list" aria-label="Tags"' in source.text
        assert ">transformer<" in source.text
        assert ">ml<" in source.text

        fact = client.get(
            "/search",
            params={
                "q": "Transformer",
                "scope": "public-safe",
                "kind": "note",
                "subtype": "literature",
                "visibility": "public",
                "record_status": "active",
                "maturity": "developing",
                "role": "fact",
                "tag": "transformer",
            },
        )
        assert fact.status_code == 200
        assert "note_01JSTAG7N9Q3V5X8Y2Z4A6B8D2" in fact.text
        assert "sec_attention_facts" in fact.text
        assert "src_01JSTAG7N9Q3V5X8Y2Z4A6B8C0" in fact.text

        default_ai = client.get("/search?q=Candidate")
        assert default_ai.status_code == 200
        assert "ai_01JSTAG7N9Q3V5X8Y2Z4A6B8E0" not in default_ai.text
        explicit_ai = client.get(
            "/search?q=Candidate&scope=trusted-local&kind=ai_artifact&subtype=draft"
            "&visibility=private&record_status=active&review_status=promoted&role=ai"
        )
        assert explicit_ai.status_code == 200
        assert "ai_01JSTAG7N9Q3V5X8Y2Z4A6B8E0" in explicit_ai.text
        assert "ai_01JSTAG7N9Q3V5X8Y2Z4A6B8E1" not in explicit_ai.text
        assert "/ai_artifacts/" not in explicit_ai.text

        chinese = client.get("/search", params={"q": "知识系统"})
        assert chinese.status_code == 200
        assert "note_01JSTAG7N9Q3V5X8Y2Z4A6B8D0" in chinese.text
        public = client.get("/search", params={"q": "Knowledge", "scope": "public-safe"})
        assert public.status_code == 200
        assert "note_01JSTAG7N9Q3V5X8Y2Z4A6B8D0" not in public.text


def test_search_stale_incompatible_and_corrupt_recovery_pages(tmp_path: Path) -> None:
    vault = rich_vault(tmp_path)
    store = projection()
    store.build(vault, rebuild=True)
    app = web_app(vault, store)
    idea = vault.path("notes") / "ideas" / "idea-note.md"
    idea.write_text(idea.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
    with _client(app) as client:
        stale = client.get("/search?q=Knowledge")
        assert stale.status_code == 503
        assert "INDEX_SOURCE_CHANGED" in stale.text
        assert "kb index build" in stale.text
        _assert_security_headers(stale)

    store.build(vault)
    with closing(sqlite3.connect(store.database_path(vault))) as connection:
        connection.execute(
            "UPDATE index_metadata SET value='99' WHERE key='tokenizer_version'"
        )
        connection.commit()
    with _client(app) as client:
        incompatible = client.get("/search?q=Knowledge")
        assert incompatible.status_code == 503
        assert "INDEX_INCOMPATIBLE" in incompatible.text
        assert "kb index rebuild" in incompatible.text
        _assert_security_headers(incompatible)

    store.build(vault, rebuild=True)
    database = store.database_path(vault)
    database.write_bytes(b"not sqlite")
    with _client(app) as client:
        corrupt = client.get("/search?q=Knowledge")
        assert corrupt.status_code == 503
        assert "INDEX_CORRUPT" in corrupt.text
        assert "kb index rebuild" in corrupt.text
        _assert_security_headers(corrupt)


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        ({"Host": "evil.example:8765"}, 403),
        ({"Host": "127.0.0.1:9999"}, 403),
        ({"Origin": "http://evil.example:8765"}, 403),
        ({"Origin": "http://localhost:8765"}, 403),
        ({"Origin": "http://127.0.0.1:8765/"}, 403),
        ({"Origin": "http://evil.example:8765", "HX-Request": "true"}, 403),
        ({"Origin": BASE_URL}, 200),
        ({"Host": "localhost:8765", "Origin": "http://localhost:8765"}, 200),
        ({"Host": "[::1]:8765", "Origin": "http://[::1]:8765"}, 200),
        ({"X-Forwarded-Host": "evil.example", "X-Forwarded-Proto": "https"}, 200),
    ],
)
def test_host_origin_and_proxy_headers_fail_closed(
    tmp_path: Path, headers: dict[str, str], status: int
) -> None:
    vault = empty_vault(tmp_path)
    with _client(web_app(vault)) as client:
        response = client.get("/", headers=headers)
    assert response.status_code == status
    _assert_security_headers(response)


def test_methods_paths_xss_headers_logs_and_concurrent_reads(tmp_path: Path, caplog: Any) -> None:
    vault = rich_vault(tmp_path)
    note = vault.path("notes") / "ideas" / "idea-note.md"
    note.write_text(
        note.read_text(encoding="utf-8")
        .replace("title: Source-free idea", 'title: "<img src=x onerror=alert(3)>"')
        .replace(
            "Knowledge tools",
            "<script>alert(1)</script> <img src=x onerror=alert(2)> "
            "<svg onload=alert(3)></svg> [bad](javascript:alert(4)) "
            "[data](data:text/html,unsafe) ![remote](https://example.com/tracker.svg) "
            "{{ 7 * 7 }} [unterminated Knowledge tools",
        ),
        encoding="utf-8",
    )
    app = web_app(vault)
    with _client(app) as client:
        for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT"):
            response = client.request(method, "/notes")
            assert response.status_code == 405
            assert "WEB_METHOD_NOT_ALLOWED" in response.text
            assert response.headers["content-type"].startswith("text/html")
            _assert_security_headers(response)
        preflight = client.options(
            "/notes",
            headers={"Origin": BASE_URL, "Access-Control-Request-Method": "GET"},
        )
        assert preflight.status_code == 405
        _assert_security_headers(preflight)
        detail = client.get("/notes/note_01JSTAG7N9Q3V5X8Y2Z4A6B8D0")
        assert detail.status_code == 200
        assert "<script>alert(1)</script>" not in detail.text
        assert "<img" not in detail.text
        assert "<svg" not in detail.text
        assert 'href="javascript:' not in detail.text
        assert 'href="data:' not in detail.text
        assert 'src="https://example.com/tracker.svg"' not in detail.text
        assert "{{ 7 * 7 }}" in detail.text
        assert "49" not in detail.text
        query_echo = client.get("/sources", params={"tag": "<svg onload=alert(6)>"})
        assert query_echo.status_code == 200
        assert "<svg" not in query_echo.text
        _assert_security_headers(query_echo)
        template_echo = client.get("/sources", params={"tag": "{{ 7 * 7 }}"})
        assert 'value="{{ 7 * 7 }}"' in template_echo.text

    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(lambda _index: _client(app).get("/health").status_code, range(8)))
    assert statuses == [200] * 8

    class BrokenCatalog:
        def sources(self, *_args: object, **_kwargs: object) -> object:
            raise RuntimeError("private body /absolute/path adapter stderr SECRET_QUERY")

    store = projection()
    broken = create_app(
        vault=vault,
        catalog=BrokenCatalog(),  # type: ignore[arg-type]
        query=QueryService(store),
        projection=store,
        template_reader=template_reader,
        asset_reader=asset_reader,
    )
    with _client(broken) as client:
        response = client.get("/sources?tag=SECRET_QUERY")
    assert response.status_code == 500
    _assert_security_headers(response)
    assert "correlation ID:" in response.text
    assert "private body" not in response.text
    assert str(vault.root) not in response.text
    assert "SECRET_QUERY" not in caplog.text
    assert "adapter stderr" not in caplog.text


def test_cli_help_arguments_capability_server_and_browser_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    vault = empty_vault(tmp_path)
    help_result = RUNNER.invoke(cli.app, ["serve", "--help"])
    assert help_result.exit_code == 0
    assert "--open-browser" in help_result.stdout
    for args in (
        ("--host", "0.0.0.0"),
        ("--port", "0"),
        ("--port", "-1"),
        ("--port", "65536"),
        ("--port", "abc"),
    ):
        result = RUNNER.invoke(
            cli.app, ["--vault", str(vault.root), "serve", *args]
        )
        assert result.exit_code == 2
        assert "WEB_ARGUMENT_INVALID" in result.stderr

    original_import = builtins.__import__

    def unavailable(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "knowlume.web.server":
            raise ModuleNotFoundError(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", unavailable)
    missing = RUNNER.invoke(cli.app, ["--vault", str(vault.root), "serve"])
    assert missing.exit_code == 5
    assert "WEB_CAPABILITY_UNAVAILABLE" in missing.stderr
    monkeypatch.setattr(builtins, "__import__", original_import)

    import knowlume.web.server as server

    monkeypatch.setattr(
        server,
        "run_server",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            DomainError("WEB_SERVER_UNAVAILABLE", "occupied")
        ),
    )
    unavailable_server = RUNNER.invoke(
        cli.app, ["--vault", str(vault.root), "serve"]
    )
    assert unavailable_server.exit_code == 5
    assert "WEB_SERVER_UNAVAILABLE" in unavailable_server.stderr

    monkeypatch.setattr(
        server,
        "run_server",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt),
    )
    interrupted = RUNNER.invoke(cli.app, ["--vault", str(vault.root), "serve"])
    assert interrupted.exit_code == 0
    assert "Traceback" not in interrupted.output

    def fake_serve(app: Any, **kwargs: object) -> None:
        with _client(app):
            pass
        cast(Any, kwargs["on_started"])()

    monkeypatch.setattr("knowlume.web.server._serve", fake_serve)
    run_server(
        vault,
        host="127.0.0.1",
        port=8765,
        open_browser=True,
        browser_opener=lambda _url: False,
    )
    assert "WEB_BROWSER_OPEN_FAILED" in capsys.readouterr().err


def test_run_server_disables_access_log_and_proxy_headers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = empty_vault(tmp_path)
    captured: dict[str, object] = {}

    def fake_config(_app: Any, **kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    class FakeServer:
        def __init__(self, _config: object, on_started: Any) -> None:
            self._on_started = on_started

        def run(self) -> None:
            self._on_started()

    monkeypatch.setattr("knowlume.web.server.uvicorn.Config", fake_config)
    monkeypatch.setattr("knowlume.web.server._AfterStartupServer", FakeServer)
    run_server(vault, host="localhost", port=4321, open_browser=False)
    assert captured["host"] == "localhost"
    assert captured["port"] == 4321
    assert captured["access_log"] is False
    assert captured["proxy_headers"] is False


def test_browser_callback_runs_only_after_uvicorn_has_started(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    async def successful_startup(_server: object, sockets: object = None) -> None:
        del sockets
        cast(Any, _server).started = True
        events.append("listening")

    monkeypatch.setattr("knowlume.web.server.uvicorn.Server.startup", successful_startup)
    server = __import__("knowlume.web.server", fromlist=["_AfterStartupServer"])
    configured = server._AfterStartupServer(
        server.uvicorn.Config("unused:app"), lambda: events.append("browser")
    )
    asyncio.run(configured.startup())
    assert events == ["listening", "browser"]

    async def failed_startup(_server: object, sockets: object = None) -> None:
        del _server, sockets
        events.append("bind-failed")
        raise SystemExit(1)

    events.clear()
    monkeypatch.setattr("knowlume.web.server.uvicorn.Server.startup", failed_startup)
    failed = server._AfterStartupServer(
        server.uvicorn.Config("unused:app"), lambda: events.append("browser")
    )
    with pytest.raises(SystemExit):
        asyncio.run(failed.startup())
    assert events == ["bind-failed"]
