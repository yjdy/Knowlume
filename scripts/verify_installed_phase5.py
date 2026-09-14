"""Verify Phase 5 with the built core wheel, outside the source checkout and offline."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ID = "ai_01JSTAG7N9Q3V5X8Y2Z4A6B8E1"
NOTE_ID = "note_01JSTAG7N9Q3V5X8Y2Z4A6B8D0"


def run(command: list[str], work: Path, *, code: int = 0) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    result = subprocess.run(
        command, cwd=work, env=environment, capture_output=True, encoding="utf-8", timeout=180
    )
    if result.returncode != code:
        raise RuntimeError(
            f"installed smoke failed ({result.returncode} != {code}): "
            f"{result.stdout!r} {result.stderr!r}"
        )
    return result


def read_json(command: list[str], work: Path, *, code: int = 0) -> dict[str, Any]:
    process = run(command, work, code=code)
    document: dict[str, Any] = json.loads(process.stdout)
    assert document["exit_code"] == code and document["success"] == (code == 0)
    assert not process.stderr
    return document


def snapshot(vault: Path) -> tuple[dict[str, bytes], set[str]]:
    paths = list(vault.rglob("*"))
    return (
        {p.relative_to(vault).as_posix(): p.read_bytes() for p in paths if p.is_file()},
        {p.relative_to(vault).as_posix() for p in paths},
    )


LEGACY_PROBE = """
import sys
from dataclasses import replace
from pathlib import Path
from knowlume.adapters.contract_v2 import parse_object_document, render_object_document
from knowlume.adapters.filesystem import load_vault
from knowlume.application.ai import AIService
from knowlume.domain.values import ReviewStatus
vault = load_vault(Path(sys.argv[1]))
path = vault.root / 'ai/artifacts/candidate.md'
original = path.read_bytes()
document = parse_object_document(original.decode('utf-8'))
try:
    for status in (ReviewStatus.ACCEPTED, ReviewStatus.REJECTED, ReviewStatus.PROMOTED):
        obj = replace(document.object, review_status=status, promotion=None, review_evidence=None)
        path.write_text(render_object_document(replace(document, object=obj)), encoding='utf-8')
        queue = AIService().list(vault, review_status='all')
        assert queue['total'] == 1
        assert queue['items'][0]['evidence_version'] is None
        assert queue['items'][0]['review_status'] == status.value
finally:
    path.write_bytes(original)
"""

OPTIONAL_PROBE = """
import importlib.util
from knowlume.adapters.zotero_local import ZoteroLocalApi
from knowlume.application.diagnostics import diagnostic_report
from knowlume.doctor import doctor_report
assert importlib.util.find_spec('httpx') is not None
assert importlib.util.find_spec('fastapi') is None
calls = []
class OfflineApi(ZoteroLocalApi):
    def _request(self, path, *, binary=False):
        assert not binary, 'attachment access was not authorized'
        calls.append(path)
        return [{'key': 'SYNTH001', 'data': {'title': 'Synthetic metadata'}}]
api = OfflineApi()
class OfflineProbes:
    def probe(self, name):
        assert name == 'zotero'
        api.probe()
