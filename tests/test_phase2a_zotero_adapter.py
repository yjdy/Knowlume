from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

from knowlume.adapters.zotero_local import ZoteroLocalApi
from knowlume.domain.values import DomainError
from knowlume.ports.zotero import ZoteroReference


@pytest.fixture()
def mock_zotero() -> Iterator[tuple[str, dict[str, tuple[int, bytes, str]], list[str]]]:
    routes: dict[str, tuple[int, bytes, str]] = {}
    requests: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            requests.append(self.path)
            status, body, content_type = routes.get(self.path, (404, b"missing", "text/plain"))
            if self.path == "/api/slow":
                time.sleep(0.2)
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.end_headers()
            try:
                self.wfile.write(body)
            except BrokenPipeError:
                pass

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/api", routes, requests
    finally:
        server.shutdown()
        thread.join()


def _json(value: object) -> tuple[int, bytes, str]:
    return 200, json.dumps(value).encode(), "application/json"


def _reference() -> ZoteroReference:
    return ZoteroReference("user", "0", "ABCD1234")


def _item() -> dict[str, object]:
    return {
        "key": "ABCD1234",
        "version": 7,
        "data": {
            "title": "Example Paper",
            "DOI": "10.1000/EXAMPLE",
            "extra": "arXiv: 2401.12345v2",
            "url": "https://example.test/paper",
            "date": "2024-01-02",
            "creators": [{"creatorType": "author", "firstName": "Ada", "lastName": "Lovelace"}],
        },
    }


def _child(key: str = "EFGH5678", filename: str = "paper.pdf") -> dict[str, object]:
    return {
        "key": key,
        "version": 3,
        "data": {"itemType": "attachment", "contentType": "application/pdf", "filename": filename},
    }


def test_loopback_only_and_metadata_mapping(
    mock_zotero: tuple[str, dict[str, tuple[int, bytes, str]], list[str]], tmp_path: Path
) -> None:
    endpoint, routes, _ = mock_zotero
    routes["/api/users/0/items/ABCD1234"] = _json(_item())
    result = ZoteroLocalApi(endpoint=endpoint, cache_root=tmp_path).metadata(_reference())
    assert result.title == "Example Paper"
    assert result.authors == ("Ada Lovelace",)
    assert result.year == 2024
    assert result.identity is not None
    assert result.identity.canonical == "doi:10.1000/example"
    assert result.arxiv is not None and result.arxiv.version == 2
    with pytest.raises(DomainError) as caught:
        ZoteroLocalApi(endpoint="https://api.zotero.org")
    assert caught.value.code == "ZOTERO_ENDPOINT_UNSAFE"


@pytest.mark.parametrize(
    ("response", "code"),
    [
        ((403, b"forbidden", "text/plain"), "ZOTERO_PERMISSION_DENIED"),
        ((404, b"missing", "text/plain"), "ZOTERO_ITEM_UNAVAILABLE"),
        ((200, b"{bad", "application/json"), "ZOTERO_RESPONSE_INVALID"),
    ],
)
def test_typed_metadata_failures(
    mock_zotero: tuple[str, dict[str, tuple[int, bytes, str]], list[str]],
    tmp_path: Path,
    response: tuple[int, bytes, str],
    code: str,
) -> None:
    endpoint, routes, _ = mock_zotero
    routes["/api/users/0/items/ABCD1234"] = response
    with pytest.raises(DomainError) as caught:
        ZoteroLocalApi(endpoint=endpoint, cache_root=tmp_path).metadata(_reference())
    assert caught.value.code == code


def test_timeout_is_unavailable(
    mock_zotero: tuple[str, dict[str, tuple[int, bytes, str]], list[str]], tmp_path: Path
) -> None:
    endpoint, _, _ = mock_zotero
    client = ZoteroLocalApi(endpoint=endpoint, cache_root=tmp_path, timeout=0.01)
    with pytest.raises(DomainError) as caught:
        client._request("slow")
    assert caught.value.code == "ZOTERO_API_UNAVAILABLE"


def test_missing_zotero_extra_has_typed_capability_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing_httpx(name: str) -> object:
        assert name == "httpx"
        raise ModuleNotFoundError(name)

    monkeypatch.setattr("knowlume.adapters.zotero_local.importlib.import_module", missing_httpx)
    with pytest.raises(DomainError) as caught:
        ZoteroLocalApi(cache_root=tmp_path)._request("users/0/items/ABCD1234")
    assert caught.value.code == "ZOTERO_CAPABILITY_UNAVAILABLE"


