from __future__ import annotations

import re
import string
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import SplitResult, unquote, urlsplit, urlunsplit

from knowlume.domain.isbn import normalize_isbn
from knowlume.domain.paper import ArxivIdentity, Doi, normalize_arxiv, normalize_doi
from knowlume.domain.repository import BUILTIN_REPOSITORY_HOSTS, normalize_repository_host
from knowlume.domain.values import DomainError

_UNRESERVED = frozenset(string.ascii_letters + string.digits + "-._~")
_SCP_RE = re.compile(r"^[^/\s@]+@[^/\s:]+:")


class CaptureType(StrEnum):
    PAPER = "paper"
    WEB = "web"
    BOOK = "book"
    REPO = "repo"


@dataclass(frozen=True)
class RepositoryInput:
    canonical_url: str
    host: str
    project_path: str


@dataclass(frozen=True)
class CaptureCandidate:
    raw_input: str
    requested_type: CaptureType | None
    kind: str
    doi: Doi | None = None
    arxiv: ArxivIdentity | None = None
    isbn: str | None = None
    canonical_url: str | None = None
    repository: RepositoryInput | None = None


def _decode_unreserved(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        character = chr(int(match.group(1), 16))
        return character if character in _UNRESERVED else match.group(0).upper()

    return re.sub(r"%([0-9A-Fa-f]{2})", replace, value)


def _remove_dot_segments(path: str) -> str:
    absolute = path.startswith("/")
    trailing = path.endswith("/")
    output: list[str] = []
    for segment in path.split("/"):
        if segment in {"", "."}:
            continue
        if segment == "..":
            if output:
                output.pop()
            continue
        output.append(segment)
    normalized = "/".join(output)
    if absolute:
        normalized = "/" + normalized
    if trailing and normalized != "/":
        normalized += "/"
    return normalized or "/"


def _normalized_http_parts(value: str, *, keep_fragment: bool = False) -> SplitResult:
    if not isinstance(value, str) or not value or value != value.strip() or _SCP_RE.match(value):
        raise DomainError("ADD_INPUT_INVALID", "input must be a credential-free HTTP(S) URL")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise DomainError("ADD_INPUT_INVALID", "input URL is invalid") from error
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise DomainError("ADD_INPUT_INVALID", "input must be a credential-free HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise DomainError("ADD_INPUT_INVALID", "credential-bearing URLs are not accepted")
    try:
        host = parsed.hostname.encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise DomainError("ADD_INPUT_INVALID", "URL host is not valid IDNA") from error
    # URL host matching follows the same DNS normalization rule as configured
    # repository hosts.  A single terminal dot denotes the DNS root and is not
    # part of the canonical host identity.
    if host.endswith("."):
        host = host[:-1]
    if not host or host.endswith("."):
        raise DomainError("ADD_INPUT_INVALID", "input URL is invalid")
    if ":" in host:
        netloc_host = f"[{host}]"
    else:
        netloc_host = host
    default_port = (parsed.scheme.lower(), port) in {("http", 80), ("https", 443)}
    netloc = netloc_host if port is None or default_port else f"{netloc_host}:{port}"
    return SplitResult(
        parsed.scheme.lower(),
        netloc,
        parsed.path,
        parsed.query,
        parsed.fragment if keep_fragment else "",
    )


def canonicalize_web_url(value: str) -> str:
    parsed = _normalized_http_parts(value)
    path = _remove_dot_segments(_decode_unreserved(parsed.path or "/"))
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, ""))


