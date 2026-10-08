from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from test_phase5_contracts import validator
from typer.testing import CliRunner

import knowlume.cli as cli

ROOT = Path(__file__).resolve().parents[1]


def test_single_offline_demo_uses_registered_commands_and_existing_safe_boundaries(
    tmp_path: Path, monkeypatch: Any
) -> None:
    from phase4_support import projection
    from test_phase1_notes_cli import _template

    monkeypatch.setattr(cli, "read_asset_text", _template)
    monkeypatch.setattr(cli, "_projection", projection)
    spec = importlib.util.spec_from_file_location(
        "daily_demo", ROOT / "scripts/daily_workflow_demo.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    runner = CliRunner()
    operations = []

    def invoke(args: list[str], expected: int) -> str:
        operations.append(args)
        result = runner.invoke(cli.app, args)
        assert result.exit_code == expected, (args, result.stdout, result.stderr, result.exception)
        return result.stdout

    report = module.run_demo(tmp_path / "independent-vault", invoke=invoke)
    assert report["synthetic"] is True
    assert len(report["notes"]) == 4
    for data in report["notes"]:
        validator("note-create-result-v1.schema.json").validate(data)
    assert report["bilingual_search"] == "passed"
    assert report["ai_conflict"] == "VAULT_WRITE_CONFLICT"
    assert report["real_trial"] == "not_run"
    assert any("evolve" in args for args in operations)