def test_disabled_local_api_is_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def connection_refused(*args: object, **kwargs: object) -> object:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "get", connection_refused)
    with pytest.raises(DomainError) as caught:
        ZoteroLocalApi(cache_root=tmp_path)._request("users/0/items/ABCD1234")
    assert caught.value.code == "ZOTERO_API_UNAVAILABLE"


@pytest.mark.parametrize(
    ("children", "warning"),
    [
        ([], "PAPER_ATTACHMENT_UNAVAILABLE"),
        ([_child(), _child("IJKL9012", "other.pdf")], "PAPER_ATTACHMENT_AMBIGUOUS"),
    ],
)
def test_zero_or_multiple_pdf_candidates_do_not_guess(
    mock_zotero: tuple[str, dict[str, tuple[int, bytes, str]], list[str]],
    tmp_path: Path,
    children: list[dict[str, object]],
    warning: str,
) -> None:
    endpoint, routes, _ = mock_zotero
    routes["/api/users/0/items/ABCD1234/children"] = _json(children)
    result = ZoteroLocalApi(endpoint=endpoint, cache_root=tmp_path).primary_attachment(_reference())
    assert result.attachment is None
    assert result.warning_code == warning


def test_one_pdf_is_cached_and_hashed(
    mock_zotero: tuple[str, dict[str, tuple[int, bytes, str]], list[str]], tmp_path: Path
) -> None:
    endpoint, routes, requests = mock_zotero
    routes["/api/users/0/items/ABCD1234/children"] = _json([_child()])
    routes["/api/users/0/items/EFGH5678/file"] = (200, b"%PDF-example", "application/pdf")
    client = ZoteroLocalApi(endpoint=endpoint, cache_root=tmp_path)
    first = client.primary_attachment(_reference()).attachment
    second = client.primary_attachment(_reference()).attachment
    assert first is not None and second is not None
    assert first.sha256 == "sha256:6b081077b62ba46e09c937ea190244f530db1e421f63cabe1508f8af6f183b31"
    assert first.cache_path.is_file()
    assert requests.count("/api/users/0/items/EFGH5678/file") == 1


def test_zotero10_local_file_redirect_is_cached_and_hashed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "论文 2608.pdf"
    body = b"%PDF-zotero-10-local-redirect"
    source.write_bytes(body)
    endpoint = "http://127.0.0.1:23119/api"
    responses = {
        f"{endpoint}/users/0/items/ABCD1234/children": httpx.Response(
            200, json=[_child(filename=source.name)]
        ),
        f"{endpoint}/users/0/items/EFGH5678/file": httpx.Response(
            302, headers={"location": source.as_uri()}
        ),
    }

    def redirected_get(url: str, *args: object, **kwargs: object) -> httpx.Response:
        return responses[url]

    monkeypatch.setattr(httpx, "get", redirected_get)
    attachment = ZoteroLocalApi(
        endpoint=endpoint, cache_root=tmp_path / "cache"
    ).primary_attachment(_reference()).attachment
    assert attachment is not None
    assert attachment.cache_path != source
    assert attachment.cache_path.read_bytes() == body
    assert attachment.sha256 == f"sha256:{sha256(body).hexdigest()}"


@pytest.mark.parametrize(
    "location",
    [
        "https://example.test/paper.pdf",
        "file://server/share/paper.pdf",
        "file://user:secret@localhost/C:/paper.pdf",
        "file:relative.pdf",
        "file:///C:/paper.pdf?download=1",
        "file:///C:/paper.pdf#fragment",
        "file:////server/share/paper.pdf",
    ],
)
def test_zotero10_unsafe_file_redirects_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    location: str,
) -> None:
    def redirected_get(url: str, *args: object, **kwargs: object) -> httpx.Response:
        return httpx.Response(302, headers={"location": location})

    monkeypatch.setattr(httpx, "get", redirected_get)
    with pytest.raises(DomainError) as caught:
        ZoteroLocalApi(cache_root=tmp_path)._request(
            "users/0/items/EFGH5678/file", binary=True
        )
    assert caught.value.code == "ZOTERO_RESPONSE_INVALID"


def test_zotero10_missing_redirect_target_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = (tmp_path / "missing.pdf").as_uri()

    def redirected_get(url: str, *args: object, **kwargs: object) -> httpx.Response:
        return httpx.Response(302, headers={"location": missing})

    monkeypatch.setattr(httpx, "get", redirected_get)
    with pytest.raises(DomainError) as caught:
        ZoteroLocalApi(cache_root=tmp_path)._request(
            "users/0/items/EFGH5678/file", binary=True
        )
    assert caught.value.code == "ZOTERO_ITEM_UNAVAILABLE"
