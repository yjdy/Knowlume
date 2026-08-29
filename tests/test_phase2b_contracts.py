from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from knowlume.adapters.contract_v2 import parse_object_document, render_object_document
from knowlume.adapters.filesystem import parse_vault_config
from knowlume.domain.capture import (
    CaptureType,
    canonicalize_web_url,
    normalize_repository_url,
    recognize_capture_input,
)
from knowlume.domain.isbn import normalize_isbn
from knowlume.domain.models import (
    Actor,
    BookLocator,
    Citation,
    FactBlock,
    NoteBody,
    ObjectDocument,
    OssLocator,
    Relation,
    RelationShard,
    SnapshotRef,
    Source,
    WebLocator,
)
from knowlume.domain.repository import normalize_repository_host
from knowlume.domain.validation import validate_object_references, validate_relation_shard
from knowlume.domain.values import ActorType, DomainError, RelationType, SourceType

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "tests/fixtures/v2"
CONFIG = ROOT / "tests/fixtures/config/v1"


def test_book_edition_contract_round_trips_and_is_book_only() -> None:
    document = parse_object_document(
        (V2 / "valid/book-source-edition.md").read_text(encoding="utf-8")
    )
    assert document.object.edition == "Second Edition"  # type: ignore[union-attr]
    assert parse_object_document(render_object_document(document)) == document
    for name in ("paper-source-edition.md", "book-source-edition-whitespace.md"):
        with pytest.raises(DomainError):
            parse_object_document((V2 / "invalid" / name).read_text(encoding="utf-8"))


def test_legacy_web_source_without_snapshot_remains_readable() -> None:
    document = parse_object_document(
        (V2 / "valid/web-source-legacy-no-snapshot.md").read_text(encoding="utf-8")
    )
    source = document.object
    assert isinstance(source, Source)
    assert source.source_type is SourceType.WEB
    assert source.snapshot_ref is None
    assert parse_object_document(render_object_document(document)) == document


def test_repository_host_config_defaults_and_extends_builtins() -> None:
    legacy = (CONFIG / "valid/legacy-no-capture.toml").read_text(encoding="utf-8")
    empty = parse_vault_config((CONFIG / "valid/knowlume.toml").read_text(encoding="utf-8"))
    old = parse_vault_config(legacy)
    extended = parse_vault_config(
        (CONFIG / "valid/repository-hosts.toml").read_text(encoding="utf-8")
    )
    assert old.repository_hosts == empty.repository_hosts == ("github.com", "gitlab.com")
    assert extended.repository_hosts == (
        "github.com",
        "gitlab.com",
        "git.example.com",
        "xn--bcher-kva.example",
    )
    for name in ("duplicate-repository-host.toml", "unsafe-repository-host.toml"):
        with pytest.raises(DomainError) as caught:
            parse_vault_config((CONFIG / "invalid" / name).read_text(encoding="utf-8"))
        assert caught.value.code == "VAULT_INVALID"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0-306-40615-2", "9780306406157"),
        ("978-1-4493-7332-0", "9781449373320"),
    ],
)
def test_isbn_checksum_and_conversion(value: str, expected: str) -> None:
    assert normalize_isbn(value) == expected


@pytest.mark.parametrize("value", ["0306406153", "9781449373321", "not-an-isbn"])
def test_invalid_isbn_is_rejected(value: str) -> None:
    with pytest.raises(DomainError):
        normalize_isbn(value)


