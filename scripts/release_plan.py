from __future__ import annotations

import argparse
import re
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def release_plan(config: dict[str, Any]) -> dict[str, bool]:
    version = str(config["project"]["version"])
    gates = config["tool"]["knowlume"]["release"]
    prerelease = re.search(r"(?:a|b|rc|dev)\d", version) is not None
    pypi_key = "pypi-prerelease-enabled" if prerelease else "pypi-stable-enabled"
    testpypi = bool(gates["testpypi-enabled"])
    pypi = bool(gates[pypi_key])
    if pypi and not testpypi:
        raise ValueError("PyPI gate cannot open before the TestPyPI gate")
    return {"testpypi": testpypi, "pypi": pypi, "github_release": pypi}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "pyproject.toml")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    config = tomllib.loads(args.config.read_text(encoding="utf-8"))
    plan = release_plan(config)
    lines = [f"{key}={str(value).lower()}" for key, value in plan.items()]
    rendered = "\n".join(lines) + "\n"
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as stream:
            stream.write(rendered)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