def normalize_repository_url(
    value: str, *, configured: bool, explicit: bool = False
) -> RepositoryInput:
    parsed = _normalized_http_parts(value, keep_fragment=True)
    if parsed.query or parsed.fragment:
        raise DomainError("ADD_INPUT_INVALID", "repository URL cannot contain query or fragment")
    host = parsed.hostname
    assert host is not None
    try:
        normalized_host = normalize_repository_host(host)
    except DomainError as error:
        raise DomainError("ADD_INPUT_INVALID", "repository host is invalid") from error
    raw_path = unquote(parsed.path)
    if "\\" in raw_path or any(character.isspace() for character in raw_path):
        raise DomainError("ADD_INPUT_INVALID", "repository project path is invalid")
    path = raw_path[1:] if raw_path.startswith("/") else raw_path
    if path.endswith("/"):
        path = path[:-1]
    if path.lower().endswith(".git"):
        path = path[:-4]
    segments = path.split("/") if path else []
    if len(segments) < 2 or any(segment in {"", ".", ".."} for segment in segments):
        raise DomainError("ADD_INPUT_INVALID", "repository URL is not a project root")
    if normalized_host == "github.com" and len(segments) != 2:
        raise DomainError("ADD_INPUT_INVALID", "GitHub URL is not a repository root")
    if normalized_host == "gitlab.com" or configured:
        if "-" in segments and segments[segments.index("-") : segments.index("-") + 2] == ["-", ""]:
            raise DomainError("ADD_INPUT_INVALID", "GitLab provider route is not a project root")
        if "-" in segments:
            raise DomainError("ADD_INPUT_INVALID", "GitLab provider route is not a project root")
    if not configured and not explicit and normalized_host not in BUILTIN_REPOSITORY_HOSTS:
        raise DomainError("ADD_INPUT_INVALID", "repository host is not configured")
    canonical_url = urlunsplit((parsed.scheme, parsed.netloc, f"/{'/'.join(segments)}", "", ""))
    return RepositoryInput(canonical_url, normalized_host, "/".join(segments))


def _capture_type(value: CaptureType | str | None) -> CaptureType | None:
    if value is None or isinstance(value, CaptureType):
        return value
    try:
        return CaptureType(value)
    except ValueError as error:
        raise DomainError(
            "ADD_INPUT_INVALID", "--type must be paper, web, book, or repo"
        ) from error


def recognize_capture_input(
    value: str,
    requested_type: CaptureType | str | None,
    repository_hosts: tuple[str, ...] = BUILTIN_REPOSITORY_HOSTS,
) -> CaptureCandidate:
    selected = _capture_type(requested_type)
    raw = value
    if not isinstance(raw, str) or not raw.strip():
        raise DomainError("ADD_INPUT_INVALID", "capture input must be non-empty")

    def doi_candidate() -> CaptureCandidate:
        try:
            doi = normalize_doi(raw)
        except DomainError as error:
            raise DomainError("ADD_INPUT_INVALID", "input is not a DOI") from error
        return CaptureCandidate(raw, selected, "doi", doi=doi)

    def arxiv_candidate() -> CaptureCandidate:
        try:
            arxiv = normalize_arxiv(raw)
        except DomainError as error:
            raise DomainError("ADD_INPUT_INVALID", "input is not an arXiv identifier") from error
        return CaptureCandidate(raw, selected, "arxiv", arxiv=arxiv)

    if selected is CaptureType.PAPER:
        try:
            return doi_candidate()
        except DomainError:
            return arxiv_candidate()
    if selected is CaptureType.BOOK:
        try:
            return doi_candidate()
        except DomainError:
            return CaptureCandidate(raw, selected, "isbn", isbn=normalize_isbn(raw))
    if selected is CaptureType.WEB:
        return CaptureCandidate(raw, selected, "web", canonical_url=canonicalize_web_url(raw))
    if selected is CaptureType.REPO:
        repository = normalize_repository_url(raw, configured=False, explicit=True)
        return CaptureCandidate(raw, selected, "repo", repository=repository)

    try:
        return arxiv_candidate()
    except DomainError:
        pass
    try:
        return doi_candidate()
    except DomainError:
        pass
    try:
        return CaptureCandidate(raw, None, "isbn", isbn=normalize_isbn(raw))
    except DomainError:
        pass
    canonical_url = canonicalize_web_url(raw)
    host = urlsplit(canonical_url).hostname
    configured_hosts = frozenset(repository_hosts)
    if host in configured_hosts:
        repository = normalize_repository_url(raw, configured=True)
        return CaptureCandidate(raw, None, "repo", repository=repository)
    return CaptureCandidate(raw, None, "web", canonical_url=canonical_url)