def test_url_and_repository_host_normalization() -> None:
    assert canonicalize_web_url("HTTPS://BÜCHER.example:443/a/../b/%7E?q=2&q=1#part") == (
        "https://xn--bcher-kva.example/b/~?q=2&q=1"
    )
    assert normalize_repository_host("Git.Example.COM.") == "git.example.com"
    configured = recognize_capture_input(
        "HTTPS://GIT.EXAMPLE.COM./group/subgroup/project.git/",
        None,
        ("github.com", "gitlab.com", "git.example.com"),
    )
    assert configured.kind == "repo"
    assert configured.repository is not None
    assert configured.repository.host == "git.example.com"
    assert configured.repository.project_path == "group/subgroup/project"
    assert configured.repository.canonical_url == (
        "https://git.example.com/group/subgroup/project"
    )
    for value in ("localhost", "127.0.0.1", "*.example.com", "https://git.example.com"):
        with pytest.raises(DomainError):
            normalize_repository_host(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        " git.example.com",
        "git.example.com ",
        "git example.com",
        "git.example.com:443",
        "user@git.example.com",
        "git.example.com/path",
        "*.example.com",
        "localhost",
        "127.0.0.1",
        "[::1]",
    ],
)
def test_unsafe_repository_host_forms_are_rejected(value: str) -> None:
    with pytest.raises(DomainError) as caught:
        normalize_repository_host(value)
    assert caught.value.code == "VAULT_INVALID"


def test_recognition_order_and_explicit_shapes() -> None:
    hosts = ("github.com", "gitlab.com")
    assert recognize_capture_input("arXiv:2401.12345", None, hosts).kind == "arxiv"
    assert recognize_capture_input("10.1000/example", None, hosts).kind == "doi"
    assert recognize_capture_input("0-306-40615-2", None, hosts).kind == "isbn"
    assert (
        recognize_capture_input("https://github.com/OpenAI/openai-python", None, hosts).kind
        == "repo"
    )
    assert recognize_capture_input("https://git.example.com/acme/repo", None, hosts).kind == "web"
    selected = recognize_capture_input("https://git.example.com/acme/repo", CaptureType.REPO, hosts)
    assert selected.kind == "repo" and selected.requested_type is CaptureType.REPO
    with pytest.raises(DomainError) as caught:
        recognize_capture_input("https://example.com/page", CaptureType.PAPER, hosts)
    assert caught.value.code == "ADD_INPUT_INVALID"


@pytest.mark.parametrize(
    ("value", "requested", "kind"),
    [
        ("10.1000/example", CaptureType.PAPER, "doi"),
        ("arXiv:2401.12345v2", CaptureType.PAPER, "arxiv"),
        ("10.1000/example", CaptureType.BOOK, "doi"),
        ("0-306-40615-2", CaptureType.BOOK, "isbn"),
        ("https://example.test/a/../page#fragment", CaptureType.WEB, "web"),
        ("https://code.example.test/group/project", CaptureType.REPO, "repo"),
    ],
)
def test_every_valid_explicit_recognition_shape(
    value: str, requested: CaptureType, kind: str
) -> None:
    candidate = recognize_capture_input(value, requested)
    assert candidate.requested_type is requested
    assert candidate.kind == kind


@pytest.mark.parametrize(
    "value",
    [
        "git@github.com:acme/project.git",
        "ssh://git@github.com/acme/project.git",
        "file:///tmp/project",
        "C:/project",
        "https://user:secret@github.com/acme/project",
        "https://github.com/acme/project/tree/main",
        "https://github.com/acme/project?ref=main",
        "https://gitlab.com/group/project/-/tree/main",
        "https://github.com/acme",
        "https://github.com../acme/project",
    ],
)
def test_repository_non_root_and_unsafe_inputs_are_rejected(value: str) -> None:
    with pytest.raises(DomainError) as caught:
        normalize_repository_url(value, configured=True)
    assert caught.value.code == "ADD_INPUT_INVALID"


def test_configured_repository_matching_is_exact_and_idna_normalized() -> None:
    hosts = ("github.com", "gitlab.com", "xn--bcher-kva.example")
    accepted = recognize_capture_input("https://BÜCHER.example./team/project", None, hosts)
    rejected = recognize_capture_input("https://sub.bücher.example/team/project", None, hosts)
    assert accepted.kind == "repo"
    assert rejected.kind == "web"


