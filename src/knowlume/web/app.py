from __future__ import annotations

import json
import logging
import secrets
from collections.abc import Callable, Collection, Mapping
from pathlib import PurePosixPath
from typing import Any, cast
from urllib.parse import urlencode, urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from jinja2 import BaseLoader, Environment, StrictUndefined, TemplateNotFound, select_autoescape
from markupsafe import Markup

from knowlume.adapters.sqlite_projection import SQLiteProjection
from knowlume.application.catalog import CatalogQueryService
from knowlume.application.query import QueryService
from knowlume.application.rendering import SafeMarkdownRenderer, safe_external_url
from knowlume.domain.search import ContextScope, SearchFilters
from knowlume.domain.values import DomainError
from knowlume.ports.vault import Vault
from knowlume.resources import AssetError, read_asset_bytes, read_asset_text

LOGGER = logging.getLogger("knowlume.web")
ALLOWED_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; "
        "form-action 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
        "connect-src 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cache-Control": "no-store",
}


class PackageTemplateLoader(BaseLoader):
    def __init__(self, reader: Callable[[str], str] = read_asset_text) -> None:
        self._reader = reader

    def get_source(
        self, environment: Environment, template: str
    ) -> tuple[str, str, Callable[[], bool]]:
        del environment
        path = PurePosixPath(template)
        if (
            not template
            or "\\" in template
            or path.is_absolute()
            or ".." in path.parts
            or path.as_posix() != template
        ):
            raise TemplateNotFound(template)
        try:
            source = self._reader(f"templates/web/{template}")
        except AssetError as error:
            raise TemplateNotFound(template) from error
        return source, f"package:templates/web/{template}", lambda: True


class WebHttpError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        recovery: str = "",
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.recovery = recovery
        self.correlation_id = correlation_id


def _format_value(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(", ", ": "))


def _object_href(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    if value.startswith("src_"):
        return f"/sources/{value}"
    if value.startswith("note_"):
        return f"/notes/{value}"
    return None


def _page_url(request: Request, page: int) -> str:
    pairs = [(key, value) for key, value in request.query_params.multi_items() if key != "page"]
    pairs.append(("page", str(page)))
    return f"{request.url.path}?{urlencode(pairs)}"


def _environment(
    renderer: SafeMarkdownRenderer,
    template_reader: Callable[[str], str],
) -> Environment:
    environment = Environment(
        loader=PackageTemplateLoader(template_reader),
        autoescape=select_autoescape(("html", "xml"), default_for_string=True, default=True),
        undefined=StrictUndefined,
    )
    environment.filters["markdown"] = lambda value: Markup(renderer.render(value).value)
    environment.filters["display"] = _format_value
    environment.filters["external_url"] = safe_external_url
    environment.globals["object_href"] = _object_href
    environment.globals["page_url"] = _page_url
    return environment


def _with_security_headers(response: Response) -> Response:
    for name, value in SECURITY_HEADERS.items():
        response.headers[name] = value
    return response


def _authority(value: str, configured_port: int) -> tuple[str, int] | None:
    if not value or any(character.isspace() for character in value) or "," in value or "@" in value:
        return None
    try:
        parsed = urlsplit(f"//{value}")
        hostname = parsed.hostname.lower() if parsed.hostname else ""
        port = parsed.port
    except ValueError:
        return None
    if parsed.path or parsed.query or parsed.fragment or hostname not in ALLOWED_LOOPBACK_HOSTS:
        return None
    effective_port = port if port is not None else 80
    if effective_port != configured_port:
        return None
    return hostname, effective_port


def _origin(value: str, configured_port: int) -> tuple[str, int] | None:
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname.lower() if parsed.hostname else ""
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "http"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or hostname not in ALLOWED_LOOPBACK_HOSTS
    ):
        return None
    effective_port = port if port is not None else 80
    if effective_port != configured_port:
        return None
    return hostname, effective_port


def _query_values(
    request: Request,
    *,
    allowed: set[str],
    repeatable: Collection[str] = frozenset(),
) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for name, value in request.query_params.multi_items():
        if name not in allowed:
            raise WebHttpError(400, "WEB_QUERY_INVALID", "请求参数无效。")
        values.setdefault(name, []).append(value)
    if any(len(items) > 1 and name not in repeatable for name, items in values.items()):
        raise WebHttpError(400, "WEB_QUERY_INVALID", "请求参数无效。")
    return values


def _single(values: Mapping[str, list[str]], name: str) -> str | None:
    items = values.get(name)
    return items[0] if items and items[0] else None


def _tags(values: Mapping[str, list[str]]) -> tuple[str, ...]:
    return tuple(value for value in values.get("tag", ()) if value)


def _positive_int(value: str | None, *, default: int, maximum: int | None = None) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as error:
        raise WebHttpError(400, "WEB_QUERY_INVALID", "页码或数量参数无效。") from error
    if parsed < 1 or maximum is not None and parsed > maximum:
        raise WebHttpError(400, "WEB_QUERY_INVALID", "页码或数量参数无效。")
    return parsed


