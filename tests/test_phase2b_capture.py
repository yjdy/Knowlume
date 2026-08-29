from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from knowlume.adapters.filesystem import FilesystemVault
from knowlume.application.capture import UnifiedCaptureService
from knowlume.application.scanning import ScanResult, scan_vault
from knowlume.domain.models import SnapshotRef, Source
from knowlume.domain.paper import normalize_arxiv, normalize_doi
from knowlume.domain.values import DomainError
from knowlume.ports.git import RepositoryMetadata
from knowlume.ports.vault import Vault
from knowlume.ports.zotero import (
    AttachmentSelection,
    WebSnapshotMetadata,
    ZoteroItem,
    ZoteroReference,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = (ROOT / "templates/config/v1/knowlume.toml").read_text(encoding="utf-8")
NOW = datetime(2026, 8, 29, 12, tzinfo=UTC)


def _item(
    item_type: str,
    *,
    key: str,
    doi: str | None = None,
    arxiv: str | None = None,
    isbn: str | None = None,
    url: str | None = None,
) -> ZoteroItem:
    return ZoteroItem(
        ZoteroReference("user", "0", key),
        item_type,
        f"Title {key}",
        ("Ada",),
        2026,
        normalize_doi(doi) if doi else None,
        normalize_arxiv(arxiv) if arxiv else None,
        isbn,
        "Second Edition" if item_type == "book" else None,
        url,
        1,
    )


@dataclass
class Zotero:
    candidates: dict[tuple[str, str], tuple[ZoteroItem, ...]]

    def exact_candidates(self, kind: str, value: str) -> tuple[ZoteroItem, ...]:
        return self.candidates.get((kind, value), ())

    def primary_attachment(self, reference: ZoteroReference) -> AttachmentSelection:
        return AttachmentSelection(None, "PAPER_ATTACHMENT_UNAVAILABLE")

    def web_snapshot(self, item: ZoteroItem) -> WebSnapshotMetadata:
        captured = datetime(2026, 8, 29, 10, tzinfo=UTC)
        snapshot = SnapshotRef(
            "zotero",
            f"user/0/{item.reference.item_key}/SNAP1234",
            captured,
            "sha256:" + "1" * 64,
        )
        return WebSnapshotMetadata(
            item.reference,
            item.title,
            item.canonical_url or "",
            item.item_version,
            captured,
            snapshot,
        )

    def metadata(self, reference: ZoteroReference):  # type: ignore[no-untyped-def]
        raise AssertionError("not used")

    def attachment(self, reference: ZoteroReference, attachment_key: str):  # type: ignore[no-untyped-def]
        raise AssertionError("not used")


@dataclass
class Repositories:
    commit: str = "a" * 40

    def resolve(self, repository) -> RepositoryMetadata:  # type: ignore[no-untyped-def]
        return RepositoryMetadata(
            repository.project_path.rsplit("/", 1)[-1],
            repository.canonical_url,
            repository.host,
            repository.project_path,
            "main",
            self.commit,
        )


def _vault(tmp_path: Path) -> tuple[FilesystemVault, Vault]:
    filesystem = FilesystemVault(environment={})
    return filesystem, filesystem.initialize(tmp_path / "vault", CONFIG)


def _service(
    filesystem: FilesystemVault,
    zotero: Zotero,
    repositories: Repositories | None = None,
) -> UnifiedCaptureService:
    ids = iter(
        [
            "01JSTAG7N9Q3V5X8Y2Z4A6B8G0",
            "01JSTAG7N9Q3V5X8Y2Z4A6B8G1",
            "01JSTAG7N9Q3V5X8Y2Z4A6B8G2",
            "01JSTAG7N9Q3V5X8Y2Z4A6B8G3",
            "01JSTAG7N9Q3V5X8Y2Z4A6B8G4",
        ]
    )
    return UnifiedCaptureService(
        filesystem=filesystem,
        zotero=zotero,
        repositories=repositories or Repositories(),
        clock=lambda: NOW,
        ulid_factory=lambda: next(ids),
    )


def test_all_four_capture_paths_are_private_idempotent_and_use_one_service(tmp_path: Path) -> None:
    filesystem, vault = _vault(tmp_path)
    web_url = "https://example.test/page"
    zotero = Zotero(
        {
            ("arxiv", "2401.12345"): (_item("journalArticle", key="PAPER001", arxiv="2401.12345"),),
            ("isbn", "9780306406157"): (
                _item(
                    "book",
                    key="BOOK0001",
                    isbn="9780306406157",
                    doi="10.1000/example-book",
                ),
            ),
            ("url", web_url): (_item("webpage", key="WEBP0001", url=web_url),),
        }
    )
    service = _service(filesystem, zotero)
    paper = service.add(vault, "arXiv:2401.12345")
    book = service.add(vault, "0-306-40615-2")
    web = service.add(vault, web_url)
    repo = service.add(vault, "https://github.com/OpenAI/openai-python")
    assert [result.detected_type for result in (paper, book, web, repo)] == [
        "paper",
        "book",
        "web",
        "repo",
    ]
    assert book.canonical_identity == "isbn:9780306406157"
    assert repo.source_type == "oss"
    assert repo.canonical_identity.endswith("@" + "a" * 40)
    repeats = (
        service.add(vault, "arXiv:2401.12345"),
        service.add(vault, "9780306406157"),
        service.add(vault, web_url),
        service.add(vault, "https://github.com/OpenAI/openai-python.git/"),
    )
    assert [result.source_id for result in repeats] == [
        paper.source_id,
        book.source_id,
        web.source_id,
        repo.source_id,
    ]
    assert all(result.created is False for result in repeats)
    scan = scan_vault(vault)
    assert scan.healthy and len(scan.objects) == 4 and not scan.relation_shards
    sources = [entry.document.object for entry in scan.objects.values()]
    assert all(
        isinstance(source, Source) and source.visibility.value == "private" for source in sources
    )


@pytest.mark.parametrize(
    "items",
    [
        (),
        (
            _item("journalArticle", key="PAPER001", doi="10.1000/example"),
            _item("book", key="BOOK0001", doi="10.1000/example"),
        ),
        (_item("bookSection", key="SECT0001", doi="10.1000/example"),),
    ],
)
def test_automatic_doi_ambiguity_writes_nothing(
    tmp_path: Path, items: tuple[ZoteroItem, ...]
) -> None:
    filesystem, vault = _vault(tmp_path)
    service = _service(filesystem, Zotero({("doi", "10.1000/example"): items}))
    with pytest.raises(DomainError) as caught:
        service.add(vault, "10.1000/example")
    assert caught.value.code == "ADD_TYPE_AMBIGUOUS"
    assert scan_vault(vault).objects == {}


def test_cross_paper_book_doi_collision_is_identity_conflict(tmp_path: Path) -> None:
    filesystem, vault = _vault(tmp_path)
    zotero = Zotero(
        {
            ("doi", "10.1000/example"): (
                _item("journalArticle", key="PAPER001", doi="10.1000/example"),
            )
        }
    )
    service = _service(filesystem, zotero)
    service.add(vault, "10.1000/example", "paper")
    zotero.candidates[("doi", "10.1000/example")] = (
        _item("book", key="BOOK0001", doi="10.1000/example"),
    )
    with pytest.raises(DomainError) as caught:
        service.add(vault, "10.1000/example", "book")
    assert caught.value.code == "ADD_IDENTITY_CONFLICT"
    assert len(scan_vault(vault).objects) == 1


def test_changed_repository_head_creates_a_distinct_source(tmp_path: Path) -> None:
    filesystem, vault = _vault(tmp_path)
    repositories = Repositories()
    service = _service(filesystem, Zotero({}), repositories)
    first = service.add(vault, "https://github.com/acme/project")
    repositories.commit = "b" * 40
    second = service.add(vault, "https://github.com/acme/project")
    assert first.source_id != second.source_id
    assert len(scan_vault(vault).objects) == 2


@pytest.mark.parametrize(
    "item_type",
    ["journalArticle", "conferencePaper", "preprint", "thesis", "report", "manuscript"],
)
def test_automatic_doi_classifies_each_paper_whitelist_type(
    tmp_path: Path, item_type: str
) -> None:
    filesystem, vault = _vault(tmp_path)
    item = _item(item_type, key="PAPER001", doi="10.1000/example")
    result = _service(
        filesystem, Zotero({("doi", "10.1000/example"): (item,)})
    ).add(vault, "10.1000/example")
    assert result.detected_type == "paper" and result.requested_type is None


def test_automatic_doi_classifies_top_level_book(tmp_path: Path) -> None:
    filesystem, vault = _vault(tmp_path)
    item = _item("book", key="BOOK0001", doi="10.1000/example")
    result = _service(
        filesystem, Zotero({("doi", "10.1000/example"): (item,)})
    ).add(vault, "10.1000/example")
    assert result.detected_type == "book" and result.source_type == "book"


@pytest.mark.parametrize("item_type", ["bookSection", "document", None])
def test_automatic_doi_rejects_unsupported_or_missing_item_type(
    tmp_path: Path, item_type: str | None
) -> None:
    filesystem, vault = _vault(tmp_path)
    item = _item("document", key="OTHER001", doi="10.1000/example")
    item = ZoteroItem(
        item.reference,
        item_type,
        item.title,
        item.authors,
        item.year,
        item.doi,
        item.arxiv,
        item.isbn,
        item.edition,
        item.canonical_url,
        item.item_version,
    )
    service = _service(filesystem, Zotero({("doi", "10.1000/example"): (item,)}))
    with pytest.raises(DomainError) as caught:
        service.add(vault, "10.1000/example")
    assert caught.value.code == "ADD_TYPE_AMBIGUOUS"
    assert scan_vault(vault).objects == {}


@pytest.mark.parametrize(
    ("requested", "items"),
    [
        ("paper", ()),
        ("paper", (_item("journalArticle", key="PAPER001", doi="10.1000/example"),) * 2),
        ("paper", (_item("book", key="BOOK0001", doi="10.1000/example"),)),
        ("book", ()),
        ("book", (_item("book", key="BOOK0001", doi="10.1000/example"),) * 2),
        ("book", (_item("journalArticle", key="PAPER001", doi="10.1000/example"),)),
    ],
)
def test_explicit_doi_selection_rejects_missing_multiple_or_incompatible_candidates(
    tmp_path: Path, requested: str, items: tuple[ZoteroItem, ...]
) -> None:
    filesystem, vault = _vault(tmp_path)
    service = _service(filesystem, Zotero({("doi", "10.1000/example"): items}))
    with pytest.raises(DomainError) as caught:
        service.add(vault, "10.1000/example", requested)
    assert caught.value.code == "ADD_METADATA_UNAVAILABLE"
    assert scan_vault(vault).objects == {}


def test_paper_and_book_aliases_converge_on_one_source(tmp_path: Path) -> None:
    filesystem, vault = _vault(tmp_path)
    paper = _item(
        "journalArticle",
        key="PAPER001",
        doi="10.1000/paper",
        arxiv="2401.12345",
    )
    book = _item(
        "book",
        key="BOOK0001",
        doi="10.1000/book",
        isbn="9780306406157",
    )
    service = _service(
        filesystem,
        Zotero(
            {
                ("doi", "10.1000/paper"): (paper,),
                ("arxiv", "2401.12345"): (paper,),
                ("doi", "10.1000/book"): (book,),
                ("isbn", "9780306406157"): (book,),
            }
        ),
    )
    paper_doi = service.add(vault, "10.1000/paper")
    paper_arxiv = service.add(vault, "arXiv:2401.12345")
    book_doi = service.add(vault, "10.1000/book")
    book_isbn = service.add(vault, "0-306-40615-2")
    assert paper_doi.source_id == paper_arxiv.source_id
    assert book_doi.source_id == book_isbn.source_id
    assert len(scan_vault(vault).objects) == 2


def _vault_bytes(vault: Vault) -> dict[str, bytes]:
    return {
        path.relative_to(vault.root).as_posix(): path.read_bytes()
        for path in vault.root.rglob("*")
        if path.is_file()
    }


def test_post_write_scanner_failure_rolls_back_byte_identically(tmp_path: Path) -> None:
    filesystem, vault = _vault(tmp_path)
    before = _vault_bytes(vault)
    calls = 0

    def scanner(current: Vault) -> ScanResult:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise DomainError("INTERNAL_SCAN_FAILURE", "must not leak")
        return scan_vault(current)

    service = UnifiedCaptureService(
        filesystem=filesystem,
        zotero=Zotero({}),
        repositories=Repositories(),
        scanner=scanner,
        clock=lambda: NOW,
        ulid_factory=lambda: "01JSTAG7N9Q3V5X8Y2Z4A6B8G0",
    )
    with pytest.raises(DomainError) as caught:
        service.add(vault, "https://github.com/acme/project")
    assert caught.value.code == "ADD_WRITE_CONFLICT"
    assert _vault_bytes(vault) == before
    assert not any(
        any(vault.path("state").joinpath(name).iterdir())
        for name in ("transactions", "locks")
    )


def test_post_write_interruption_rolls_back_and_propagates(tmp_path: Path) -> None:
    filesystem, vault = _vault(tmp_path)
    before = _vault_bytes(vault)
    calls = 0

    def scanner(current: Vault) -> ScanResult:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        return scan_vault(current)

    service = UnifiedCaptureService(
        filesystem=filesystem,
        zotero=Zotero({}),
        repositories=Repositories(),
        scanner=scanner,
        clock=lambda: NOW,
        ulid_factory=lambda: "01JSTAG7N9Q3V5X8Y2Z4A6B8G0",
    )
    with pytest.raises(KeyboardInterrupt):
        service.add(vault, "https://github.com/acme/project")
    assert _vault_bytes(vault) == before


def test_atomic_write_interruption_after_replace_rolls_back(tmp_path: Path) -> None:
    class InterruptingFilesystem(FilesystemVault):
        def atomic_write(
            self,
            vault: Vault,
            relative_path: str,
            content: bytes,
            expected_checksum: str | None,
        ) -> str:
            super().atomic_write(vault, relative_path, content, expected_checksum)
            raise KeyboardInterrupt

    filesystem = InterruptingFilesystem(environment={})
    vault = filesystem.initialize(tmp_path / "vault", CONFIG)
    before = _vault_bytes(vault)
    service = UnifiedCaptureService(
        filesystem=filesystem,
        zotero=Zotero({}),
        repositories=Repositories(),
        clock=lambda: NOW,
        ulid_factory=lambda: "01JSTAG7N9Q3V5X8Y2Z4A6B8G0",
    )
    with pytest.raises(KeyboardInterrupt):
        service.add(vault, "https://github.com/acme/project")
    assert _vault_bytes(vault) == before


def test_target_conflict_preserves_existing_source_bytes(tmp_path: Path) -> None:
    filesystem, vault = _vault(tmp_path)
    repositories = Repositories()
    service = UnifiedCaptureService(
        filesystem=filesystem,
        zotero=Zotero({}),
        repositories=repositories,
        clock=lambda: NOW,
        ulid_factory=lambda: "01JSTAG7N9Q3V5X8Y2Z4A6B8G0",
    )
    service.add(vault, "https://github.com/acme/project")
    before = _vault_bytes(vault)
    repositories.commit = "b" * 40
    with pytest.raises(DomainError) as caught:
        service.add(vault, "https://github.com/acme/project")
    assert caught.value.code == "ADD_WRITE_CONFLICT"
    assert _vault_bytes(vault) == before


@pytest.mark.parametrize("backend", ["zotero", "git"])
def test_adapter_failures_leave_vault_byte_identical(tmp_path: Path, backend: str) -> None:
    filesystem, vault = _vault(tmp_path)
    before = _vault_bytes(vault)

    class FailedZotero(Zotero):
        def exact_candidates(self, kind: str, value: str) -> tuple[ZoteroItem, ...]:
            raise DomainError("ZOTERO_API_UNAVAILABLE", "secret adapter detail")

    class FailedRepositories(Repositories):
        def resolve(self, repository):  # type: ignore[no-untyped-def]
            raise DomainError("GIT_REMOTE_UNAVAILABLE", "secret adapter detail")

    service = _service(
        filesystem,
        FailedZotero({}) if backend == "zotero" else Zotero({}),
        FailedRepositories() if backend == "git" else Repositories(),
    )
    value = "10.1000/example" if backend == "zotero" else "https://github.com/acme/project"
    with pytest.raises(DomainError) as caught:
        service.add(vault, value)
    assert caught.value.code == "ADD_METADATA_UNAVAILABLE"
    assert "secret" not in str(caught.value)
    assert _vault_bytes(vault) == before


@pytest.mark.parametrize("requested", ["paper", "book"])
def test_explicit_zotero_capture_absent_capability_is_publicly_typed(
    tmp_path: Path, requested: str
) -> None:
    filesystem, vault = _vault(tmp_path)

    class MissingZotero(Zotero):
        def exact_candidates(self, kind: str, value: str) -> tuple[ZoteroItem, ...]:
            raise DomainError(
                "ZOTERO_CAPABILITY_UNAVAILABLE", "internal dependency diagnostic"
            )

    service = _service(filesystem, MissingZotero({}))
    with pytest.raises(DomainError) as caught:
        service.add(vault, "10.1000/example", requested)
    assert caught.value.code == "ADD_METADATA_UNAVAILABLE"
    assert "dependency" not in str(caught.value)
    assert scan_vault(vault).objects == {}


def test_web_source_capture_time_and_snapshot_time_are_identical(tmp_path: Path) -> None:
    filesystem, vault = _vault(tmp_path)
    url = "https://example.test/page"
    result = _service(
        filesystem,
        Zotero({("url", url): (_item("webpage", key="WEBP0001", url=url),)}),
    ).add(vault, url)
    source = scan_vault(vault).objects[result.source_id].document.object
    assert isinstance(source, Source)
    assert source.snapshot_ref is not None
    assert source.captured_at == source.snapshot_ref.captured_at
