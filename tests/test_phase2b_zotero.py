from __future__ import annotations

from collections.abc import Callable
from typing import cast

import pytest

from knowlume.adapters.zotero_local import ZoteroLocalApi
from knowlume.domain.values import DomainError
from knowlume.ports.zotero import ZoteroItem


def _item(
    key: str,
    item_type: str,
    *,
    doi: str = "",
    isbn: str = "",
    url: str = "",
) -> dict[str, object]:
    return {
        "key": key,
        "version": 1,
        "data": {
            "itemType": item_type,
            "title": f"Title {key}",
            "DOI": doi,
            "ISBN": isbn,
            "url": url,
            "date": "2026",
            "edition": "Second Edition",
            "creators": [{"creatorType": "author", "name": "Ada"}],
        },
    }


def _client(responses: dict[str, object | bytes]) -> ZoteroLocalApi:
    client = ZoteroLocalApi()

    def request(path: str, *, binary: bool = False) -> object | bytes:
        assert path in responses, path
        return responses[path]

    client._request = cast(Callable[..., object], request)  # type: ignore[method-assign]
    return client


def test_exact_candidate_search_rechecks_identity_and_does_not_choose_first() -> None:
    path = "users/0/items/top?q=10.1000%2Fexample&qmode=everything&limit=100&start=0"
    client = _client(
        {
            path: [
                _item("AAAA1111", "journalArticle", doi="10.1000/other"),
                _item("BBBB2222", "journalArticle", doi="10.1000/EXAMPLE"),
            ]
        }
    )
    candidates = client.exact_candidates("doi", "10.1000/example")
    assert [item.reference.item_key for item in candidates] == ["BBBB2222"]
    assert candidates[0].item_type == "journalArticle"


def test_exact_candidate_search_follows_all_pages() -> None:
    first = "users/0/items/top?q=10.1000%2Fexample&qmode=everything&limit=100&start=0"
    second = "users/0/items/top?q=10.1000%2Fexample&qmode=everything&limit=100&start=100"
    client = _client(
        {
            first: [
                _item(f"A{index:07d}", "journalArticle", doi=f"10.1000/other-{index}")
                for index in range(100)
            ],
            second: [_item("BBBB2222", "journalArticle", doi="10.1000/example")],
        }
    )
    keys = [
        item.reference.item_key
        for item in client.exact_candidates("doi", "10.1000/example")
    ]
    assert keys == ["BBBB2222"]


@pytest.mark.parametrize("count", [0, 1, 2])
def test_exact_candidate_search_preserves_zero_one_or_multiple_matches(count: int) -> None:
    path = "users/0/items/top?q=10.1000%2Fexample&qmode=everything&limit=100&start=0"
    items = [
        _item(f"B{index:07d}", "journalArticle", doi="10.1000/example")
        for index in range(count)
    ]
    assert len(_client({path: items}).exact_candidates("doi", "10.1000/example")) == count


@pytest.mark.parametrize(
    "item_type",
    ["journalArticle", "conferencePaper", "preprint", "thesis", "report", "manuscript"],
)
def test_all_paper_item_types_are_preserved_for_classification(item_type: str) -> None:
    path = "users/0/items/top?q=10.1000%2Fexample&qmode=everything&limit=100&start=0"
    result = _client(
        {path: [_item("BBBB2222", item_type, doi="10.1000/example")]}
    ).exact_candidates("doi", "10.1000/example")
    assert result[0].item_type == item_type


def test_web_snapshot_requires_one_eligible_nonempty_child() -> None:
    search = (
        "users/0/items/top?q=https%3A%2F%2Fexample.test%2Fpage&qmode=everything&limit=100&start=0"
    )
    children = "users/0/items/ABCD1234/children"
    body = "users/0/items/EFGH5678/file"
    client = _client(
        {
            search: [_item("ABCD1234", "webpage", url="https://example.test/page")],
            children: [
                {
                    "key": "EFGH5678",
                    "version": 2,
                    "data": {
                        "itemType": "attachment",
                        "parentItem": "ABCD1234",
                        "linkMode": "imported_url",
                        "contentType": "text/html",
                        "dateAdded": "2026-08-29T10:20:30Z",
                    },
                }
            ],
            body: b"<html>snapshot</html>",
        }
    )
    item = client.exact_candidates("url", "https://example.test/page")[0]
    snapshot = client.web_snapshot(item)
    assert snapshot.captured_at.isoformat() == "2026-08-29T10:20:30+00:00"
    assert snapshot.snapshot_ref.identifier == "user/0/ABCD1234/EFGH5678"
    assert snapshot.snapshot_ref.content_hash.startswith("sha256:")


