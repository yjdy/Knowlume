from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from knowlume.adapters.contract_v2 import parse_object_document, render_object_document
from knowlume.adapters.filesystem import FilesystemVault, checksum_bytes, checksum_file
from knowlume.application.paper_capture import _managed_fields
from knowlume.application.scanning import ScanResult, scan_vault
from knowlume.domain.capture import (
    CaptureCandidate,
    CaptureType,
    recognize_capture_input,
)
from knowlume.domain.isbn import normalize_isbn
from knowlume.domain.models import ObjectDocument, Source
from knowlume.domain.paper import managed_fields_hash, normalize_arxiv, normalize_doi
from knowlume.domain.values import (
    DomainError,
    ObjectId,
    RecordStatus,
    SourceType,
    Visibility,
    WorkflowStage,
)
from knowlume.ids import new_ulid
from knowlume.ports.git import RepositoryMetadata, RepositoryMetadataPort
from knowlume.ports.vault import Vault
from knowlume.ports.zotero import AttachmentSelection, ZoteroCapturePort, ZoteroItem

PAPER_ITEM_TYPES = frozenset(
    {"journalArticle", "conferencePaper", "preprint", "thesis", "report", "manuscript"}
)


@dataclass(frozen=True)
class AddResult:
    input: str
    requested_type: str | None
    detected_type: str
    source_type: str
    canonical_identity: str
    source_id: ObjectId
    created: bool
    warnings: tuple[str, ...] = ()

    def data(self) -> dict[str, Any]:
        return {
            "input": self.input,
            "requested_type": self.requested_type,
            "detected_type": self.detected_type,
            "source_type": self.source_type,
            "canonical_identity": self.canonical_identity,
            "source_id": str(self.source_id),
            "created": self.created,
        }


def _aliases(source: Source) -> tuple[str, ...]:
    values: list[str] = []
    if source.source_type is SourceType.PAPER:
        if source.doi:
            try:
                values.append(f"doi:{normalize_doi(source.doi)}")
            except DomainError:
                pass
        if source.arxiv_id:
            try:
                values.append(f"arxiv:{normalize_arxiv(source.arxiv_id).base_id}")
            except DomainError:
                pass
    elif source.source_type is SourceType.BOOK:
        if source.isbn:
            try:
                values.append(f"isbn:{normalize_isbn(source.isbn)}")
            except DomainError:
                pass
        if source.doi:
            try:
                values.append(f"doi:{normalize_doi(source.doi)}")
            except DomainError:
                pass
    elif source.source_type is SourceType.WEB and source.canonical_url:
        values.append(f"url:{source.canonical_url}")
    elif source.source_type is SourceType.OSS and all(
        (source.repository_host, source.repository_path, source.commit)
    ):
        values.append(f"repo:{source.repository_host}/{source.repository_path}@{source.commit}")
    return tuple(values)


def _canonical_identity(source: Source) -> str:
    aliases = _aliases(source)
    if not aliases:
        raise DomainError("ADD_IDENTITY_CONFLICT", "Source has no canonical capture identity")
    if source.source_type is SourceType.PAPER:
        order = {"doi": 0, "arxiv": 1}
    elif source.source_type is SourceType.BOOK:
        order = {"isbn": 0, "doi": 1}
    else:
        order = {"url": 0, "repo": 0}
    return min(aliases, key=lambda value: order.get(value.split(":", 1)[0], 99))


def _external_failure(error: DomainError) -> DomainError:
    if error.code.startswith("ADD_"):
        return error
    return DomainError("ADD_METADATA_UNAVAILABLE", "required capture metadata is unavailable")


