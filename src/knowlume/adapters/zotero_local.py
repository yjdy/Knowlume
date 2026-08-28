from __future__ import annotations

import hashlib
import importlib
import ipaddress
import json
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import urlparse

from platformdirs import user_cache_dir

from knowlume.domain.paper import PaperIdentity, normalize_arxiv, normalize_doi
from knowlume.domain.values import DomainError
from knowlume.ports.zotero import (
    AttachmentSelection,
    PaperMetadata,
    PrimaryAttachment,
    ZoteroReference,
)

DEFAULT_ENDPOINT = "http://127.0.0.1:23119/api"
_KEY_RE = re.compile(r"^[A-Z0-9]{8}$")


class _HttpResponse(Protocol):
    status_code: int
    content: bytes


class _HttpxModule(Protocol):
    RequestError: type[Exception]

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
        follow_redirects: bool,
    ) -> _HttpResponse: ...


def _httpx() -> _HttpxModule:
    try:
        module = importlib.import_module("httpx")
    except ModuleNotFoundError as error:
        raise DomainError(
            "ZOTERO_CAPABILITY_UNAVAILABLE",
            "Zotero support requires the 'knowlume[zotero]' optional dependency",
        ) from error
    return cast(_HttpxModule, module)


def _loopback_endpoint(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password:
        raise DomainError("ZOTERO_ENDPOINT_UNSAFE", "Zotero Local API endpoint is invalid")
    host = parsed.hostname.lower()
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host == "localhost"
    if not loopback:
        raise DomainError(
            "ZOTERO_ENDPOINT_UNSAFE", "Zotero Local API endpoint must use a loopback address"
        )
    if parsed.query or parsed.fragment:
        raise DomainError("ZOTERO_ENDPOINT_UNSAFE", "Zotero Local API endpoint is invalid")
    return value.rstrip("/")


def _library_path(reference: ZoteroReference) -> str:
    if reference.library_type == "user" and reference.library_id == "0":
        prefix = "users/0"
    elif reference.library_type == "group" and reference.library_id.isdigit():
        prefix = f"groups/{reference.library_id}"
    else:
        raise DomainError("ZOTERO_REFERENCE_INVALID", "unsupported Zotero library reference")
    if not _KEY_RE.fullmatch(reference.item_key):
        raise DomainError("ZOTERO_REFERENCE_INVALID", "invalid Zotero item key")
    return prefix


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DomainError("ZOTERO_RESPONSE_INVALID", f"Zotero {field} is not an object")
    return dict(value)


def _string(value: object, field: str, *, required: bool = True) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or (required and not value.strip()):
        raise DomainError("ZOTERO_RESPONSE_INVALID", f"Zotero {field} is invalid")
    return value.strip()


def _version(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DomainError("ZOTERO_RESPONSE_INVALID", f"Zotero {field} is invalid")
    return value


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return f"sha256:{digest.hexdigest()}", size


class ZoteroLocalApi:
    def __init__(
        self,
        *,
        endpoint: str = DEFAULT_ENDPOINT,
        cache_root: Path | None = None,
        timeout: float = 5.0,
    ) -> None:
        self._endpoint = _loopback_endpoint(endpoint)
        self._cache_root = cache_root or Path(user_cache_dir("knowlume")) / "zotero"
        self._timeout = timeout

    def _request(self, path: str, *, binary: bool = False) -> bytes | object:
        httpx = _httpx()
        try:
            response = httpx.get(
                f"{self._endpoint}/{path.lstrip('/')}",
                headers={"Zotero-API-Version": "3", "Accept": "application/json"},
                timeout=self._timeout,
                follow_redirects=False,
            )
        except httpx.RequestError as error:
            raise DomainError(
                "ZOTERO_API_UNAVAILABLE", "Zotero Local API is unavailable"
            ) from error
        if response.status_code in {401, 403}:
            raise DomainError("ZOTERO_PERMISSION_DENIED", "Zotero Local API refused read access")
        if response.status_code == 404:
            raise DomainError("ZOTERO_ITEM_UNAVAILABLE", "Zotero item or attachment is unavailable")
        if not 200 <= response.status_code < 300:
            raise DomainError(
                "ZOTERO_API_UNAVAILABLE",
                f"Zotero Local API returned HTTP {response.status_code}",
            )
        body = response.content
        if binary:
            return body
        try:
            return cast(object, json.loads(body))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DomainError(
                "ZOTERO_RESPONSE_INVALID", "Zotero returned malformed JSON"
            ) from error

    def metadata(self, reference: ZoteroReference) -> PaperMetadata:
        prefix = _library_path(reference)
        document = _mapping(self._request(f"{prefix}/items/{reference.item_key}"), "item")
        key = _string(document.get("key"), "item key")
        if key != reference.item_key:
            raise DomainError("ZOTERO_RESPONSE_INVALID", "Zotero item key does not match request")
        version = _version(document.get("version"), "item version")
        data = _mapping(document.get("data"), "item data")
        title = cast(str, _string(data.get("title"), "title"))
        doi = None
        if raw_doi := _string(data.get("DOI"), "DOI", required=False):
            try:
                doi = normalize_doi(raw_doi)
            except DomainError as error:
                raise DomainError("ZOTERO_RESPONSE_INVALID", "Zotero DOI is invalid") from error
        arxiv = None
        extra = _string(data.get("extra"), "extra", required=False) or ""
        match = re.search(r"(?im)^\s*arxiv\s*:\s*(\S+)\s*$", extra)
        url = _string(data.get("url"), "URL", required=False)
        arxiv_value = match.group(1) if match else (url if url and "arxiv.org/" in url else None)
        if arxiv_value:
            try:
                arxiv = normalize_arxiv(arxiv_value)
            except DomainError as error:
                raise DomainError(
                    "ZOTERO_RESPONSE_INVALID", "Zotero arXiv ID is invalid"
                ) from error
        identity = PaperIdentity(doi, arxiv) if doi or arxiv else None
        creators = data.get("creators", [])
        if not isinstance(creators, list):
            raise DomainError("ZOTERO_RESPONSE_INVALID", "Zotero creators are invalid")
        authors: list[str] = []
        for creator_value in creators:
            creator = _mapping(creator_value, "creator")
            if creator.get("creatorType") not in {"author", None}:
                continue
            name = creator.get("name")
            if not isinstance(name, str) or not name.strip():
                parts = [creator.get("firstName"), creator.get("lastName")]
                name = " ".join(
                    part.strip() for part in parts if isinstance(part, str) and part.strip()
                )
            if name:
                authors.append(name)
        date_value = _string(data.get("date"), "date", required=False) or ""
        year_match = re.search(r"\b(1\d{3}|2\d{3}|3\d{3})\b", date_value)
        return PaperMetadata(
            title=title,
            authors=tuple(authors),
            year=int(year_match.group(1)) if year_match else None,
            identity=identity,
            canonical_url=url,
            zotero=reference,
            item_version=version,
        )

    def primary_attachment(self, reference: ZoteroReference) -> AttachmentSelection:
        prefix = _library_path(reference)
        response = self._request(f"{prefix}/items/{reference.item_key}/children")
        if not isinstance(response, list):
            raise DomainError("ZOTERO_RESPONSE_INVALID", "Zotero children response is invalid")
        candidates: list[tuple[str, int, str, str]] = []
        for raw in response:
            item = _mapping(raw, "child item")
            data = _mapping(item.get("data"), "child item data")
            filename = _string(data.get("filename"), "attachment filename", required=False)
            media_type = _string(data.get("contentType"), "attachment media type", required=False)
            if data.get("itemType") != "attachment" or not filename:
                continue
            if media_type != "application/pdf" and not filename.lower().endswith(".pdf"):
                continue
            key = cast(str, _string(item.get("key"), "attachment key"))
            if not _KEY_RE.fullmatch(key):
                raise DomainError("ZOTERO_RESPONSE_INVALID", "Zotero attachment key is invalid")
            candidates.append(
                (
                    key,
                    _version(item.get("version"), "attachment version"),
                    filename,
                    "application/pdf",
                )
            )
        if not candidates:
            return AttachmentSelection(None, "PAPER_ATTACHMENT_UNAVAILABLE")
        if len(candidates) > 1:
            return AttachmentSelection(None, "PAPER_ATTACHMENT_AMBIGUOUS")
        key, version, filename, media_type = candidates[0]
        safe_name = Path(filename).name
        if safe_name != filename or safe_name in {"", ".", ".."}:
            raise DomainError("ZOTERO_RESPONSE_INVALID", "Zotero attachment filename is unsafe")
        cache_name = f"{reference.library_type}-{reference.library_id}-{key}-v{version}-{safe_name}"
        self._cache_root.mkdir(parents=True, exist_ok=True)
        target = self._cache_root / cache_name
        if not target.is_file():
            body = cast(bytes, self._request(f"{prefix}/items/{key}/file", binary=True))
            descriptor, temporary_name = tempfile.mkstemp(prefix=".zotero-", dir=self._cache_root)
            temporary = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(body)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
            finally:
                if temporary.exists():
                    temporary.unlink()
        digest, size = _sha256_file(target)
        return AttachmentSelection(
            PrimaryAttachment(key, version, safe_name, media_type, size, digest, target)
        )

    def attachment(self, reference: ZoteroReference, attachment_key: str) -> PrimaryAttachment:
        prefix = _library_path(reference)
        response = self._request(f"{prefix}/items/{reference.item_key}/children")
        if not isinstance(response, list):
            raise DomainError("ZOTERO_RESPONSE_INVALID", "Zotero children response is invalid")
        for raw in response:
            item = _mapping(raw, "child item")
            if item.get("key") != attachment_key:
                continue
            data = _mapping(item.get("data"), "child item data")
            filename = cast(
                str, _string(data.get("filename"), "attachment filename", required=True)
            )
            if Path(filename).name != filename or filename in {"", ".", ".."}:
                raise DomainError("ZOTERO_RESPONSE_INVALID", "Zotero attachment filename is unsafe")
            if data.get("itemType") != "attachment":
                break
            version = _version(item.get("version"), "attachment version")
            media_type = _string(data.get("contentType"), "attachment media type", required=False)
            if media_type != "application/pdf" and not filename.lower().endswith(".pdf"):
                break
            # Reuse the selection recovery path while limiting it to this recorded child.
            cache_name = (
                f"{reference.library_type}-{reference.library_id}-{attachment_key}-"
                f"v{version}-{filename}"
            )
            self._cache_root.mkdir(parents=True, exist_ok=True)
            target = self._cache_root / cache_name
            if not target.is_file():
                body = cast(
                    bytes, self._request(f"{prefix}/items/{attachment_key}/file", binary=True)
                )
                descriptor, temporary_name = tempfile.mkstemp(
                    prefix=".zotero-", dir=self._cache_root
                )
                temporary = Path(temporary_name)
                try:
                    with os.fdopen(descriptor, "wb") as stream:
                        stream.write(body)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temporary, target)
                finally:
                    if temporary.exists():
                        temporary.unlink()
            digest, size = _sha256_file(target)
            return PrimaryAttachment(
                attachment_key, version, filename, "application/pdf", size, digest, target
            )
        raise DomainError("ZOTERO_ITEM_UNAVAILABLE", "recorded Zotero attachment is unavailable")
