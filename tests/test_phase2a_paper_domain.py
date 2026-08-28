from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from knowlume.adapters.contract_v2 import parse_object_document
from knowlume.application.paper_identity import find_existing_paper, source_identity
from knowlume.domain.models import Source
from knowlume.domain.paper import PaperIdentity, managed_fields_hash, normalize_arxiv, normalize_doi
from knowlume.domain.values import DomainError

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "value",
    [
        "10.1000/ABC.Def",
        " doi: 10.1000/ABC.Def ",
        "https://doi.org/10.1000/ABC.Def",
        "http://dx.doi.org/10.1000%2FABC.Def",
    ],
)
def test_doi_normalization(value: str) -> None:
    assert str(normalize_doi(value)) == "10.1000/abc.def"


@pytest.mark.parametrize(
    ("value", "base", "version"),
    [
        ("arXiv:2401.12345v2", "2401.12345", 2),
        ("https://arxiv.org/abs/2401.12345", "2401.12345", None),
        ("https://arxiv.org/pdf/hep-th/9901001v3.pdf", "hep-th/9901001", 3),
        ("math.GT/0309136", "math.gt/0309136", None),
    ],
)
def test_arxiv_normalization(value: str, base: str, version: int | None) -> None:
    result = normalize_arxiv(value)
    assert (result.base_id, result.version) == (base, version)


def _fixture_source() -> Source:
    document = parse_object_document(
        (ROOT / "tests/fixtures/v2/valid/phase2a-paper-source.md").read_text(encoding="utf-8")
    )
    assert isinstance(document.object, Source)
    return document.object


def test_doi_is_canonical_and_arxiv_is_alias() -> None:
    identity = source_identity(_fixture_source())
    assert identity is not None
    assert identity.canonical == "doi:10.1000/example.paper"
    assert identity.aliases == ("doi:10.1000/example.paper", "arxiv:2401.12345")


def test_alias_match_and_split_identity_conflict() -> None:
    first = _fixture_source()
    identity = PaperIdentity(normalize_doi("10.1000/example.paper"), normalize_arxiv("2401.12345"))
    assert find_existing_paper([first], identity) == first.id
    second = replace(
        first,
        id=type(first.id)("src_01JSTAG7N9Q3V5X8Y2Z4A6B8E9"),
        doi="10.1000/other",
        arxiv_id="2401.12345",
    )
    incoming = PaperIdentity(normalize_doi("10.1000/example.paper"), normalize_arxiv("2401.12345"))
    with pytest.raises(DomainError) as caught:
        find_existing_paper([first, second], incoming)
    assert caught.value.code == "PAPER_IDENTITY_CONFLICT"


def test_managed_hash_is_deterministic_and_omits_absent_values() -> None:
    left = managed_fields_hash({"title": "Cafe\u0301", "year": None, "authors": ["Ada"]})
    right = managed_fields_hash({"authors": ["Ada"], "title": "Café"})
    assert left == right
