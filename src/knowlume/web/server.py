from __future__ import annotations

import signal
import socket
import sys
import webbrowser
from collections.abc import Callable
from typing import Any

import uvicorn

from knowlume.adapters.sqlite_projection import SQLiteProjection
from knowlume.application.catalog import CatalogQueryService
from knowlume.application.query import QueryService
from knowlume.domain.values import DomainError
from knowlume.ports.vault import Vault
from knowlume.web.app import create_app


class _AfterStartupServer(uvicorn.Server):
    """Invoke the browser callback only after Uvicorn owns a listening socket."""

    def __init__(self, config: uvicorn.Config, on_started: Callable[[], None]) -> None:
        super().__init__(config)
        self._on_started = on_started

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets=sockets)
        if self.started:
            self._on_started()


def _serve(app: Any, *, host: str, port: int, on_started: Callable[[], None]) -> None:
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        access_log=False,
        proxy_headers=False,
        log_level="warning",
    )
    _AfterStartupServer(config, on_started).run()


def run_server(
    vault: Vault,
    *,
    host: str,
    port: int,
    open_browser: bool,
    browser_opener: Callable[[str], bool] = webbrowser.open,
) -> None:
    projection = SQLiteProjection()
    catalog = CatalogQueryService(
        index_status=lambda selected_vault, scan: projection.status(selected_vault, scan=scan)
    )
    query = QueryService(projection)

    def started() -> None:
        if not open_browser:
            return
        browser_host = f"[{host}]" if host == "::1" else host
        try:
            opened = browser_opener(f"http://{browser_host}:{port}/")
        except Exception:
            opened = False
        if not opened:
            print(
                "WEB_BROWSER_OPEN_FAILED: server started but the browser could not be opened",
                file=sys.stderr,
            )

    app = create_app(
        vault=vault,
        catalog=catalog,
        query=query,
        projection=projection,
        port=port,
    )
    break_signal = getattr(signal, "SIGBREAK", None)
    previous_break_handler: Any = None
    if break_signal is not None:
        previous_break_handler = signal.getsignal(break_signal)

        def interrupt_on_break(_signum: int, _frame: object) -> None:
            raise KeyboardInterrupt

        signal.signal(break_signal, interrupt_on_break)
    try:
        try:
            _serve(
                app,
                host=host,
                port=port,
                on_started=started,
            )
        except (OSError, SystemExit) as error:
            raise DomainError(
                "WEB_SERVER_UNAVAILABLE", "loopback server could not start"
            ) from error
    finally:
        if break_signal is not None and previous_break_handler is not None:
            signal.signal(break_signal, previous_break_handler)