@pytest.mark.parametrize(
    "children",
    [
        [],
        [
            {
                "key": "EFGH5678",
                "version": 2,
                "data": {
                    "itemType": "attachment",
                    "parentItem": "WRONG111",
                    "linkMode": "imported_url",
                    "contentType": "text/html",
                    "dateAdded": "2026-08-29T10:20:30Z",
                },
            }
        ],
    ],
)
def test_web_snapshot_missing_or_ineligible_is_typed(children: list[dict[str, object]]) -> None:
    client = _client({"users/0/items/ABCD1234/children": children})
    search = (
        "users/0/items/top?q=https%3A%2F%2Fexample.test%2Fpage"
        "&qmode=everything&limit=100&start=0"
    )
    item = _client(
        {search: [_item("ABCD1234", "webpage", url="https://example.test/page")]}
    ).exact_candidates("url", "https://example.test/page")[0]
    with pytest.raises(DomainError) as caught:
        client.web_snapshot(item)
    assert caught.value.code == "ZOTERO_ITEM_UNAVAILABLE"


def _child(**changes: object) -> dict[str, object]:
    data: dict[str, object] = {
        "itemType": "attachment",
        "parentItem": "ABCD1234",
        "linkMode": "imported_url",
        "contentType": "text/html",
        "dateAdded": "2026-08-29T10:20:30Z",
    }
    data.update(changes)
    return {"key": "EFGH5678", "version": 2, "data": data}


@pytest.mark.parametrize(
    "changes",
    [
        {"itemType": "note"},
        {"parentItem": "WRONG111"},
        {"linkMode": "linked_url"},
        {"contentType": "application/pdf"},
    ],
)
def test_each_web_snapshot_eligibility_field_is_enforced(changes: dict[str, object]) -> None:
    client = _client({"users/0/items/ABCD1234/children": [_child(**changes)]})
    item = _web_item()
    with pytest.raises(DomainError) as caught:
        client.web_snapshot(item)
    assert caught.value.code == "ZOTERO_ITEM_UNAVAILABLE"


def _web_item() -> ZoteroItem:
    search = (
        "users/0/items/top?q=https%3A%2F%2Fexample.test%2Fpage"
        "&qmode=everything&limit=100&start=0"
    )
    return _client(
        {search: [_item("ABCD1234", "webpage", url="https://example.test/page")]}
    ).exact_candidates("url", "https://example.test/page")[0]


def test_multiple_eligible_web_snapshots_are_rejected() -> None:
    second = _child()
    second["key"] = "IJKL9012"
    client = _client({"users/0/items/ABCD1234/children": [_child(), second]})
    with pytest.raises(DomainError) as caught:
        client.web_snapshot(_web_item())
    assert caught.value.code == "ZOTERO_ITEM_UNAVAILABLE"


@pytest.mark.parametrize("date_added", [None, "", "not-a-date", "2026-08-29T10:20:30"])
def test_web_snapshot_date_must_be_present_parseable_and_timezone_aware(
    date_added: object,
) -> None:
    child = _child(dateAdded=date_added)
    client = _client({"users/0/items/ABCD1234/children": [child]})
    with pytest.raises(DomainError) as caught:
        client.web_snapshot(_web_item())
    assert caught.value.code == "ZOTERO_RESPONSE_INVALID"


def test_empty_or_unrecoverable_web_snapshot_bytes_are_typed() -> None:
    children_path = "users/0/items/ABCD1234/children"
    body_path = "users/0/items/EFGH5678/file"
    empty = _client({children_path: [_child()], body_path: b""})
    with pytest.raises(DomainError) as caught:
        empty.web_snapshot(_web_item())
    assert caught.value.code == "ZOTERO_ITEM_UNAVAILABLE"

    unavailable = _client({children_path: [_child()]})
    original = unavailable._request

    def request(path: str, *, binary: bool = False) -> object | bytes:
        if path == body_path:
            raise DomainError("ZOTERO_API_UNAVAILABLE", "offline")
        return original(path, binary=binary)

    unavailable._request = request  # type: ignore[method-assign]
    with pytest.raises(DomainError) as caught:
        unavailable.web_snapshot(_web_item())
    assert caught.value.code == "ZOTERO_API_UNAVAILABLE"


def test_malformed_web_children_payload_is_typed() -> None:
    client = _client({"users/0/items/ABCD1234/children": {"not": "a list"}})
    with pytest.raises(DomainError) as caught:
        client.web_snapshot(_web_item())
    assert caught.value.code == "ZOTERO_RESPONSE_INVALID"