def test_source_specific_locator_coherence_reports_fields() -> None:
    book = parse_object_document((V2 / "valid/book-source-edition.md").read_text(encoding="utf-8"))
    source = book.object
    assert isinstance(source, Source)
    assert source.edition == "Second Edition"
    from knowlume.domain.validation import locator_mismatched_fields

    assert locator_mismatched_fields(BookLocator(isbn="0-306-40615-2", page=1), source) == (
        "isbn",
    )
    assert locator_mismatched_fields(BookLocator(edition="Second Edition", page=1), source) == ()
    assert locator_mismatched_fields(BookLocator(edition="Third Edition", page=1), source) == (
        "edition",
    )

    snapshot = SnapshotRef(
        "zotero",
        "user/0/ABCD1234/EFGH5678",
        datetime(2026, 8, 29, tzinfo=UTC),
        "sha256:" + "1" * 64,
    )
    web_source = replace(
        source,
        source_type=SourceType.WEB,
        isbn=None,
        edition=None,
        canonical_url="https://example.test/",
        captured_at=snapshot.captured_at,
        snapshot_ref=snapshot,
    )
    for field, changed in (
        ("provider", replace(snapshot, provider="other")),
        ("identifier", replace(snapshot, identifier="user/0/OTHER111/OTHER222")),
        ("captured_at", replace(snapshot, captured_at=datetime(2026, 8, 30, tzinfo=UTC))),
        ("content_hash", replace(snapshot, content_hash="sha256:" + "2" * 64)),
    ):
        assert locator_mismatched_fields(WebLocator(changed, paragraph=1), web_source) == (
            f"snapshot_ref.{field}",
        )

    oss_source = replace(
        web_source,
        source_type=SourceType.OSS,
        canonical_url="https://github.com/acme/project",
        captured_at=None,
        snapshot_ref=None,
        repository_host="github.com",
        repository_path="acme/project",
        commit="a" * 40,
        license="NOASSERTION",
    )
    for locator, field in (
        (
            OssLocator("gitlab.com", "acme/project", "a" * 40, "README.md", symbol="title"),
            "repository_host",
        ),
        (
            OssLocator("github.com", "acme/other", "a" * 40, "README.md", symbol="title"),
            "repository_path",
        ),
        (
            OssLocator("github.com", "acme/project", "b" * 40, "README.md", symbol="title"),
            "commit",
        ),
    ):
        assert locator_mismatched_fields(locator, oss_source) == (field,)


def test_fact_and_relation_locator_findings_include_mismatched_fields() -> None:
    source_document = parse_object_document(
        (V2 / "valid/book-source-edition.md").read_text(encoding="utf-8")
    )
    source = source_document.object
    assert isinstance(source, Source)
    note_document = parse_object_document(
        (V2 / "invalid/fact-source-mismatch.md").read_text(encoding="utf-8")
    )
    assert isinstance(note_document.body, NoteBody)
    locator = BookLocator(isbn="0-306-40615-2", edition="Third Edition", page=1)
    sections = tuple(
        replace(
            section,
            blocks=(FactBlock("Mismatched provenance.", (Citation(source.id, locator),)),),
        )
        if any(isinstance(block, FactBlock) for block in section.blocks)
        else section
        for section in note_document.body.sections
    )
    note_document = ObjectDocument(
        note_document.object,
        replace(note_document.body, sections=sections),
    )
    objects = {
        source.id: source_document,
        note_document.object.id: note_document,
    }
    fact_error = next(
        error
        for error in validate_object_references(note_document, objects)
        if error.code == "FACT_LOCATOR_MISMATCH"
    )
    assert fact_error.details == {"fields": ["isbn", "edition"]}

    shard = RelationShard(
        note_document.object.id,
        (
            Relation(
                source.id,
                RelationType.SUMMARIZES,
                datetime(2026, 8, 29, tzinfo=UTC),
                Actor(ActorType.HUMAN, "tester"),
                locator=locator,
            ),
        ),
    )
    relation_error = next(
        error
        for error in validate_relation_shard(
            shard,
            shard_name=str(shard.from_id),
            objects=objects,
            sections={
                note_document.object.id: {
                    str(section.section_id) for section in sections
                }
            },
        )
        if error.code == "RELATION_LOCATOR_MISMATCH"
    )
    assert relation_error.details == {"fields": ["isbn", "edition"]}
