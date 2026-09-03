from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALID = ROOT / "tests/fixtures/v2/valid"
NOTE_ID = "note_01JSTAG7N9Q3V5X8Y2Z4A6B8D2"
SOURCE_ID = "src_01JSTAG7N9Q3V5X8Y2Z4A6B8C0"


def _run(command: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
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


def _json(command: list[str], *, cwd: Path, code: int = 0) -> dict[str, object]:
    result = _run(command, cwd=cwd, check=False)
    if result.returncode != code:
        raise RuntimeError(
            f"unexpected exit {result.returncode}: {result.stdout!r} {result.stderr!r}"
        )
    document = json.loads(result.stdout)
    if not isinstance(document, dict):
        raise RuntimeError("command did not emit one JSON object")
    return document


def _copy_vault_fixtures(vault: Path) -> None:
    copies = (
        (VALID / "paper-source.md", vault / "sources/papers/paper.md"),
        (VALID / "literature-note.md", vault / "notes/literature/note.md"),
        (VALID / "public-idea-note.md", vault / "notes/ideas/public.md"),
    )
    for source, target in copies:
        shutil.copyfile(source, target)
    relation = VALID / "relations" / f"{NOTE_ID}.yaml"
    shutil.copyfile(relation, vault / "relations" / relation.name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    wheel = parser.parse_args().wheel.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="knowlume-phase3-installed-") as temporary:
        root = Path(temporary)
        environment = root / "environment"
        work = root / "outside-source-checkout"
        work.mkdir()
        _run(["uv", "venv", "--python", sys.executable, str(environment)], cwd=work)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        kb = environment / ("Scripts/kb.exe" if os.name == "nt" else "bin/kb")
        _run(["uv", "pip", "install", "--python", str(python), str(wheel)], cwd=work)
        probe = _run(
            [
                str(python),
                "-c",
                (
                    "import importlib.util,sqlite3; "
                    "assert importlib.util.find_spec('fastapi') is None; "
                    "assert importlib.util.find_spec('httpx') is None; "
                    "c=sqlite3.connect(':memory:'); "
                    "c.execute('CREATE VIRTUAL TABLE probe USING fts5(value)'); c.close()"
                ),
            ],
            cwd=work,
            check=False,
        )
        if probe.returncode != 0:
            raise RuntimeError("core wheel or SQLite FTS5 capability is unavailable")

        for command in (
            ["grep", "--help"],
            ["get", "--help"],
            ["index", "--help"],
            ["search", "--help"],
            ["context", "--help"],
        ):
            _run([str(kb), *command], cwd=work)

        vault = root / "vault"
        _run([str(kb), "init", str(vault)], cwd=work)
        _copy_vault_fixtures(vault)
        base = [str(kb), "--vault", str(vault)]
        assert _json([*base, "index", "status", "--json"], cwd=work)["data"]["state"] == "missing"  # type: ignore[index]
        assert _json([*base, "grep", "Transformer", "--json"], cwd=work)["data"]["count"] > 0  # type: ignore[index]
        assert _json([*base, "get", NOTE_ID, "--json"], cwd=work)["data"]["object_id"] == NOTE_ID  # type: ignore[index]
        missing = _json([*base, "search", "Transformer", "--json"], cwd=work, code=5)
        assert missing["errors"][0]["code"] == "INDEX_NOT_FOUND"  # type: ignore[index]

        rebuilt = _json([*base, "index", "rebuild", "--json"], cwd=work)
        assert rebuilt["data"]["state"] == "fresh"  # type: ignore[index]
        search = _json(
            [
                *base,
                "search",
                "Transformer",
                "--kind",
                "note",
                "--role",
                "fact",
                "--tag",
                "transformer",
                "--json",
            ],
            cwd=work,
        )
        assert search["data"]["hits"][0]["object_id"] == NOTE_ID  # type: ignore[index]
        context = _json(
            [*base, "context", "Transformer", "--scope", "public-safe", "--json"],
            cwd=work,
        )
        assert context["data"]["groups"]["facts"]  # type: ignore[index]

        _run([*base, "process", SOURCE_ID, "--to", "integrated"], cwd=work)
        assert _json([*base, "index", "status", "--json"], cwd=work)["data"]["state"] == "fresh"  # type: ignore[index]
        _run([*base, "note", "new", "--type", "idea"], cwd=work)
        assert _json([*base, "index", "status", "--json"], cwd=work)["data"]["state"] == "fresh"  # type: ignore[index]

        database = vault / ".knowlume" / "kb.sqlite"
        database.write_bytes(b"not a sqlite database")
        corrupt = _json([*base, "search", "Transformer", "--json"], cwd=work, code=3)
        assert corrupt["errors"][0]["code"] == "INDEX_CORRUPT"  # type: ignore[index]
        assert _json([*base, "index", "rebuild", "--json"], cwd=work)["data"]["state"] == "fresh"  # type: ignore[index]
        database.unlink()
        assert _json([*base, "index", "status", "--json"], cwd=work)["data"]["state"] == "missing"  # type: ignore[index]
        assert _json([*base, "index", "build", "--json"], cwd=work)["data"]["state"] == "fresh"  # type: ignore[index]
    print("installed Phase 3 core commands and lifecycle verified outside the source checkout")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
