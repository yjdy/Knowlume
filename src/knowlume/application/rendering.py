from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from markdown_it import MarkdownIt
from markdown_it.token import Token


@dataclass(frozen=True)
class SafeHtml:
    value: str


def safe_external_url(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        and not 1 <= port <= 65535
    ):
        return None
    return value


def _sanitize_inline(children: list[Token]) -> None:
    link_stack: list[bool] = []
    for token in children:
        if token.type == "image":
            token.type = "text"
            token.tag = ""
            token.attrs = {}
            token.children = None
            continue
        if token.type == "link_open":
            href = token.attrGet("href")
            allowed = safe_external_url(href) is not None
            link_stack.append(allowed)
            if allowed:
                token.attrSet("rel", "noopener noreferrer")
            else:
                token.tag = "span"
                token.attrs = {}
        elif token.type == "link_close":
            allowed = link_stack.pop() if link_stack else False
            if not allowed:
                token.tag = "span"


class SafeMarkdownRenderer:
    """Render the frozen non-executable Markdown subset."""

    def __init__(self) -> None:
        self._markdown = MarkdownIt(
            "commonmark",
            {"html": False, "linkify": False, "typographer": False},
        )

    def render(self, value: object) -> SafeHtml:
        text = value if isinstance(value, str) else ""
        tokens = self._markdown.parse(text)
        for token in tokens:
            if token.type == "inline" and token.children:
                _sanitize_inline(token.children)
        return SafeHtml(self._markdown.renderer.render(tokens, self._markdown.options, {}))
