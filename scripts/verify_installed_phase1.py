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
FAKE_COMMIT = "a" * 40


def _fake_git(root: Path) -> Path:
    directory = root / "fake-git"
    directory.mkdir()
    if os.name == "nt":
        executable = directory / "git.cmd"
        executable.write_text(
            "@echo off\n"
            "if not \"%~1\"==\"ls-remote\" exit /b 97\n"
            "if not \"%~2\"==\"--symref\" exit /b 97\n"
            "if not \"%~4\"==\"HEAD\" exit /b 97\n"
            "if not \"%GIT_TERMINAL_PROMPT%\"==\"0\" exit /b 97\n"
            "if not \"%GCM_INTERACTIVE%\"==\"never\" exit /b 97\n"
            "if not \"%GIT_CONFIG_NOSYSTEM%\"==\"1\" exit /b 97\n"
            "if not \"%GIT_CONFIG_COUNT%\"==\"2\" exit /b 97\n"
            "if not \"%GIT_CONFIG_KEY_0%\"==\"credential.helper\" exit /b 97\n"
            "if not \"%GIT_CONFIG_VALUE_0%\"==\"\" exit /b 97\n"
            "if not \"%GIT_CONFIG_KEY_1%\"==\"credential.interactive\" exit /b 97\n"
            "if not \"%GIT_CONFIG_VALUE_1%\"==\"false\" exit /b 97\n"
            "if not exist \"%GIT_CONFIG_GLOBAL%\" exit /b 97\n"
            "if not exist \"%GIT_ASKPASS%\" exit /b 97\n"
            "if not \"%GIT_ASKPASS%\"==\"%SSH_ASKPASS%\" exit /b 97\n"
            "echo %~3 | findstr /C:\"unavailable\" >nul\n"
            "if not errorlevel 1 (\n"
            "  echo secret remote failure 1>&2\n"
            "  exit /b 128\n"
            ")\n"
            "echo %~3 | findstr /C:\"auth-required\" >nul\n"
            "if not errorlevel 1 (\n"
            "  echo password for secret-user required 1>&2\n"
            "  exit /b 128\n"
            ")\n"
            "echo %~3 | findstr /C:\"malformed\" >nul\n"
            "if not errorlevel 1 (\n"
            "  echo malformed\n"
            "  exit /b 0\n"
            ")\n"
            "echo ref: refs/heads/main\tHEAD\n"
            f"echo {FAKE_COMMIT}\tHEAD\n",
            encoding="ascii",
        )
    else:
        executable = directory / "git"
        executable.write_text(
            "#!/bin/sh\n"
            "[ \"$1\" = ls-remote ] || exit 97\n"
            "[ \"$2\" = --symref ] || exit 97\n"
            "[ \"$4\" = HEAD ] || exit 97\n"
            "[ \"$GIT_TERMINAL_PROMPT\" = 0 ] || exit 97\n"
            "[ \"$GCM_INTERACTIVE\" = never ] || exit 97\n"
            "[ \"$GIT_CONFIG_NOSYSTEM\" = 1 ] || exit 97\n"
            "[ \"$GIT_CONFIG_COUNT\" = 2 ] || exit 97\n"
            "[ \"$GIT_CONFIG_KEY_0\" = credential.helper ] || exit 97\n"
            "[ -z \"$GIT_CONFIG_VALUE_0\" ] || exit 97\n"
            "[ \"$GIT_CONFIG_KEY_1\" = credential.interactive ] || exit 97\n"
            "[ \"$GIT_CONFIG_VALUE_1\" = false ] || exit 97\n"
            "[ -f \"$GIT_CONFIG_GLOBAL\" ] || exit 97\n"
            "[ -x \"$GIT_ASKPASS\" ] || exit 97\n"
            "[ \"$GIT_ASKPASS\" = \"$SSH_ASKPASS\" ] || exit 97\n"
            "case \"$3\" in\n"
            "  *unavailable*) printf 'secret remote failure\\n' >&2; exit 128 ;;\n"
            "  *auth-required*) printf 'password for secret-user required\\n' >&2; exit 128 ;;\n"
            "  *malformed*) printf 'malformed\\n'; exit 0 ;;\n"
            "esac\n"
            f"printf 'ref: refs/heads/main\\tHEAD\\n{FAKE_COMMIT}\\tHEAD\\n'\n",
            encoding="ascii",
        )
        executable.chmod(0o700)
    return directory


def _run(
    command: list[str],
    *,
    cwd: Path,
    environment_updates: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "cp1252"
    environment.update(environment_updates or {})
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        encoding="utf-8",
        env=environment,
    )


