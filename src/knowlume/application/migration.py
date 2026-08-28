from __future__ import annotations

import re
import shutil
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

import yaml  # type: ignore[import-untyped]

from knowlume.adapters.contract_v2 import (
    parse_locator,
    parse_object_document,
    render_relation_shard,
)
from knowlume.adapters.filesystem import (
    STANDARD_DIRS,
    checksum_file,
    load_vault,
    parse_vault_config,
)
from knowlume.adapters.transactions import RecoverableTransactions, WriteRequest
from knowlume.application.scanning import scan_vault
from knowlume.domain.models import Actor, Relation, RelationShard
from knowlume.domain.values import (
    ActorType,
    DomainError,
    ObjectId,
    RelationType,
    SectionId,
    enum_value,
)
from knowlume.ports.vault import Vault

FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", re.DOTALL)
V1_SECTION_RE = re.compile(
    r"<!--\s*section_id:\s*(sec_[a-z0-9][a-z0-9_-]{2,63})\s*-->"
    r"\s*\r?\n##\s+([^\r\n]+)(?:\r?\n|\Z)"
)
SECTION_ROLES = {
    "sec_original_facts": "fact",
    "sec_my_interpretation": "human",
    "sec_ai_inference": "ai",
    "sec_view_evolution": "evolution",
}
OBJECT_ROOTS = ("sources", "notes", "snippets", "ai")


@dataclass(frozen=True)
class MigrationFinding:
    kind: str
    code: str
    message: str
    status: str
    path: str | None = None
    object_id: str | None = None
    details: Mapping[str, object] | None = None

    def data(self) -> dict[str, object]:
        value: dict[str, object] = {
            "kind": self.kind,
            "code": self.code,
            "message": self.message,
            "status": self.status,
        }
        for key in ("path", "object_id", "details"):
            if (item := getattr(self, key)) is not None:
                value[key] = item
        return value


@dataclass(frozen=True)
class MigrationReport:
    mode: str
    apply_allowed: bool
    findings: tuple[MigrationFinding, ...]

    def data(self) -> dict[str, object]:
        return {
            "report_version": 1,
            "from_contract": 1,
            "to_contract": 2,
            "mode": self.mode,
            "apply_allowed": self.apply_allowed,
            "findings": [finding.data() for finding in self.findings],
        }


@dataclass(frozen=True)
class _ObjectInput:
    path: str
    data: dict[str, Any]
    body: str


@dataclass(frozen=True)
class _Plan:
    report: MigrationReport
    writes: tuple[WriteRequest, ...]


def _load_frontmatter(root: Path, path: Path) -> _ObjectInput:
    relative = path.relative_to(root).as_posix()
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise DomainError("MIGRATION_PARSE_FAILED", f"cannot read {relative}") from error
    match = FRONTMATTER_RE.match(text)
    if match is None:
        raise DomainError("MIGRATION_PARSE_FAILED", f"missing frontmatter in {relative}")
    try:
        loaded = yaml.safe_load(match.group(1))
    except yaml.YAMLError as error:
        raise DomainError("MIGRATION_PARSE_FAILED", f"invalid YAML in {relative}") from error
    if not isinstance(loaded, dict):
        raise DomainError("MIGRATION_PARSE_FAILED", f"frontmatter is not a mapping in {relative}")
    return _ObjectInput(
        relative, {str(key): value for key, value in loaded.items()}, text[match.end() :]
    )


def _yaml_document(data: Mapping[str, object], body: str) -> bytes:
    frontmatter = cast(
        str,
        yaml.safe_dump(
            dict(data), allow_unicode=True, default_flow_style=False, sort_keys=False, width=4096
        ),
    )
    return f"---\n{frontmatter}---\n\n{body.strip()}\n".encode()