class UnifiedCaptureService:
    def __init__(
        self,
        *,
        filesystem: FilesystemVault,
        zotero: ZoteroCapturePort,
        repositories: RepositoryMetadataPort,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        ulid_factory: Callable[[], str] = new_ulid,
        scanner: Callable[[Vault], ScanResult] = scan_vault,
    ) -> None:
        self._filesystem = filesystem
        self._zotero = zotero
        self._repositories = repositories
        self._clock = clock
        self._ulid_factory = ulid_factory
        self._scanner = scanner

    @staticmethod
    def _sources(result: ScanResult) -> tuple[Source, ...]:
        return tuple(
            scanned.document.object
            for scanned in result.objects.values()
            if isinstance(scanned.document.object, Source)
        )

    def _existing(
        self,
        sources: Iterable[Source],
        aliases: Iterable[str],
        expected: SourceType,
    ) -> Source | None:
        wanted = set(aliases)
        matches = [source for source in sources if wanted.intersection(_aliases(source))]
        ids = {source.id for source in matches}
        if len(ids) > 1 or any(source.source_type is not expected for source in matches):
            raise DomainError(
                "ADD_IDENTITY_CONFLICT", "capture identities resolve to conflicting Sources"
            )
        return matches[0] if matches else None

    @staticmethod
    def _result(
        candidate: CaptureCandidate,
        detected: CaptureType,
        source: Source,
        created: bool,
        warnings: tuple[str, ...] = (),
    ) -> AddResult:
        return AddResult(
            candidate.raw_input,
            candidate.requested_type.value if candidate.requested_type else None,
            detected.value,
            source.source_type.value,
            _canonical_identity(source),
            source.id,
            created,
            warnings,
        )

    def _exact(self, kind: str, value: str) -> tuple[ZoteroItem, ...]:
        try:
            return self._zotero.exact_candidates(kind, value)
        except DomainError as error:
            raise _external_failure(error) from error

    def _select_zotero(self, candidate: CaptureCandidate) -> tuple[CaptureType, ZoteroItem]:
        if candidate.kind == "doi":
            assert candidate.doi is not None
            items = self._exact("doi", str(candidate.doi))
            requested = candidate.requested_type
            if requested in {CaptureType.PAPER, CaptureType.BOOK}:
                eligible = len(items) == 1 and (
                    items[0].item_type in PAPER_ITEM_TYPES
                    if requested is CaptureType.PAPER
                    else items[0].item_type == "book"
                )
                if not eligible:
                    raise DomainError(
                        "ADD_METADATA_UNAVAILABLE", "exact Zotero metadata is unavailable"
                    )
                return requested, items[0]
            if len(items) != 1:
                raise DomainError("ADD_TYPE_AMBIGUOUS", "DOI capture type is ambiguous")
            item = items[0]
            if item.item_type in PAPER_ITEM_TYPES:
                return CaptureType.PAPER, item
            if item.item_type == "book":
                return CaptureType.BOOK, item
            raise DomainError("ADD_TYPE_AMBIGUOUS", "DOI capture type is ambiguous")
        if candidate.kind == "arxiv":
            assert candidate.arxiv is not None
            items = self._exact("arxiv", candidate.arxiv.base_id)
            if len(items) != 1 or items[0].item_type not in PAPER_ITEM_TYPES:
                raise DomainError("ADD_METADATA_UNAVAILABLE", "exact Paper metadata is unavailable")
            return CaptureType.PAPER, items[0]
        if candidate.kind == "isbn":
            assert candidate.isbn is not None
            items = self._exact("isbn", candidate.isbn)
            if len(items) != 1 or items[0].item_type != "book":
                raise DomainError("ADD_METADATA_UNAVAILABLE", "exact Book metadata is unavailable")
            return CaptureType.BOOK, items[0]
        assert candidate.kind == "web" and candidate.canonical_url is not None
        items = self._exact("url", candidate.canonical_url)
        if len(items) != 1 or items[0].item_type != "webpage":
            raise DomainError("ADD_METADATA_UNAVAILABLE", "exact Web metadata is unavailable")
        return CaptureType.WEB, items[0]

    def _preexisting(
        self, candidate: CaptureCandidate, sources: tuple[Source, ...]
    ) -> AddResult | None:
        alias: str | None = None
        expected: SourceType | None = None
        detected: CaptureType | None = None
        if candidate.kind == "arxiv" and candidate.arxiv:
            alias, expected, detected = (
                f"arxiv:{candidate.arxiv.base_id}",
                SourceType.PAPER,
                CaptureType.PAPER,
            )
        elif candidate.kind == "isbn" and candidate.isbn:
            alias, expected, detected = (
                f"isbn:{candidate.isbn}",
                SourceType.BOOK,
                CaptureType.BOOK,
            )
        elif candidate.kind == "web" and candidate.canonical_url:
            alias, expected, detected = (
                f"url:{candidate.canonical_url}",
                SourceType.WEB,
                CaptureType.WEB,
            )
        elif candidate.kind == "doi" and candidate.doi:
            requested = candidate.requested_type
            alias = f"doi:{candidate.doi}"
            if requested is CaptureType.PAPER:
                expected, detected = SourceType.PAPER, CaptureType.PAPER
            elif requested is CaptureType.BOOK:
                expected, detected = SourceType.BOOK, CaptureType.BOOK
            else:
                matches = [source for source in sources if alias in _aliases(source)]
                if len({source.id for source in matches}) > 1:
                    raise DomainError(
                        "ADD_IDENTITY_CONFLICT", "DOI resolves to conflicting Sources"
                    )
                if matches:
                    source = matches[0]
                    detected = (
                        CaptureType.PAPER
                        if source.source_type is SourceType.PAPER
                        else CaptureType.BOOK
                    )
                    return self._result(candidate, detected, source, False)
        if alias and expected and detected:
            matched_source = self._existing(sources, (alias,), expected)
            if matched_source:
                return self._result(candidate, detected, matched_source, False)
        return None

    def add(
        self, vault: Vault, value: str, requested_type: CaptureType | str | None = None
    ) -> AddResult:
        try:
            return self._add(vault, value, requested_type)
        except DomainError as error:
            if error.code.startswith("ADD_"):
                raise
            if error.code in {
                "VAULT_LOCKED",
                "VAULT_RECOVERY_REQUIRED",
                "VAULT_WRITE_CONFLICT",
            }:
                raise DomainError(
                    "ADD_WRITE_CONFLICT", "durable Source changed concurrently"
                ) from error
            raise DomainError(
                "ADD_METADATA_UNAVAILABLE", "required capture metadata is unavailable"
            ) from error

    def _add(
        self, vault: Vault, value: str, requested_type: CaptureType | str | None = None
    ) -> AddResult:
        try:
            initial = self._scanner(vault)
        except DomainError as error:
            raise DomainError("ADD_WRITE_CONFLICT", "Vault scan is unavailable") from error
        if not initial.healthy:
            raise DomainError("ADD_WRITE_CONFLICT", "Vault must pass scan before capture")
        candidate = recognize_capture_input(value, requested_type, vault.config.repository_hosts)
        sources = self._sources(initial)
        if candidate.kind != "repo" and (preexisting := self._preexisting(candidate, sources)):
            return preexisting

        now = self._clock()
        warnings: tuple[str, ...] = ()
        if candidate.kind == "repo":
            assert candidate.repository is not None
            try:
                repository = self._repositories.resolve(candidate.repository)
            except DomainError as error:
                raise _external_failure(error) from error
            detected = CaptureType.REPO
            source = self._repository_source(repository, now)
        else:
            detected, item = self._select_zotero(candidate)
            if detected is CaptureType.PAPER:
                source, warnings = self._paper_source(item, now)
            elif detected is CaptureType.BOOK:
                source = self._book_source(item, now)
            else:
                try:
                    snapshot = self._zotero.web_snapshot(item)
                except DomainError as error:
                    raise _external_failure(error) from error
                if snapshot.canonical_url != candidate.canonical_url:
                    raise DomainError(
                        "ADD_METADATA_UNAVAILABLE", "Web snapshot URL does not match input"
                    )
                source = Source(
                    id=ObjectId(f"src_{self._ulid_factory()}"),
                    source_type=SourceType.WEB,
                    title=snapshot.title,
                    visibility=Visibility.PRIVATE,
                    record_status=RecordStatus.ACTIVE,
                    workflow_stage=WorkflowStage.INBOX,
                    created=now.date(),
                    updated=now.date(),
                    tags=(),
                    captured_at=snapshot.captured_at,
                    canonical_url=snapshot.canonical_url,
                    snapshot_ref=snapshot.snapshot_ref,
                    zotero_library_id=snapshot.reference.library_id,
                    zotero_library_type=snapshot.reference.library_type,
                    zotero_key=snapshot.reference.item_key,
                    zotero_item_version=snapshot.item_version,
                    synced_at=now,
                )

        aliases = _aliases(source)
        matched = self._existing(sources, aliases, source.source_type)
        if matched:
            return self._result(candidate, detected, matched, False, warnings)
        return self._write(vault, candidate, detected, source, warnings)

    def _paper_source(self, item: ZoteroItem, now: datetime) -> tuple[Source, tuple[str, ...]]:
        identity = item.paper_identity
        if identity is None:
            raise DomainError("ADD_METADATA_UNAVAILABLE", "Paper identity is unavailable")
        try:
            selection = self._zotero.primary_attachment(item.reference)
        except DomainError as error:
            raise _external_failure(error) from error
        assert isinstance(selection, AttachmentSelection)
        attachment = selection.attachment
        warnings = (selection.warning_code,) if selection.warning_code else ()
        source = Source(
            id=ObjectId(f"src_{self._ulid_factory()}"),
            source_type=SourceType.PAPER,
            title=item.title,
            visibility=Visibility.PRIVATE,
            record_status=RecordStatus.ACTIVE,
            workflow_stage=WorkflowStage.INBOX,
            created=now.date(),
            updated=now.date(),
            tags=(),
            canonical_url=item.canonical_url,
            zotero_library_id=item.reference.library_id,
            zotero_library_type=item.reference.library_type,
            zotero_key=item.reference.item_key,
            zotero_item_version=item.item_version,
            synced_at=now,
            attachment_key=attachment.key if attachment else None,
            attachment_version=attachment.version if attachment else None,
            attachment_filename=attachment.filename if attachment else None,
            attachment_media_type=attachment.media_type if attachment else None,
            attachment_size=attachment.size if attachment else None,
            attachment_sha256=attachment.sha256 if attachment else None,
            doi=str(identity.doi) if identity.doi else None,
            arxiv_id=identity.arxiv.base_id if identity.arxiv else None,
            arxiv_version=identity.arxiv.version if identity.arxiv else None,
            year=item.year,
            authors=item.authors,
        )
        return replace(
            source, managed_fields_hash=managed_fields_hash(_managed_fields(source))
        ), warnings

    def _book_source(self, item: ZoteroItem, now: datetime) -> Source:
        if item.isbn is None and item.doi is None:
            raise DomainError("ADD_METADATA_UNAVAILABLE", "Book identity is unavailable")
        return Source(
            id=ObjectId(f"src_{self._ulid_factory()}"),
            source_type=SourceType.BOOK,
            title=item.title,
            visibility=Visibility.PRIVATE,
            record_status=RecordStatus.ACTIVE,
            workflow_stage=WorkflowStage.INBOX,
            created=now.date(),
            updated=now.date(),
            tags=(),
            canonical_url=item.canonical_url,
            zotero_library_id=item.reference.library_id,
            zotero_library_type=item.reference.library_type,
            zotero_key=item.reference.item_key,
            zotero_item_version=item.item_version,
            synced_at=now,
            isbn=item.isbn,
            edition=item.edition,
            doi=str(item.doi) if item.doi else None,
            year=item.year,
            authors=item.authors,
        )

    def _repository_source(self, repository: RepositoryMetadata, now: datetime) -> Source:
        return Source(
            id=ObjectId(f"src_{self._ulid_factory()}"),
            source_type=SourceType.OSS,
            title=repository.title,
            visibility=Visibility.PRIVATE,
            record_status=RecordStatus.ACTIVE,
            workflow_stage=WorkflowStage.INBOX,
            created=now.date(),
            updated=now.date(),
            tags=(),
            canonical_url=repository.canonical_url,
            repository_host=repository.host,
            repository_path=repository.project_path,
            default_branch=repository.default_branch,
            commit=repository.commit,
            license="NOASSERTION",
        )

    def _write(
        self,
        vault: Vault,
        candidate: CaptureCandidate,
        detected: CaptureType,
        source: Source,
        warnings: tuple[str, ...],
    ) -> AddResult:
        document = ObjectDocument(
            source,
            f"# {source.title}\n\n## Capture notes\n\nCaptured by kb add.",
        )
        content = render_object_document(document).encode("utf-8")
        if parse_object_document(content.decode("utf-8")) != document:
            raise DomainError("ADD_METADATA_UNAVAILABLE", "constructed Source is invalid")
        directory = {
            SourceType.PAPER: "papers",
            SourceType.WEB: "web",
            SourceType.BOOK: "books",
            SourceType.OSS: "oss",
        }[source.source_type]
        relative = f"{vault.config.sources}/{directory}/{source.id}.md"
        try:
            checksum = self._filesystem.atomic_write(vault, relative, content, None)
        except DomainError as error:
            if error.code in {"VAULT_WRITE_CONFLICT", "VAULT_LOCKED", "VAULT_RECOVERY_REQUIRED"}:
                raise DomainError(
                    "ADD_WRITE_CONFLICT", "durable Source changed concurrently"
                ) from error
            raise
        except BaseException as error:
            destination = vault.root.joinpath(*relative.split("/"))
            expected = checksum_bytes(content)
            if checksum_file(destination) == expected:
                try:
                    self._filesystem.atomic_delete(vault, relative, expected)
                except DomainError as rollback_error:
                    raise DomainError(
                        "ADD_WRITE_CONFLICT", "captured Source rollback conflicted"
                    ) from rollback_error
            if isinstance(error, Exception):
                raise DomainError(
                    "ADD_WRITE_CONFLICT", "captured Source write was interrupted"
                ) from error
            raise
        scan_error: BaseException | None = None
        accepted: ScanResult | None = None
        try:
            accepted = self._scanner(vault)
        except BaseException as error:
            # The just-created Source is the only durable change owned by this
            # operation, so remove it before propagating an interruption or
            # translating a scanner failure.  Atomic delete still protects a
            # concurrent user edit through the expected checksum.
            scan_error = error
        if (
            scan_error is not None
            or accepted is None
            or not accepted.healthy
            or source.id not in accepted.objects
        ):
            try:
                self._filesystem.atomic_delete(vault, relative, checksum)
            except DomainError as error:
                raise DomainError(
                    "ADD_WRITE_CONFLICT", "captured Source rollback conflicted"
                ) from error
            if scan_error is not None and not isinstance(scan_error, Exception):
                raise scan_error
            raise DomainError("ADD_WRITE_CONFLICT", "captured Source failed validation")
        return self._result(candidate, detected, source, True, warnings)
