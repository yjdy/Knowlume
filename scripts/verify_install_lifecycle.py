from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _snapshot(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _run(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    current_wheel = args.wheel.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="knowlume-lifecycle-") as temporary:
        root = Path(temporary)
        source = root / "older-source"
        source.mkdir()
        for name in ("src", "schemas", "templates"):
            shutil.copytree(ROOT / name, source / name)
        for name in ("README.md", "LICENSE", "pyproject.toml"):
            shutil.copyfile(ROOT / name, source / name)
        project = (source / "pyproject.toml").read_text(encoding="utf-8")
        project = project.replace('version = "0.1.0"', 'version = "0.0.9"', 1)
        (source / "pyproject.toml").write_text(project, encoding="utf-8")
        older_dist = root / "older-dist"
        _run(["uv", "build", "--wheel", "--out-dir", str(older_dist)], source)
        older_wheel = next(older_dist.glob("*.whl"))

        environment = root / "environment"
        _run(["uv", "venv", "--python", sys.executable, str(environment)], root)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        vault = root / "independent-vault"
        vault.mkdir()
        (vault / "durable.md").write_text("stable knowledge\n", encoding="utf-8")
        before = _snapshot(vault)
        operations = (
            ["uv", "pip", "install", "--no-deps", "--python", str(python), str(older_wheel)],
            [
                "uv",
                "pip",
                "install",
                "--no-deps",
                "--upgrade",
                "--python",
                str(python),
                str(current_wheel),
            ],
            [
                "uv",
                "pip",
                "install",
                "--no-deps",
                "--force-reinstall",
                "--python",
                str(python),
                str(older_wheel),
            ],
            ["uv", "pip", "uninstall", "--python", str(python), "knowlume"],
        )
        for operation in operations:
            _run(operation, root)
            if _snapshot(vault) != before:
                raise RuntimeError("package lifecycle operation modified the independent Vault")
    print("install, upgrade, downgrade, and uninstall preserved the Vault")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
