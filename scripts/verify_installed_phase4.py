from __future__ import annotations

import argparse
import hashlib
import http.client
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALID = ROOT / "tests/fixtures/v2/valid"
SECURITY_HEADERS = {
    "Content-Security-Policy",
    "X-Content-Type-Options",
    "Referrer-Policy",
    "X-Frame-Options",
    "Permissions-Policy",
    "Cross-Origin-Opener-Policy",
    "Cross-Origin-Resource-Policy",
    "Cache-Control",
}


def _run(
    command: list[str], *, cwd: Path, check: bool = True
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    return subprocess.run(
        command,
        cwd=cwd,
        check=check,
        capture_output=True,
        encoding="utf-8",
        env=environment,
    )


def _executables(environment: Path) -> tuple[Path, Path]:
    if os.name == "nt":
        return environment / "Scripts/python.exe", environment / "Scripts/kb.exe"
    return environment / "bin/python", environment / "bin/kb"


def _create_environment(root: Path, name: str, wheel: Path, *, web: bool) -> tuple[Path, Path]:
    environment = root / name
    _run(["uv", "venv", "--python", sys.executable, str(environment)], cwd=root)
    python, kb = _executables(environment)
    requirement = f"{wheel}[web]" if web else str(wheel)
    _run(["uv", "pip", "install", "--python", str(python), requirement], cwd=root)
    return python, kb


def _snapshot(root: Path) -> dict[str, tuple[int, str]]:
    return {
        path.relative_to(root).as_posix(): (
            path.stat().st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _free_port(host: str = "127.0.0.1") -> int:
    family = socket.AF_INET6 if host == "::1" else socket.AF_INET
    bind_host = "127.0.0.1" if host == "localhost" else host
    with socket.socket(family, socket.SOCK_STREAM) as listener:
        listener.bind((bind_host, 0))
        return int(listener.getsockname()[1])


def _start_server(
    kb: Path, vault: Path, work: Path, host: str, port: int
) -> subprocess.Popen[str]:
    command = [
        str(kb),
        "--vault",
        str(vault),
        "serve",
        "--host",
        host,
        "--port",
        str(port),
    ]
    process = subprocess.Popen(
        command,
        cwd=work,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
        creationflags=(
            int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) if os.name == "nt" else 0
        ),
    )
    try:
        for _ in range(100):
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                raise RuntimeError(f"Web server exited early: {stdout!r} {stderr!r}")
            try:
                connection = http.client.HTTPConnection(host, port, timeout=1)
                connection.request("GET", "/health")
                response = connection.getresponse()
                status = response.status
                response.read()
                connection.close()
                if status == 200:
                    return process
            except OSError:
                time.sleep(0.1)
    except BaseException:
        process.terminate()
        process.wait(timeout=10)
        raise
    process.terminate()
    raise RuntimeError("Web server did not become ready")


def _stop_server(process: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        process.send_signal(vars(signal)["CTRL_BREAK_EVENT"])
    else:
        process.send_signal(signal.SIGINT)
    try:
        return_code = process.wait(timeout=15)
    except subprocess.TimeoutExpired as error:
        process.terminate()
        process.wait(timeout=10)
        raise RuntimeError("Web server did not stop after interrupt") from error
    if return_code != 0:
        stdout, stderr = process.communicate()
        raise RuntimeError(f"Web server interrupt exit was {return_code}: {stdout!r} {stderr!r}")


def _request(url: str, *, method: str = "GET") -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers.items()), error.read()


def _copy_vault(vault: Path) -> None:
    copies = (
        (VALID / "paper-source.md", vault / "sources/papers/paper.md"),
        (VALID / "literature-note.md", vault / "notes/literature/note.md"),
        (VALID / "idea-note.md", vault / "notes/ideas/idea.md"),
    )
    for source, target in copies:
        shutil.copyfile(source, target)
    relation = VALID / "relations/note_01JSTAG7N9Q3V5X8Y2Z4A6B8D2.yaml"
    shutil.copyfile(relation, vault / "relations" / relation.name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    wheel = parser.parse_args().wheel.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="knowlume-phase4-installed-") as temporary:
        root = Path(temporary)
        work = root / "outside-source-checkout"
        work.mkdir()
        core_python, core_kb = _create_environment(root, "core", wheel, web=False)
        _run([str(core_kb), "serve", "--help"], cwd=work)
        _run(
            [
                str(core_python),
                "-c",
                "import importlib.util; assert importlib.util.find_spec('fastapi') is None",
            ],
            cwd=work,
        )
        core_vault = root / "core-vault"
        _run([str(core_kb), "init", str(core_vault)], cwd=work)
        missing = _run(
            [str(core_kb), "--vault", str(core_vault), "serve"],
            cwd=work,
            check=False,
        )
        if missing.returncode != 5 or "WEB_CAPABILITY_UNAVAILABLE" not in missing.stderr:
            raise RuntimeError("core-only serve did not produce the typed missing-extra diagnostic")

        web_python, web_kb = _create_environment(root, "web", wheel, web=True)
        _run(
            [
                str(web_python),
                "-c",
                "import fastapi,jinja2,markdown_it,uvicorn; "
                "from knowlume.web.app import create_app",
            ],
            cwd=work,
        )
        vault = root / "vault"
        _run([str(web_kb), "init", str(vault)], cwd=work)
        _copy_vault(vault)
        _run([str(web_kb), "--vault", str(vault), "index", "rebuild"], cwd=work)
        before = _snapshot(vault)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied_listener:
            occupied_listener.bind(("127.0.0.1", 0))
            occupied_listener.listen()
            occupied_port = int(occupied_listener.getsockname()[1])
            occupied = _run(
                [
                    str(web_kb),
                    "--vault",
                    str(vault),
                    "serve",
                    "--port",
                    str(occupied_port),
                ],
                cwd=work,
                check=False,
            )
        if occupied.returncode != 5 or "WEB_SERVER_UNAVAILABLE" not in occupied.stderr:
            raise RuntimeError("occupied port did not produce the typed server diagnostic")

        port = _free_port()
        process = _start_server(web_kb, vault, work, "127.0.0.1", port)
        try:
            base = f"http://127.0.0.1:{port}"
            for route in (
                "/",
                "/sources",
                "/sources/src_01JSTAG7N9Q3V5X8Y2Z4A6B8C0",
                "/notes",
                "/notes/note_01JSTAG7N9Q3V5X8Y2Z4A6B8D2",
                "/search?q=Transformer",
                "/health",
                "/assets/app.css",
                "/assets/htmx.min.js",
            ):
                status, headers, body = _request(base + route)
                if status != 200 or not body:
                    raise RuntimeError(f"installed Web route failed: {route} ({status})")
                if not {name.lower() for name in SECURITY_HEADERS} <= {
                    name.lower() for name in headers
                }:
                    raise RuntimeError(f"installed Web route lacks security headers: {route}")
            status, _headers, body = _request(base + "/search?q=Transformer", method="HEAD")
            if status != 200 or body:
                raise RuntimeError("installed HEAD behavior failed")
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            connection.request("GET", "/", headers={"Host": f"evil.example:{port}"})
            rejected = connection.getresponse()
            rejected.read()
            connection.close()
            if rejected.status != 403:
                raise RuntimeError("installed Host rejection failed")
        finally:
            _stop_server(process)
        for host in ("localhost", "::1"):
            host_port = _free_port(host)
            host_process = _start_server(web_kb, vault, work, host, host_port)
            _stop_server(host_process)
        if _snapshot(vault) != before:
            raise RuntimeError("installed Web traversal modified Vault or index state")
    print("installed Phase 4 core-only and Web loopback behavior verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