def _domain_web_error(error: DomainError) -> WebHttpError:
    if error.code in {"SEARCH_QUERY_INVALID", "CATALOG_QUERY_INVALID", "FIELD_INVALID"}:
        return WebHttpError(400, error.code, "查询或筛选条件无效。")
    if error.code == "OBJECT_NOT_FOUND":
        return WebHttpError(404, error.code, "对象不存在。")
    recoveries = {
        "INDEX_NOT_FOUND": "kb index build",
        "INDEX_SOURCE_CHANGED": "kb index build",
        "INDEX_SOURCE_INVALID": "kb index build",
        "INDEX_INCOMPATIBLE": "kb index rebuild",
        "INDEX_CORRUPT": "kb index rebuild",
    }
    if recovery := recoveries.get(error.code):
        return WebHttpError(503, error.code, "搜索索引当前不可用。", recovery=recovery)
    correlation_id = secrets.token_hex(8)
    LOGGER.error("web request failed correlation_id=%s", correlation_id)
    return WebHttpError(
        500,
        "WEB_INTERNAL_ERROR",
        "发生未预期错误。",
        correlation_id=correlation_id,
    )


def create_app(
    *,
    vault: Vault,
    catalog: CatalogQueryService,
    query: QueryService,
    projection: SQLiteProjection,
    port: int = 8765,
    template_reader: Callable[[str], str] = read_asset_text,
    asset_reader: Callable[[str], bytes] = read_asset_bytes,
) -> FastAPI:
    """Create the optional read-only app without reading or mutating the Vault."""

    templates = _environment(SafeMarkdownRenderer(), template_reader)

    app = FastAPI(
        title="Knowlume",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    def render(
        request: Request,
        template_name: str,
        context: dict[str, object] | None = None,
        *,
        status_code: int = 200,
    ) -> HTMLResponse:
        payload: dict[str, object] = {
            "request": request,
            "current_path": request.url.path,
        }
        if context:
            payload.update(context)
        content = templates.get_template(template_name).render(payload)
        return HTMLResponse(content, status_code=status_code)

    @app.middleware("http")
    async def local_security_boundary(request: Request, call_next: Callable[..., Any]) -> Response:
        current = _authority(request.headers.get("host", ""), port)
        origin_value = request.headers.get("origin")
        if current is None or (
            origin_value is not None and _origin(origin_value, port) != current
        ):
            response = render(
                request,
                "error.html",
                {"code": "WEB_ORIGIN_REJECTED", "message": "请求来源被拒绝。", "recovery": ""},
                status_code=403,
            )
            return _with_security_headers(response)
        try:
            response = await call_next(request)
        except Exception:
            correlation_id = secrets.token_hex(8)
            LOGGER.error("web request failed correlation_id=%s", correlation_id)
            response = render(
                request,
                "error.html",
                {
                    "code": "WEB_INTERNAL_ERROR",
                    "message": "发生未预期错误。",
                    "recovery": "",
                    "correlation_id": correlation_id,
                },
                status_code=500,
            )
        return _with_security_headers(response)

    @app.exception_handler(WebHttpError)
    async def web_error(request: Request, error: WebHttpError) -> Response:
        return _with_security_headers(
            render(
                request,
                "error.html",
                {
                    "code": error.code,
                    "message": error.message,
                    "recovery": error.recovery,
                    "correlation_id": error.correlation_id,
                },
                status_code=error.status_code,
            )
        )

    @app.exception_handler(404)
    async def not_found(request: Request, _error: Exception) -> Response:
        return _with_security_headers(
            render(
                request,
                "error.html",
                {"code": "WEB_NOT_FOUND", "message": "页面或资源不存在。", "recovery": ""},
                status_code=404,
            )
        )

    @app.exception_handler(405)
    async def method_not_allowed(request: Request, _error: Exception) -> Response:
        return _with_security_headers(
            render(
                request,
                "error.html",
                {
                    "code": "WEB_METHOD_NOT_ALLOWED",
                    "message": "此页面只允许只读请求。",
                    "recovery": "",
                },
                status_code=405,
            )
        )

    @app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        try:
            data = catalog.dashboard(vault)
        except DomainError as error:
            raise _domain_web_error(error) from error
        return render(request, "dashboard.html", {"dashboard": data})

    @app.api_route("/sources", methods=["GET", "HEAD"], response_class=HTMLResponse)
    async def sources(request: Request) -> HTMLResponse:
        values = _query_values(
            request,
            allowed={"source_type", "workflow_stage", "record_status", "visibility", "tag", "page"},
            repeatable={"tag"},
        )
        try:
            page = catalog.sources(
                vault,
                source_type=_single(values, "source_type"),
                workflow_stage=_single(values, "workflow_stage"),
                record_status=_single(values, "record_status"),
                visibility=_single(values, "visibility"),
                tags=_tags(values),
                page=_positive_int(_single(values, "page"), default=1),
            )
        except DomainError as error:
            raise _domain_web_error(error) from error
        template = (
            "fragments/catalog-list.html"
            if request.headers.get("hx-request") == "true"
            else "sources.html"
        )
        return render(request, template, {"catalog_page": page, "catalog_kind": "source"})

    @app.api_route("/sources/{source_id}", methods=["GET", "HEAD"], response_class=HTMLResponse)
    async def source_detail(request: Request, source_id: str) -> HTMLResponse:
        _query_values(request, allowed=set())
        try:
            detail = catalog.detail(vault, source_id, expected_kind="source")
        except DomainError as error:
            raise _domain_web_error(error) from error
        source = cast(dict[str, object], detail["object"])
        source["attachment_exists"] = bool(source.get("attachment_key"))
        source["external_url"] = safe_external_url(source.get("canonical_url"))
        return render(request, "source-detail.html", {"detail": detail})

    @app.api_route("/notes", methods=["GET", "HEAD"], response_class=HTMLResponse)
    async def notes(request: Request) -> HTMLResponse:
        values = _query_values(
            request,
            allowed={"note_type", "maturity", "record_status", "visibility", "tag", "page"},
            repeatable={"tag"},
        )
        try:
            page = catalog.notes(
                vault,
                note_type=_single(values, "note_type"),
                maturity=_single(values, "maturity"),
                record_status=_single(values, "record_status"),
                visibility=_single(values, "visibility"),
                tags=_tags(values),
                page=_positive_int(_single(values, "page"), default=1),
            )
        except DomainError as error:
            raise _domain_web_error(error) from error
        template = (
            "fragments/catalog-list.html"
            if request.headers.get("hx-request") == "true"
            else "notes.html"
        )
        return render(request, template, {"catalog_page": page, "catalog_kind": "note"})

    @app.api_route("/notes/{note_id}", methods=["GET", "HEAD"], response_class=HTMLResponse)
    async def note_detail(request: Request, note_id: str) -> HTMLResponse:
        _query_values(request, allowed=set())
        try:
            detail = catalog.detail(vault, note_id, expected_kind="note")
        except DomainError as error:
            raise _domain_web_error(error) from error
        return render(request, "note-detail.html", {"detail": detail})

    @app.api_route("/search", methods=["GET", "HEAD"], response_class=HTMLResponse)
    async def search(request: Request) -> HTMLResponse:
        values = _query_values(
            request,
            allowed={
                "q", "kind", "subtype", "visibility", "record_status", "workflow_stage",
                "maturity", "review_status", "tag", "role", "scope", "limit",
            },
            repeatable={"tag"},
        )
        q = _single(values, "q") or ""
        result: dict[str, object] | None = None
        if q.strip():
            try:
                selected_scope = ContextScope(
                    _single(values, "scope") or ContextScope.TRUSTED_LOCAL.value
                )
                filters = SearchFilters(
                    kind=_single(values, "kind"),
                    subtype=_single(values, "subtype"),
                    visibility=_single(values, "visibility"),
                    record_status=_single(values, "record_status"),
                    workflow_stage=_single(values, "workflow_stage"),
                    maturity=_single(values, "maturity"),
                    review_status=_single(values, "review_status"),
                    tags=_tags(values),
                    role=_single(values, "role"),
                )
                result = query.search(
                    vault,
                    q,
                    filters,
                    selected_scope,
                    _positive_int(_single(values, "limit"), default=20, maximum=200),
                )
            except (DomainError, ValueError) as error:
                domain_error = (
                    error
                    if isinstance(error, DomainError)
                    else DomainError("SEARCH_QUERY_INVALID", "unsupported search scope")
                )
                raise _domain_web_error(domain_error) from error
        template = (
            "fragments/search-results.html"
            if request.headers.get("hx-request") == "true"
            else "search.html"
        )
        return render(
            request,
            template,
            {"query_text": q, "search_result": result, "search_values": values},
        )

    @app.api_route("/health", methods=["GET", "HEAD"], response_class=HTMLResponse)
    async def health(request: Request) -> HTMLResponse:
        values = _query_values(request, allowed={"page"})
        try:
            data = catalog.health(
                vault, page=_positive_int(_single(values, "page"), default=1)
            )
        except DomainError as error:
            raise _domain_web_error(error) from error
        return render(request, "health.html", {"health": data})

    @app.api_route("/assets/app.css", methods=["GET", "HEAD"])
    async def stylesheet(request: Request) -> Response:
        _query_values(request, allowed=set())
        return Response(asset_reader("templates/web/assets/app.css"), media_type="text/css")

    @app.api_route("/assets/htmx.min.js", methods=["GET", "HEAD"])
    async def htmx(request: Request) -> Response:
        _query_values(request, allowed=set())
        return Response(
            asset_reader("templates/web/assets/htmx.min.js"),
            media_type="text/javascript",
        )

    app.state.knowlume_services = {
        "vault": vault,
        "catalog": catalog,
        "query": query,
        "projection": projection,
    }
    return app
