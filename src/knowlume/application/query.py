from __future__ import annotations

import re
import unicodedata
from bisect import bisect_right

from knowlume.adapters.contract_v2 import (
    locator_data,
    note_body_data,
    object_data,
    parse_locator,
)
from knowlume.application.scanning import ScanResult, scan_vault
from knowlume.constants import PROJECTION_VERSION, SEGMENT_ALGORITHM_VERSION, TOKENIZER_VERSION
from knowlume.domain.models import FactBlock, NoteBody, Relation, Snippet, Source
from knowlume.domain.search import ContextScope, SearchFilters, SearchHit
from knowlume.domain.validation import locator_mismatched_fields
from knowlume.domain.values import DomainError, ObjectId, RecordStatus, Visibility
from knowlume.ports.search import SearchBackend
from knowlume.ports.vault import Vault

_SECTION_MARKER = re.compile(r"<!--\s*knowlume:section\s+id=(sec_[a-z0-9][a-z0-9_-]{2,63})\b")


def _validate_limit(limit: int) -> None:
    if not 1 <= limit <= 200:
        raise DomainError("SEARCH_QUERY_INVALID", "limit must be between 1 and 200")


def _normalized_query(query: str) -> str:
    value = unicodedata.normalize("NFKC", query).casefold()
    if not any(unicodedata.category(character)[0] in {"L", "N"} for character in value):
        raise DomainError("SEARCH_QUERY_INVALID", "query must contain a letter or number")
    return value


def _original_column(line: str, normalized_column: int) -> int:
    """Map a casefolded NFKC offset back to a one-based source column."""

    boundaries = [
        len(unicodedata.normalize("NFKC", line[:index]).casefold())
        for index in range(len(line) + 1)
    ]
    return max(0, bisect_right(boundaries, normalized_column) - 1) + 1


