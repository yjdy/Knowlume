from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from urllib.parse import unquote, urlparse

from knowlume.domain.values import DomainError

_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
_ARXIV_RE = re.compile(
    r"^(?P<base>(?:[a-z-]+(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5}))"
    r"(?:v(?P<version>[1-9]\d*))?$",
    re.IGNORECASE,
)


@dataclass(frozen=True, order=True)
class Doi:
    value: str

    def __post_init__(self) -> None:
        if not _DOI_RE.fullmatch(self.value):
            raise DomainError("PAPER_DOI_INVALID", f"invalid DOI: {self.value!r}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class ArxivIdentity:
    base_id: str
    version: int | None = None

    def __post_init__(self) -> None:
        suffix = f"v{self.version}" if self.version is not None else ""
        match = _ARXIV_RE.fullmatch(f"{self.base_id}{suffix}")
        if match is None or match.group("base").lower() != self.base_id.lower():
            raise DomainError("PAPER_ARXIV_INVALID", f"invalid arXiv ID: {self.base_id!r}")

    @property
    def versioned_id(self) -> str:
        return f"{self.base_id}v{self.version}" if self.version is not None else self.base_id


@dataclass(frozen=True)
class PaperIdentity:
    doi: Doi | None = None
    arxiv: ArxivIdentity | None = None

    def __post_init__(self) -> None:
        if self.doi is None and self.arxiv is None:
            raise DomainError(
                "PAPER_CANONICAL_IDENTITY_MISSING",
                "Paper metadata has neither DOI nor arXiv identity",
            )

    @property
    def canonical(self) -> str:
        if self.doi is not None:
            return f"doi:{self.doi}"
        assert self.arxiv is not None
        return f"arxiv:{self.arxiv.base_id}"

    @property
    def aliases(self) -> tuple[str, ...]:
        values: list[str] = []
        if self.doi is not None:
            values.append(f"doi:{self.doi}")
        if self.arxiv is not None:
            values.append(f"arxiv:{self.arxiv.base_id}")
        return tuple(values)


def normalize_doi(value: str) -> Doi:
    normalized = unquote(value.strip())
    normalized = re.sub(r"^doi\s*:\s*", "", normalized, flags=re.IGNORECASE)
    parsed = urlparse(normalized)
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc.lower() in {
        "doi.org",
        "dx.doi.org",
        "www.doi.org",
    }:
        normalized = parsed.path.lstrip("/")
    normalized = normalized.strip().rstrip(".,;").lower()
    return Doi(normalized)


def normalize_arxiv(value: str) -> ArxivIdentity:
    normalized = unquote(value.strip())
    normalized = re.sub(r"^arxiv\s*:\s*", "", normalized, flags=re.IGNORECASE)
    parsed = urlparse(normalized)
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc.lower() in {
        "arxiv.org",
        "www.arxiv.org",
    }:
        parts = [part for part in parsed.path.split("/") if part]
        if parts and parts[0].lower() in {"abs", "pdf"}:
            parts = parts[1:]
        normalized = "/".join(parts)
    if normalized.lower().endswith(".pdf"):
        normalized = normalized[:-4]
    match = _ARXIV_RE.fullmatch(normalized)
    if match is None:
        raise DomainError("PAPER_ARXIV_INVALID", f"invalid arXiv ID: {value!r}")
    base = match.group("base")
    if "/" in base:
        archive, number = base.split("/", 1)
        base = f"{archive.lower()}/{number}"
    return ArxivIdentity(base, int(match.group("version")) if match.group("version") else None)


def managed_fields_hash(fields: dict[str, Any]) -> str:
    normalized = {
        key: unicodedata.normalize("NFC", value) if isinstance(value, str) else value
        for key, value in fields.items()
        if value is not None and value != () and value != []
    }
    payload = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{sha256(payload).hexdigest()}"
