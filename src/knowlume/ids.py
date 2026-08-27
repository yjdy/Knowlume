from __future__ import annotations

import os
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid(*, timestamp_ms: int | None = None, randomness: bytes | None = None) -> str:
    """Return a canonical 26-character ULID without external dependencies."""

    timestamp = int(time.time() * 1000) if timestamp_ms is None else timestamp_ms
    random_bytes = os.urandom(10) if randomness is None else randomness
    if not 0 <= timestamp < 2**48 or len(random_bytes) != 10:
        raise ValueError("ULID timestamp or randomness is out of range")
    value = (timestamp << 80) | int.from_bytes(random_bytes)
    characters = ["0"] * 26
    for index in range(25, -1, -1):
        characters[index] = _CROCKFORD[value & 31]
        value >>= 5
    return "".join(characters)
