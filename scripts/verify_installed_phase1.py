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
SOURCE_FIXTURE = ROOT / "tests/fixtures/v2/valid/paper-source.md"
V1_SOURCE_FIXTURE = ROOT / "tests/fixtures/v1/valid/paper-source.md"
SOURCE_ID = "src_01JSTAG7N9Q3V5X8Y2Z4A6B8C0"


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "cp1252"
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        encoding="utf-8",
        env=environment,
    )


def _run_result(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "cp1252"
    return subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        encoding="utf-8",
        env=environment,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    wheel = args.wheel.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="knowlume-installed-") as temporary:
        root = Path(temporary)
        environment = root / "environment"
        work = root / "arbitrary-cwd"
        work.mkdir()
        _run(["uv", "venv", "--python", sys.executable, str(environment)], cwd=work)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        kb = environment / ("Scripts/kb.exe" if os.name == "nt" else "bin/kb")
        _run(["uv", "pip", "install", "--python", str(python), str(wheel)], cwd=work)

        _run([str(kb), "--version"], cwd=work)
        _run([str(kb), "--help"], cwd=work)
        _run([str(kb), "doctor"], cwd=work)
        for command in ("init", "scan", "status", "lint", "migrate", "inbox", "process"):
            _run([str(kb), command, "--help"], cwd=work)
        for group in ("note", "relation", "source"):
            _run([str(kb), group, "--help"], cwd=work)

        vault = root / "vault"
        _run([str(kb), "init", str(vault)], cwd=work)
        shutil.copyfile(SOURCE_FIXTURE, vault / "sources/papers/paper.md")
        base = [str(kb), "--vault", str(vault)]
        _run([*base, "scan"], cwd=work)
        _run([*base, "status"], cwd=work)
        _run([*base, "lint"], cwd=work)
        _run([*base, "source", "list", "--json"], cwd=work)
        _run([*base, "source", "show", SOURCE_ID, "--json"], cwd=work)
        _run([*base, "inbox", "--json"], cwd=work)
        missing_extra = _run_result([*base, "source", "sync", SOURCE_ID, "--json"], cwd=work)
        assert missing_extra.returncode == 5, missing_extra.stderr
        missing_document = json.loads(missing_extra.stdout)
        assert missing_document["errors"] == [
            {
                "code": "ZOTERO_CAPABILITY_UNAVAILABLE",
                "message": "Zotero support requires the 'knowlume[zotero]' optional dependency",
            }
        ]
        identifiers: dict[str, str] = {}
        for note_type in ("idea", "concept", "synthesis"):
            result = _run([*base, "note", "new", "--type", note_type], cwd=work)
            identifiers[note_type] = result.stdout.strip()
        literature = _run(
            [*base, "note", "new", "--type", "literature", "--source", SOURCE_ID],
            cwd=work,
        )
        identifiers["literature"] = literature.stdout.strip()
        _run([*base, "note", "show", identifiers["idea"]], cwd=work)
        _run(
            [*base, "note", "evolve", identifiers["idea"], "--to", "concept"],
            cwd=work,
        )
        relation = [identifiers["idea"], identifiers["concept"], "--type", "related_to"]
        _run([*base, "relation", "add", *relation], cwd=work)
        _run([*base, "relation", "list", identifiers["concept"]], cwd=work)
        _run([*base, "relation", "remove", *relation], cwd=work)
        _run([*base, "scan"], cwd=work)

        v1 = root / "v1-vault"
        (v1 / "sources/papers").mkdir(parents=True)
        shutil.copyfile(V1_SOURCE_FIXTURE, v1 / "sources/papers/paper.md")
        _run(
            [
                str(kb),
                "--vault",
                str(v1),
                "migrate",
                "--from",
                "1",
                "--to",
                "2",
                "--dry-run",
            ],
            cwd=work,
        )
        _run(
            ["uv", "pip", "install", "--python", str(python), f"{wheel}[zotero]"],
            cwd=work,
        )
        _run([str(python), "-c", "import httpx"], cwd=work)
        _run([str(kb), "source", "--help"], cwd=work)
        _run([*base, "source", "list", "--json"], cwd=work)
    print("installed command smoke through Phase 2A verified with core and Zotero profiles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