def _base_v2(data: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(data)
    result["schema_version"] = 2
    return result


def _repository_parts(data: Mapping[str, Any]) -> tuple[str, str]:
    canonical = str(data.get("canonical_url", ""))
    parsed = urlparse(canonical)
    repo = str(data.get("repo", "")).removesuffix(".git").strip("/")
    if not parsed.hostname or not repo:
        raise DomainError("MIGRATION_IDENTITY_BLOCKED", "OSS repository identity is incomplete")
    return parsed.hostname, repo


def _convert_source(item: _ObjectInput) -> bytes:
    data = _base_v2(item.data)
    content_hash = data.pop("content_hash", None)
    repo = data.pop("repo", None)
    if data.get("source_type") == "oss":
        host, repository_path = _repository_parts({**data, "repo": repo})
        data["repository_host"] = host
        data["repository_path"] = repository_path
    if content_hash is not None:
        data["snapshot_ref"] = {
            "provider": "v1-migration",
            "identifier": str(data.get("canonical_url", data["id"])),
            "captured_at": data.get("captured_at"),
            "content_hash": content_hash,
        }
    return _yaml_document(data, item.body)


def _convert_snippet(item: _ObjectInput, objects: Mapping[str, _ObjectInput]) -> bytes:
    data = _base_v2(item.data)
    repo = str(data.pop("repo", ""))
    source = objects.get(str(data.get("source_id")))
    if source is None:
        raise DomainError("MIGRATION_REFERENCE_BLOCKED", "Snippet Source is missing")
    host, repository_path = _repository_parts({**source.data, "repo": repo})
    data["repository_host"] = host
    data["repository_path"] = repository_path
    data["publication_approved"] = False
    return _yaml_document(data, item.body)


def _convert_ai(item: _ObjectInput) -> bytes:
    data = _base_v2(item.data)
    data["input_refs"] = [{"object_id": source_id} for source_id in data.pop("source_ids", [])]
    return _yaml_document(data, item.body)


def _note_sections(item: _ObjectInput) -> tuple[str, list[tuple[str, str]]]:
    matches = list(V1_SECTION_RE.finditer(item.body))
    if not matches:
        raise DomainError("MIGRATION_SECTION_BLOCKED", "v1 Note has no fixed sections")
    seen: set[str] = set()
    contents: list[tuple[str, str]] = []
    result: list[str] = [item.body[: matches[0].start()].strip()]
    for index, match in enumerate(matches):
        section_id, heading = match.group(1), match.group(2).strip()
        if section_id in seen or section_id not in SECTION_ROLES:
            raise DomainError(
                "MIGRATION_SECTION_BLOCKED", "section identity is duplicate or unknown"
            )
        seen.add(section_id)
        content = item.body[
            match.end() : matches[index + 1].start() if index + 1 < len(matches) else len(item.body)
        ].strip()
        contents.append((section_id, content))
        result.append(
            f"<!-- knowlume:section id={section_id} role={SECTION_ROLES[section_id]} -->\n"
            f"## {heading}\n\n{content}".rstrip()
        )
    return "\n\n".join(part for part in result if part).rstrip(), contents


def _convert_note(item: _ObjectInput) -> tuple[bytes, list[tuple[str, str]]]:
    data = _base_v2(item.data)
    for key in ("source_ids", "related_notes", "supersedes", "superseded_by", "ai_assisted"):
        data.pop(key, None)
    data.pop("review_status", None)
    data["type_history"] = []
    body, contents = _note_sections(item)
    return _yaml_document(data, body), contents


def _finding(
    kind: str,
    code: str,
    message: str,
    *,
    path: str | None = None,
    object_id: str | None = None,
    details: Mapping[str, object] | None = None,
) -> MigrationFinding:
    status = "proposed" if kind == "change" else "unresolved"
    return MigrationFinding(kind, code, message, status, path, object_id, details)


class MigrationService:
    def __init__(
        self,
        *,
        config_reader: Callable[[], str],
        transactions: RecoverableTransactions | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._config_reader = config_reader
        self._transactions = transactions or RecoverableTransactions()
        self._clock = clock

    def _already_applied(self, root: Path, apply: bool) -> _Plan | None:
        marker = root / "knowlume.toml"
        if not marker.is_file():
            return None
        try:
            vault = load_vault(root)
        except DomainError as error:
            raise DomainError("MIGRATION_VAULT_INVALID", str(error)) from error
        if vault.config.object_contract_version != 2:
            return None
        result = scan_vault(vault)
        if not result.healthy:
            codes = ", ".join(sorted({finding.code for finding in result.findings}))
            raise DomainError(
                "MIGRATION_VAULT_INVALID", f"existing Contract v2 Vault fails scan: {codes}"
            )
        finding = MigrationFinding(
            "change",
            "MIGRATION_ALREADY_APPLIED",
            "Vault already uses Contract v2; no writes are required.",
            "resolved",
        )
        return _Plan(MigrationReport("apply" if apply else "dry-run", True, (finding,)), ())

    def _read_inputs(self, root: Path) -> tuple[list[_ObjectInput], list[MigrationFinding]]:
        inputs: list[_ObjectInput] = []
        findings: list[MigrationFinding] = []
        for folder in OBJECT_ROOTS:
            candidate = root / folder
            if not candidate.exists():
                continue
            for path in sorted(candidate.rglob("*.md")):
                try:
                    item = _load_frontmatter(root, path)
                except DomainError as error:
                    findings.append(
                        _finding(
                            "blocker",
                            error.code,
                            str(error),
                            path=path.relative_to(root).as_posix(),
                        )
                    )
                    continue
                if item.data.get("schema_version") != 1:
                    findings.append(
                        _finding(
                            "blocker",
                            "MIGRATION_VERSION_BLOCKED",
                            "Migration input is not Contract v1.",
                            path=item.path,
                        )
                    )
                else:
                    inputs.append(item)
        if not inputs:
            findings.append(
                _finding("blocker", "MIGRATION_INPUT_MISSING", "No Contract v1 objects were found.")
            )
        return inputs, findings

    def _global_relations(
        self, root: Path, findings: list[MigrationFinding]
    ) -> list[dict[str, Any]]:
        path = root / "relations.yaml"
        if not path.exists():
            return []
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError):
            findings.append(
                _finding(
                    "blocker",
                    "MIGRATION_RELATIONS_BLOCKED",
                    "Global relations are unreadable.",
                    path="relations.yaml",
                )
            )
            return []
        if (
            not isinstance(value, dict)
            or value.get("schema_version") != 1
            or not isinstance(value.get("relations"), list)
        ):
            findings.append(
                _finding(
                    "blocker",
                    "MIGRATION_RELATIONS_BLOCKED",
                    "Global relation collection is invalid.",
                    path="relations.yaml",
                )
            )
            return []
        return [
            cast(dict[str, Any], relation)
            for relation in value["relations"]
            if isinstance(relation, dict)
        ]

    def _plan(self, root: Path, apply: bool) -> _Plan:
        inputs, findings = self._read_inputs(root)
        by_id: dict[str, _ObjectInput] = {}
        duplicates: set[str] = set()
        for item in inputs:
            value = item.data.get("id")
            if not isinstance(value, str):
                findings.append(
                    _finding(
                        "blocker",
                        "MIGRATION_IDENTITY_BLOCKED",
                        "Object ID is missing.",
                        path=item.path,
                    )
                )
                continue
            if value in by_id:
                duplicates.add(value)
            by_id[value] = item
        for object_id in sorted(duplicates):
            findings.append(
                _finding(
                    "blocker",
                    "MIGRATION_IDENTITY_DUPLICATE",
                    "Object ID is duplicated.",
                    object_id=object_id,
                )
            )

        writes: list[WriteRequest] = []
        relations: dict[str, list[Relation]] = {}
        now = self._clock()

        def add_relation(
            from_value: str,
            to_value: str,
            relation_type: RelationType,
            *,
            section: str | None = None,
            locator: object = None,
            actor_id: str = "migration",
        ) -> None:
            if from_value not in by_id or to_value not in by_id:
                findings.append(
                    _finding(
                        "blocker",
                        "MIGRATION_REFERENCE_BLOCKED",
                        "Relation references a missing object.",
                        object_id=from_value,
                        details={"to_id": to_value},
                    )
                )
                return
            from_id, to_id = ObjectId(from_value), ObjectId(to_value)
            if relation_type is RelationType.RELATED_TO and str(from_id) > str(to_id):
                from_id, to_id = to_id, from_id
            try:
                normalized_locator = None
                if locator is not None:
                    if not isinstance(locator, Mapping):
                        raise DomainError("LOCATOR_INVALID", "v1 locator is not a mapping")
                    normalized_locator = dict(locator)
                    normalized_locator["locator_version"] = 2
                parsed_locator = (
                    parse_locator(normalized_locator) if normalized_locator is not None else None
                )
                relation = Relation(
                    to_id,
                    relation_type,
                    now,
                    Actor(ActorType.HUMAN, actor_id),
                    SectionId(section) if section else None,
                    parsed_locator,
                )
            except DomainError as error:
                findings.append(_finding("blocker", error.code, str(error), object_id=from_value))
                return
            bucket = relations.setdefault(str(from_id), [])
            if any(existing.canonical_key == relation.canonical_key for existing in bucket):
                findings.append(
                    _finding(
                        "change",
                        "MIGRATION_RELATION_DEDUPLICATED",
                        "Duplicate v1 relation declarations collapse to one canonical entry.",
                        object_id=str(from_id),
                    )
                )
                return
            bucket.append(relation)

        for object_id, item in sorted(by_id.items()):
            kind = item.data.get("kind")
            try:
                if kind == "source":
                    content = _convert_source(item)
                elif kind == "snippet":
                    content = _convert_snippet(item, by_id)
                elif kind == "ai_artifact":
                    review = item.data.get("review_status")
                    if review != "unreviewed" and not (
                        item.data.get("reviewed_by") and item.data.get("reviewed_at")
                    ):
                        findings.append(
                            _finding(
                                "blocker",
                                "MIGRATION_AI_PROVENANCE_BLOCKED",
                                "Reviewed AI Artifact lacks reviewer provenance.",
                                path=item.path,
                                object_id=object_id,
                            )
                        )
                    content = _convert_ai(item)
                elif kind == "note":
                    note_type = item.data.get("note_type")
                    if note_type == "evergreen":
                        findings.append(
                            _finding(
                                "decision",
                                "MIGRATION_EVERGREEN_CLASSIFICATION_REQUIRED",
                                "Evergreen Note must be classified as Concept or Synthesis.",
                                path=item.path,
                                object_id=object_id,
                            )
                        )
                        continue
                    content, sections = _convert_note(item)
                    section_ids = {section_id for section_id, _ in sections}
                    for section_id, section_content in sections:
                        if section_id == "sec_original_facts" and section_content:
                            findings.append(
                                _finding(
                                    "decision",
                                    "MIGRATION_FACT_LOCATOR_REQUIRED",
                                    "V1 Fact content requires per-block Source and "
                                    "locator binding.",
                                    path=item.path,
                                    object_id=object_id,
                                    details={"section_id": section_id, "inference_written": False},
                                )
                            )
                        if section_id == "sec_ai_inference" and section_content:
                            findings.append(
                                _finding(
                                    "blocker",
                                    "MIGRATION_AI_SECTION_BLOCKED",
                                    "AI section content lacks a promoted Artifact reference.",
                                    path=item.path,
                                    object_id=object_id,
                                )
                            )
                    if item.data.get("ai_assisted"):
                        findings.append(
                            _finding(
                                "blocker",
                                "MIGRATION_AI_ASSISTED_BLOCKED",
                                "ai_assisted is true without resolvable reviewed provenance.",
                                path=item.path,
                                object_id=object_id,
                            )
                        )
                    source_ids = item.data.get("source_ids", [])
                    if note_type == "literature":
                        if isinstance(source_ids, list) and len(source_ids) == 1:
                            add_relation(object_id, str(source_ids[0]), RelationType.SUMMARIZES)
                        else:
                            findings.append(
                                _finding(
                                    "decision",
                                    "MIGRATION_LITERATURE_SOURCE_REQUIRED",
                                    "Literature Note must resolve to exactly one Source.",
                                    path=item.path,
                                    object_id=object_id,
                                )
                            )
                    elif source_ids:
                        findings.append(
                            _finding(
                                "decision",
                                "MIGRATION_INFERENCE_PROHIBITED",
                                "Non-Literature source_ids cannot be guessed as cites or "
                                "synthesizes.",
                                path=item.path,
                                object_id=object_id,
                                details={
                                    "source_ids": list(source_ids),
                                    "inference_written": False,
                                },
                            )
                        )
                    for target in item.data.get("related_notes", []):
                        add_relation(object_id, str(target), RelationType.RELATED_TO)
                    for target in item.data.get("supersedes", []):
                        add_relation(object_id, str(target), RelationType.SUPERSEDES)
                    if target := item.data.get("superseded_by"):
                        add_relation(str(target), object_id, RelationType.SUPERSEDES)
                    if not section_ids:
                        raise DomainError(
                            "MIGRATION_SECTION_BLOCKED", "Note has no stable sections"
                        )
                else:
                    raise DomainError("MIGRATION_KIND_BLOCKED", "unknown v1 object kind")
                parse_object_document(content.decode())
                writes.append(WriteRequest(item.path, content, checksum_file(root / item.path)))
                findings.append(
                    _finding(
                        "change",
                        "MIGRATION_OBJECT_CONVERTED",
                        "Contract v1 object will be converted to v2.",
                        path=item.path,
                        object_id=object_id,
                    )
                )
            except (DomainError, KeyError, TypeError, ValueError) as error:
                code = (
                    error.code if isinstance(error, DomainError) else "MIGRATION_CONVERSION_BLOCKED"
                )
                findings.append(
                    _finding("blocker", code, str(error), path=item.path, object_id=object_id)
                )

        for value in self._global_relations(root, findings):
            try:
                add_relation(
                    str(value["from_id"]),
                    str(value["to_id"]),
                    enum_value(RelationType, value["relation_type"], field="relation type"),
                    section=str(value["to_section_id"]) if value.get("to_section_id") else None,
                    locator=value.get("locator"),
                    actor_id=str(value.get("created_by", "migration")),
                )
            except (DomainError, KeyError) as error:
                code = (
                    error.code if isinstance(error, DomainError) else "MIGRATION_RELATIONS_BLOCKED"
                )
                findings.append(_finding("blocker", code, str(error), path="relations.yaml"))

        for from_id, values in sorted(relations.items()):
            shard = RelationShard(
                ObjectId(from_id), tuple(sorted(values, key=lambda value: value.canonical_key))
            )
            path = f"relations/{from_id}.yaml"
            writes.append(
                WriteRequest(
                    path, render_relation_shard(shard).encode(), checksum_file(root / path)
                )
            )
            findings.append(
                _finding(
                    "change",
                    "MIGRATION_RELATION_SHARD_CREATED",
                    "Relations will be written to the owning shard.",
                    path=path,
                    object_id=from_id,
                )
            )

        config_text = self._config_reader()
        parse_vault_config(config_text)
        writes.append(WriteRequest("knowlume.toml", config_text.encode(), None))
        findings.append(
            _finding(
                "change",
                "MIGRATION_VAULT_CONFIG_CREATED",
                "Portable Contract v2 Vault configuration will be created.",
                path="knowlume.toml",
            )
        )
        blockers = any(finding.kind in {"decision", "blocker"} for finding in findings)
        mode = "apply" if apply else "dry-run"
        if apply and not blockers:
            findings = [replace(finding, status="resolved") for finding in findings]
        report = MigrationReport(
            mode,
            not blockers,
            tuple(
                sorted(
                    findings,
                    key=lambda item: (item.kind, item.code, item.path or "", item.object_id or ""),
                )
            ),
        )
        return _Plan(report, tuple(sorted(writes, key=lambda item: item.path)))

    def _prepare_topology(self, root: Path) -> Vault:
        config = parse_vault_config(self._config_reader())
        for relative in STANDARD_DIRS:
            path = root.joinpath(*relative.split("/"))
            path.mkdir(parents=True, exist_ok=True)
            if not path.resolve(strict=True).is_relative_to(root):
                raise DomainError("VAULT_PATH_UNSAFE", "migration topology escapes the Vault")
        return Vault(root, config)

    def _verify_plan(
        self, root: Path, writes: tuple[WriteRequest, ...]
    ) -> tuple[MigrationFinding, ...]:
        with tempfile.TemporaryDirectory(prefix="knowlume-migration-") as temporary:
            candidate = Path(temporary) / "vault"
            shutil.copytree(root, candidate)
            for relative in STANDARD_DIRS:
                candidate.joinpath(*relative.split("/")).mkdir(parents=True, exist_ok=True)
            for write in writes:
                path = candidate.joinpath(*write.path.split("/"))
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(write.content)
            result = scan_vault(load_vault(candidate))
            return tuple(
                _finding(
                    "blocker",
                    f"MIGRATION_RESULT_{finding.code}",
                    finding.message,
                    path=finding.path or None,
                    object_id=finding.object_id or None,
                )
                for finding in result.findings
                if finding.severity == "error"
            )

    def _with_prospective_validation(self, root: Path, plan: _Plan) -> _Plan:
        if not plan.report.apply_allowed:
            return plan
        invalid = self._verify_plan(root, plan.writes)
        if not invalid:
            return plan
        findings = (
            tuple(
                replace(finding, status="proposed") if finding.kind == "change" else finding
                for finding in plan.report.findings
            )
            + invalid
        )
        report = replace(
            plan.report,
            apply_allowed=False,
            findings=tuple(
                sorted(
                    findings,
                    key=lambda item: (
                        item.kind,
                        item.code,
                        item.path or "",
                        item.object_id or "",
                    ),
                )
            ),
        )
        return replace(plan, report=report)

    def run(self, root_value: Path, *, apply: bool = False) -> MigrationReport:
        try:
            root = root_value.resolve(strict=True)
        except OSError as error:
            raise DomainError("MIGRATION_VAULT_INVALID", "migration root does not exist") from error
        if not root.is_dir():
            raise DomainError("MIGRATION_VAULT_INVALID", "migration root is not a directory")
        marker = root / "knowlume.toml"
        if marker.is_file():
            try:
                recovery_vault = load_vault(root)
            except DomainError as error:
                raise DomainError("MIGRATION_VAULT_INVALID", str(error)) from error
            transaction_root = recovery_vault.path("state") / "transactions"
            if any(transaction_root.iterdir()):
                self._transactions.recover(recovery_vault)
        if already := self._already_applied(root, apply):
            return already.report
        plan = self._with_prospective_validation(root, self._plan(root, apply))
        if not apply or not plan.report.apply_allowed:
            return plan.report
        vault = self._prepare_topology(root)
        transaction_root = vault.path("state") / "transactions"
        if any(transaction_root.iterdir()):
            self._transactions.recover(vault)
            plan = self._with_prospective_validation(root, self._plan(root, apply))
            if not plan.report.apply_allowed:
                return plan.report
        self._transactions.commit(vault, "migration", plan.writes)
        if not scan_vault(load_vault(root)).healthy:
            raise DomainError("MIGRATION_RESULT_INVALID", "applied v2 Vault fails scan")
        return plan.report