def grep_vault(vault: Vault, query: str, limit: int = 20) -> dict[str, object]:
    _validate_limit(limit)
    normalized = _normalized_query(query)
    scan = scan_vault(vault)
    identity_by_path = {item.path: str(object_id) for object_id, item in scan.objects.items()} | {
        item.path: str(object_id) for object_id, item in scan.relation_shards.items()
    }
    roots = (
        vault.path("sources"),
        vault.path("notes"),
        vault.path("snippets"),
        vault.path("ai_artifacts"),
        vault.path("relations"),
    )
    paths = sorted(
        (path for root in roots for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(vault.root).as_posix(),
    )
    hits: list[dict[str, object]] = []
    for path in paths:
        try:
            path.resolve(strict=True).relative_to(vault.root)
        except (OSError, ValueError):
            continue
        relative = path.relative_to(vault.root).as_posix()
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        active_section: str | None = None
        for line_number, line in enumerate(lines, 1):
            if marker := _SECTION_MARKER.search(line):
                active_section = marker.group(1)
            folded = unicodedata.normalize("NFKC", line).casefold()
            start = 0
            while (column := folded.find(normalized, start)) >= 0:
                item: dict[str, object] = {
                    "path": relative,
                    "line": line_number,
                    "column": _original_column(line, column),
                    "excerpt": line.strip(),
                }
                if identity := identity_by_path.get(relative):
                    item["object_id"] = identity
                if active_section and relative.endswith(".md"):
                    item["section_id"] = active_section
                hits.append(item)
                if len(hits) >= limit:
                    return {"query": query, "limit": limit, "hits": hits, "count": len(hits)}
                start = column + max(1, len(normalized))
    return {"query": query, "limit": limit, "hits": hits, "count": len(hits)}


def _relation_data(from_id: str, relation: Relation) -> dict[str, object]:
    result: dict[str, object] = {
        "from_id": from_id,
        "to_id": str(relation.to_id),
        "relation_type": relation.relation_type.value,
        "created_at": relation.created_at.isoformat(),
        "actor": {"type": relation.actor.type.value, "id": relation.actor.id},
    }
    if relation.to_section_id:
        result["to_section_id"] = str(relation.to_section_id)
    if relation.locator:
        result["locator"] = locator_data(relation.locator)
    if relation.reason:
        result["reason"] = relation.reason
    return result


def get_object(vault: Vault, object_id_value: str) -> dict[str, object]:
    try:
        object_id = ObjectId(object_id_value)
    except DomainError as error:
        raise DomainError("OBJECT_NOT_FOUND", "object ID was not found") from error
    scan = scan_vault(vault)
    scanned = scan.objects.get(object_id)
    if scanned is None:
        raise DomainError("OBJECT_NOT_FOUND", "object ID was not found")
    document = scanned.document
    citations: list[dict[str, object]] = []
    if isinstance(document.body, NoteBody):
        body: object = note_body_data(document.body)
        for section in document.body.sections:
            for block_ordinal, block in enumerate(section.blocks):
                if isinstance(block, FactBlock):
                    citations.extend(
                        {
                            "section_id": str(section.section_id),
                            "block_ordinal": block_ordinal,
                            "source_id": str(citation.source_id),
                            "locator": locator_data(citation.locator),
                        }
                        for citation in block.citations
                    )
    else:
        body = document.body
    outgoing = []
    if shard := scan.relation_shards.get(object_id):
        outgoing = [_relation_data(str(object_id), relation) for relation in shard.shard.relations]
    incoming = [
        _relation_data(str(from_id), relation)
        for from_id, shard in scan.relation_shards.items()
        for relation in shard.shard.relations
        if relation.to_id == object_id
    ]
    return {
        "object_id": str(object_id),
        "path": scanned.path,
        "checksum": scanned.checksum,
        "object": object_data(document.object),
        "body": body,
        "citations": citations,
        "relations": {
            "outgoing": sorted(outgoing, key=lambda item: repr(sorted(item.items()))),
            "incoming": sorted(incoming, key=lambda item: repr(sorted(item.items()))),
        },
    }


def hit_data(hit: SearchHit, *, public_safe: bool = False) -> dict[str, object]:
    result: dict[str, object] = {
        "classification": {"kind": hit.kind, "subtype": hit.subtype, "role": hit.role},
        "path": hit.path,
        "object_id": hit.object_id,
        "section_id": hit.section_id,
        "segment_id": hit.segment_id,
        "ordinal": hit.ordinal,
        "title": hit.title,
        "snippet": hit.text,
        "score": hit.score,
        "tags": list(hit.tags),
        "visibility": hit.visibility,
        "record_status": hit.record_status,
        "citations": list(hit.citations),
    }
    if public_safe:
        result["public_audit"] = {"eligible": True}
    return result


class QueryService:
    def __init__(self, backend: SearchBackend) -> None:
        self._backend = backend

    def search(
        self,
        vault: Vault,
        query: str,
        filters: SearchFilters,
        scope: ContextScope = ContextScope.TRUSTED_LOCAL,
        limit: int = 20,
    ) -> dict[str, object]:
        hits = self._backend.search(vault, query, filters, scope, limit)
        return {
            "query": query,
            "scope": scope.value,
            "filters": filters.as_dict(),
            "limit": limit,
            "index_versions": {
                "projection": PROJECTION_VERSION,
                "tokenizer": TOKENIZER_VERSION,
                "segment_algorithm": SEGMENT_ALGORITHM_VERSION,
            },
            "hits": [hit_data(hit, public_safe=scope is ContextScope.PUBLIC_SAFE) for hit in hits],
            "count": len(hits),
        }

    def context(
        self,
        vault: Vault,
        query: str,
        scope: ContextScope,
        limit: int = 20,
        max_chars: int = 12_000,
    ) -> dict[str, object]:
        _validate_limit(limit)
        if not 1 <= max_chars <= 100_000:
            raise DomainError("SEARCH_QUERY_INVALID", "max-chars must be between 1 and 100000")
        if scope is ContextScope.PUBLIC_SAFE:
            status_candidates = (
                self._backend.search(
                    vault,
                    query,
                    SearchFilters(record_status=status.value),
                    ContextScope.TRUSTED_LOCAL,
                    200,
                )
                for status in RecordStatus
            )
            unique_candidates = {
                hit.segment_id: hit for candidates in status_candidates for hit in candidates
            }
            candidates = tuple(
                sorted(
                    unique_candidates.values(),
                    key=lambda hit: (
                        hit.score,
                        hit.object_id,
                        hit.section_id or "",
                        hit.ordinal,
                    ),
                )
            )
        else:
            candidates = self._backend.search(
                vault, query, SearchFilters(), ContextScope.TRUSTED_LOCAL, 200
            )
        scan = scan_vault(vault)
        groups: dict[str, list[dict[str, object]]] = {
            "sources": [],
            "facts": [],
            "human_notes": [],
            "snippets": [],
        }
        exclusions: list[dict[str, object]] = []
        character_count = 0
        included = 0
        budget_excluded = 0
        limit_excluded = 0
        budget_closed = False
        for hit in candidates:
            if included >= limit:
                exclusions.append(self._exclusion(hit, "LIMIT_EXCEEDED"))
                limit_excluded += 1
                continue
            if scope is ContextScope.PUBLIC_SAFE:
                code = self._public_exclusion(scan, hit)
                if code:
                    exclusions.append(self._exclusion(hit, code))
                    continue
            if budget_closed or character_count + len(hit.text) > max_chars:
                exclusions.append(self._exclusion(hit, "CHARACTER_BUDGET_EXCEEDED"))
                budget_excluded += 1
                budget_closed = True
                continue
            group = {
                "source": "sources",
                "fact": "facts",
                "human": "human_notes",
                "snippet": "snippets",
            }.get(hit.role)
            if group is None:
                exclusions.append(self._exclusion(hit, "CONTEXT_ROLE_EXCLUDED"))
                continue
            groups[group].append(hit_data(hit, public_safe=scope is ContextScope.PUBLIC_SAFE))
            character_count += len(hit.text)
            included += 1
        return {
            "query": query,
            "scope": scope.value,
            "limit": limit,
            "max_chars": max_chars,
            "groups": groups,
            "exclusions": exclusions,
            "character_count": character_count,
            "truncated": bool(budget_excluded or limit_excluded),
            "excluded_count": len(exclusions),
            "notice": "This result is not a Phase 6B publish certification.",
        }

    @staticmethod
    def _exclusion(hit: SearchHit, code: str) -> dict[str, object]:
        return {"code": code, "object_id": hit.object_id, "segment_id": hit.segment_id}

    @staticmethod
    def _public_exclusion(scan: ScanResult, hit: SearchHit) -> str | None:
        scanned = next(
            (value for key, value in scan.objects.items() if str(key) == hit.object_id), None
        )
        if scanned is None:
            return "PUBLIC_OBJECT_UNRESOLVED"
        obj = scanned.document.object
        if obj.visibility is not Visibility.PUBLIC:
            return "PUBLIC_VISIBILITY_REQUIRED"
        if obj.record_status is not RecordStatus.ACTIVE:
            return "PUBLIC_ACTIVE_REQUIRED"
        if hit.role == "ai":
            return "PUBLIC_AI_EXCLUDED"
        if hit.role == "fact" and not hit.citations:
            return "PUBLIC_FACT_CITATION_REQUIRED"
        if isinstance(obj, Source):
            if obj.source_type.value == "web" and obj.snapshot_ref is None:
                return "PUBLIC_SNAPSHOT_REQUIRED"
            if obj.source_type.value == "oss" and obj.license == "NOASSERTION":
                return "PUBLIC_RIGHTS_UNRESOLVED"
        by_id = {str(key): value.document.object for key, value in scan.objects.items()}
        for citation in hit.citations:
            source = by_id.get(str(citation["source_id"]))
            if not isinstance(source, Source):
                return "PUBLIC_CITATION_UNRESOLVED"
            if (
                source.visibility is not Visibility.PUBLIC
                or source.record_status is not RecordStatus.ACTIVE
            ):
                return "PUBLIC_CITATION_SOURCE_UNSAFE"
            if source.source_type.value == "web" and source.snapshot_ref is None:
                return "PUBLIC_SNAPSHOT_REQUIRED"
            if source.source_type.value == "oss" and source.license == "NOASSERTION":
                return "PUBLIC_RIGHTS_UNRESOLVED"
            try:
                locator = parse_locator(citation["locator"])
            except (DomainError, KeyError, TypeError):
                return "PUBLIC_PROVENANCE_INCOHERENT"
            if locator_mismatched_fields(locator, source):
                return "PUBLIC_PROVENANCE_INCOHERENT"
        if isinstance(obj, Snippet):
            source = by_id.get(str(obj.source_id))
            if not obj.publication_approved:
                return "PUBLIC_SNIPPET_NOT_APPROVED"
            if obj.license == "NOASSERTION":
                return "PUBLIC_RIGHTS_UNRESOLVED"
            if not isinstance(source, Source) or source.visibility is not Visibility.PUBLIC:
                return "PUBLIC_SNIPPET_SOURCE_UNSAFE"
            if source.record_status is not RecordStatus.ACTIVE or source.source_type.value != "oss":
                return "PUBLIC_SNIPPET_SOURCE_UNSAFE"
            if source.license == "NOASSERTION":
                return "PUBLIC_RIGHTS_UNRESOLVED"
            if (obj.repository_host, obj.repository_path, obj.commit) != (
                source.repository_host,
                source.repository_path,
                source.commit,
            ):
                return "PUBLIC_PROVENANCE_INCOHERENT"
        return None