def _run_result(
    command: list[str],
    *,
    cwd: Path,
    environment_updates: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "cp1252"
    environment.update(environment_updates or {})
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
        _run([str(kb), "add", "--help"], cwd=work)
        _run([str(kb), "doctor"], cwd=work)
        for command in ("init", "scan", "status", "lint", "migrate", "inbox", "process"):
            _run([str(kb), command, "--help"], cwd=work)
        for group in ("note", "relation", "source"):
            _run([str(kb), group, "--help"], cwd=work)
        snippet = _run_result([str(kb), "snippet", "--help"], cwd=work)
        assert snippet.returncode == 2

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
        for capture_input, capture_type in (
            ("10.1000/example", "paper"),
            ("0-306-40615-2", "book"),
            ("https://example.test/page", "web"),
        ):
            missing_capture_extra = _run_result(
                [*base, "add", capture_input, "--type", capture_type, "--json"],
                cwd=work,
            )
            assert missing_capture_extra.returncode == 5, missing_capture_extra.stderr
            assert json.loads(missing_capture_extra.stdout)["errors"] == [
                {
                    "code": "ADD_METADATA_UNAVAILABLE",
                    "message": "required capture metadata is unavailable",
                }
            ]

        fake_git = _fake_git(root)
        isolated_path = os.pathsep.join((str(fake_git), os.environ.get("PATH", "")))
        resolver_probe = _run_result(
            [
                str(python),
                "-c",
                (
                    "from knowlume.adapters.git_remote import GitRemoteResolver; "
                    "from knowlume.domain.capture import normalize_repository_url; "
                    "r=normalize_repository_url('https://github.com/acme/offline-project', "
                    "configured=True); print(GitRemoteResolver().resolve(r).commit)"
                ),
            ],
            cwd=work,
            environment_updates={"PATH": isolated_path},
        )
        assert resolver_probe.returncode == 0, (resolver_probe.stdout, resolver_probe.stderr)
        assert resolver_probe.stdout.strip() == FAKE_COMMIT
        for project in ("unavailable", "auth-required", "malformed"):
            failed_repository = _run_result(
                [
                    *base,
                    "add",
                    f"https://github.com/acme/{project}",
                    "--type",
                    "repo",
                    "--json",
                ],
                cwd=work,
                environment_updates={
                    "PATH": isolated_path,
                    "GIT_CONFIG_GLOBAL": "secret-global-path",
                    "GIT_ASKPASS": "secret-askpass-path",
                    "GCM_INTERACTIVE": "secret-setting",
                },
            )
            assert failed_repository.returncode == 5, (
                failed_repository.stdout,
                failed_repository.stderr,
            )
            assert json.loads(failed_repository.stdout)["errors"] == [
                {
                    "code": "ADD_METADATA_UNAVAILABLE",
                    "message": "required capture metadata is unavailable",
                }
            ]
            combined = (failed_repository.stdout + failed_repository.stderr).lower()
            assert "secret" not in combined and str(root).lower() not in combined
        repository_capture = _run_result(
            [
                *base,
                "add",
                "https://github.com/acme/offline-project",
                "--type",
                "repo",
                "--json",
            ],
            cwd=work,
            environment_updates={"PATH": isolated_path},
        )
        assert repository_capture.returncode == 0, (
            repository_capture.stdout,
            repository_capture.stderr,
        )
        repository_data = json.loads(repository_capture.stdout)["data"]
        assert repository_data["source_type"] == "oss"
        assert repository_data["canonical_identity"] == (
            f"repo:github.com/acme/offline-project@{FAKE_COMMIT}"
        )
        repository_id = repository_data["source_id"]
        _run(
            [*base, "note", "new", "--type", "literature", "--source", repository_id],
            cwd=work,
        )
        _run([*base, "scan"], cwd=work)
        repository_text = next((vault / "sources/oss").glob("*.md")).read_text(encoding="utf-8")
        assert str(root) not in repository_text
        assert "secret" not in repository_text.lower()
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
        _run(
            [
                str(python),
                "-c",
                (
                    "from knowlume.adapters.zotero_local import ZoteroLocalApi; "
                    "a=ZoteroLocalApi(); "
                    "assert callable(a.exact_candidates) and callable(a.web_snapshot) "
                    "and callable(a.primary_attachment)"
                ),
            ],
            cwd=work,
        )
        _run([str(kb), "source", "--help"], cwd=work)
        _run([*base, "source", "list", "--json"], cwd=work)
    print("installed command smoke through Phase 2B verified with core and Zotero profiles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
