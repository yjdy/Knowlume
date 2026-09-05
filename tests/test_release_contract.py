from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

from phase0_support import ROOT


def test_python_distribution_metadata_is_frozen() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = config["project"]
    assert project["name"] == "knowlume"
    assert project["requires-python"] == ">=3.13,<3.15"
    assert project["scripts"] == {"kb": "knowlume.cli:app"}
    assert set(project["optional-dependencies"]) == {"web", "zotero", "all"}
    assert project["optional-dependencies"]["zotero"] == ["httpx>=0.28.1,<1"]
    assert "httpx>=0.28.1,<1" in project["optional-dependencies"]["all"]
    assert "markdown-it-py>=4.2,<5" in project["optional-dependencies"]["web"]
    assert "markdown-it-py>=4.2,<5" in project["optional-dependencies"]["all"]
    assert not {
        "fastapi>=0.115",
        "httpx>=0.28.1,<1",
        "jinja2>=3.1",
        "uvicorn[standard]>=0.34",
    } & set(project["dependencies"])

    wheel = config["tool"]["hatch"]["build"]["targets"]["wheel"]
    assert wheel["packages"] == ["src/knowlume"]
    assert wheel["force-include"] == {
        "schemas": "knowlume/_assets/schemas",
        "templates/config": "knowlume/_assets/templates/config",
        "templates/v1": "knowlume/_assets/templates/v1",
        "templates/v2": "knowlume/_assets/templates/v2",
        "templates/web": "knowlume/_assets/templates/web",
    }
    assert config["tool"]["knowlume"]["release"] == {
        "testpypi-enabled": True,
        "pypi-prerelease-enabled": True,
        "pypi-stable-enabled": False,
    }
    assert config["tool"]["uv"]["index"] == [{"url": "https://pypi.org/simple", "default": True}]


def test_lockfile_uses_the_portable_public_package_index() -> None:
    lockfile = (ROOT / "uv.lock").read_text(encoding="utf-8")
    registries = {
        line.strip()
        for line in lockfile.splitlines()
        if line.strip().startswith("source = { registry = ")
    }
    assert registries == {'source = { registry = "https://pypi.org/simple" }'}


def test_release_workflows_cover_required_trust_and_platform_gates() -> None:
    workflow_root = ROOT / ".github" / "workflows"
    assert {
        "ci.yml",
        "package-smoke.yml",
        "release.yml",
    } <= {path.name for path in workflow_root.glob("*.yml")}
    ci = (workflow_root / "ci.yml").read_text(encoding="utf-8")
    smoke = (workflow_root / "package-smoke.yml").read_text(encoding="utf-8")
    release = (workflow_root / "release.yml").read_text(encoding="utf-8")
    for document in (ci, smoke, release):
        target_systems = ("ubuntu-latest", "windows-latest", "macos-latest")
        assert all(os_name in document for os_name in target_systems)
        assert '"3.13"' in document
        assert '"3.14"' in document
    assert "pypa/gh-action-pypi-publish" in release
    assert "id-token: write" in release
    assert "actions/attest-build-provenance" in release
    assert "scripts/verify_distribution.py" in ci
    assert "uv tool run" in smoke
    assert "pipx" in smoke
    assert "actions/setup-python@v6" in smoke
    assert "python-version: ${{ matrix.python }}" in smoke
    assert "scripts/verify_installed_phase1.py" in smoke
    assert "scripts/verify_installed_phase3.py" in smoke
    assert "scripts/verify_installed_phase4.py" in smoke
    assert "scripts/verify_install_lifecycle.py" in smoke
    assert "scripts/release_plan.py" in release
    assert "if: needs.release-plan.outputs.testpypi == 'true'" in release
    assert "if: needs.release-plan.outputs.pypi == 'true'" in release
    assert "needs.release-plan.outputs.github_release == 'true'" in release


def test_release_plan_skips_formal_publication_for_testpypi_only(tmp_path: Path) -> None:
    source = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    config = tmp_path / "phase1.toml"
    config.write_text(
        source.replace("pypi-prerelease-enabled = true", "pypi-prerelease-enabled = false")
    )
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/release_plan.py"),
            "--config",
            str(config),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.splitlines() == [
        "testpypi=true",
        "pypi=false",
        "github_release=false",
    ]


def test_phase3_prerelease_plan_opens_testpypi_and_pypi(tmp_path: Path) -> None:
    source = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    config = tmp_path / "phase3.toml"
    config.write_text(source.replace('version = "0.1.0"', 'version = "0.1.0rc1"'))
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/release_plan.py"),
            "--config",
            str(config),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.splitlines() == [
        "testpypi=true",
        "pypi=true",
        "github_release=true",
    ]


def test_release_tag_and_phase_gates_fail_closed() -> None:
    script = ROOT / "scripts" / "check_release_tag.py"
    valid_tag = subprocess.run(
        [sys.executable, str(script), "v0.1.0"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert valid_tag.returncode == 0

    open_testpypi_gate = subprocess.run(
        [sys.executable, str(script), "v0.1.0", "--target", "testpypi"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert open_testpypi_gate.returncode == 0

    closed_stable_gate = subprocess.run(
        [sys.executable, str(script), "v0.1.0", "--target", "pypi"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert closed_stable_gate.returncode == 1
    assert "release gate 'pypi-stable-enabled' is closed" in closed_stable_gate.stderr

    wrong_tag = subprocess.run(
        [sys.executable, str(script), "v9.9.9"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert wrong_tag.returncode == 1
