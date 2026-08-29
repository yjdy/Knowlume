from __future__ import annotations

import re

from knowlume.domain.values import DomainError

_ISBN_LABEL_RE = re.compile(r"^isbn(?:-1[03])?\s*:?\s*", re.IGNORECASE)


def normalize_isbn(value: str) -> str:
    candidate = _ISBN_LABEL_RE.sub("", value.strip())
    candidate = re.sub(r"[\s-]", "", candidate).upper()
    if re.fullmatch(r"\d{9}[\dX]", candidate):
        total = sum(
            (10 - index) * (10 if char == "X" else int(char))
            for index, char in enumerate(candidate)
        )
        if total % 11:
            raise DomainError("ADD_INPUT_INVALID", "ISBN-10 checksum is invalid")
        body = "978" + candidate[:9]
        check = (
            10
            - sum((1 if index % 2 == 0 else 3) * int(char) for index, char in enumerate(body))
            % 10
        ) % 10
        return f"{body}{check}"
    if re.fullmatch(r"\d{13}", candidate):
        expected = (
            10
            - sum(
                (1 if index % 2 == 0 else 3) * int(char)
                for index, char in enumerate(candidate[:12])
            )
            % 10
        ) % 10
        if int(candidate[-1]) != expected:
            raise DomainError("ADD_INPUT_INVALID", "ISBN-13 checksum is invalid")
        return candidate
    raise DomainError("ADD_INPUT_INVALID", "input is not a checksum-valid ISBN")