report, code = diagnostic_report(('zotero',), runner=OfflineProbes(), installation=doctor_report)
assert code == 0, report
assert calls == ['users/0/items?limit=1'], calls
assert report['checks'][-1]['status'] == 'passed'
assert 'Synthetic metadata' not in str(report)
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    wheel = parser.parse_args().wheel.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="knowlume-phase5-installed-") as temporary:
        root = Path(temporary)
        work = root / "outside-source-checkout"
        work.mkdir()
        environment = root / "core"
        run(["uv", "venv", "--python", sys.executable, str(environment)], work)
        scripts = environment / ("Scripts" if os.name == "nt" else "bin")
        python = scripts / ("python.exe" if os.name == "nt" else "python")
        kb = scripts / ("kb.exe" if os.name == "nt" else "kb")
        run(["uv", "pip", "install", "--python", str(python), str(wheel)], work)
        run(
            [
                str(python),
                "-c",
                "import importlib.util; "
                "from knowlume.resources import read_asset_text as read_text; "
                "assert importlib.util.find_spec('httpx') is None; "
                "assert importlib.util.find_spec('fastapi') is None; "
                "assert 'review_status: unreviewed' in read_text('templates/v2/ai-artifact.md'); "
                "assert 'result_version' in "
                "read_text('schemas/interfaces/ai-list-result-v1.schema.json')",
            ],
            work,
        )
        for command in ("list", "review", "promote"):
            run([str(kb), "ai", command, "--help"], work)
        assert read_json([str(kb), "doctor", "--json"], work)["data"]["report_version"] == 1
        absent = read_json([str(kb), "doctor", "--probe", "zotero", "--json"], work, code=5)
        assert absent["data"]["checks"][-1]["status"] == "unavailable"
        usage = read_json([str(kb), "ai", "review", "--json"], work, code=2)
        assert usage["errors"][0]["code"] == "AI_ARGUMENT_INVALID"
        vault = root / "vault"
        run([str(kb), "init", str(vault)], work)
        for source, target in (
            ("unreviewed-ai-artifact.md", "ai/artifacts/candidate.md"),
            ("idea-note.md", "notes/ideas/idea.md"),
        ):
            shutil.copyfile(ROOT / "tests/fixtures/v2/valid" / source, vault / target)
        base = [str(kb), "--vault", str(vault)]

        def call(*arguments: str, code: int = 0) -> dict[str, Any]:
            return read_json([*base, *arguments, "--json"], work, code=code)

        before = snapshot(vault)
        assert call("ai", "list")["data"]["total"] == 1
        assert call("doctor", "--probe", "vault")["data"]["healthy"]
        assert call("doctor", "--probe", "sqlite", code=5)["errors"][0]["code"] == "INDEX_NOT_FOUND"
        assert snapshot(vault) == before
        artifact = call("get", ARTIFACT_ID)["data"]
        note = call("get", NOTE_ID)["data"]
        call(
            "ai",
            "review",
            ARTIFACT_ID,
            "--decision",
            "accepted",
            "--reviewer",
            "smoke-reviewer",
            "--expect-checksum",
            artifact["checksum"],
        )
        accepted = call("get", ARTIFACT_ID)["data"]
        run([str(python), "-c", LEGACY_PROBE, str(vault)], work)
        arguments = (
            "ai",
            "promote",
            ARTIFACT_ID,
            "--into",
            NOTE_ID,
            "--section",
            "sec_smoke_ai",
            "--actor",
            "smoke-promoter",
            "--expect-artifact-checksum",
            accepted["checksum"],
            "--expect-note-checksum",
            note["checksum"],
        )
        before = snapshot(vault)
        assert not call(*arguments)["data"]["changed"]
        assert snapshot(vault) == before
        assert call(*arguments, "--apply")["data"]["changed"]
        assert call("get", ARTIFACT_ID)["data"]["object"]["promotion"]["note_id"] == NOTE_ID
        assert not (vault / ".knowlume/kb.sqlite").exists()
        # Re-read revisions after success; retry remains independent of SQLite and transaction logs.
        current = call("get", ARTIFACT_ID)["data"]
        target = call("get", NOTE_ID)["data"]
        retry = (
            "ai",
            "promote",
            ARTIFACT_ID,
            "--into",
            NOTE_ID,
            "--section",
            "sec_smoke_ai",
            "--actor",
            "smoke-promoter",
            "--expect-artifact-checksum",
            current["checksum"],
            "--expect-note-checksum",
            target["checksum"],
            "--apply",
        )
        before = snapshot(vault)
        assert call(*retry)["data"]["already_promoted"]
        assert snapshot(vault) == before
        call(*arguments, "--apply", code=4)
        call("index", "rebuild")
        assert call("doctor", "--probe", "vault", "--probe", "sqlite")["data"]["healthy"]
        assert call("search", "candidate")["data"]["count"] == 0
        assert not any(
            call("context", "candidate", "--scope", "trusted-local")["data"]["groups"].values()
        )
        # Exercise the example through installed processes, including completed retry.
        example = read_json(
            [
                str(python),
                str(ROOT / "scripts/phase5_workflow.py"),
                "--kb",
                str(kb),
                "--vault",
                str(vault),
                "--query",
                "Knowledge",
                "--scope",
                "trusted-local",
                "--artifact",
                ARTIFACT_ID,
                "--decision",
                "accepted",
                "--reviewer",
                "smoke-reviewer",
                "--expect-checksum",
                current["checksum"],
                "--into",
                NOTE_ID,
                "--section",
                "sec_smoke_ai",
                "--actor",
                "smoke-promoter",
                "--expect-note-checksum",
                target["checksum"],
                "--apply",
            ],
            work,
        )
        assert example["data"]["already_promoted"]
        before = snapshot(vault)
        run(["uv", "pip", "install", "--python", str(python), f"{wheel}[zotero]"], work)
        run([str(python), "-c", OPTIONAL_PROBE], work)
        assert snapshot(vault) == before
    print("installed Phase 5 core/optional workflows and read-only probes verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
