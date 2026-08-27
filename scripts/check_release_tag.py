from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tag")
    parser.add_argument("--target", choices=["testpypi", "pypi"])
    args = parser.parse_args()
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = config["project"]
    expected = f"v{project['version']}"
    if args.tag != expected:
        print(f"release tag {args.tag!r} does not match {expected!r}", file=sys.stderr)
        return 1
    if args.target is None:
        return 0
    gates = config["tool"]["knowlume"]["release"]
    if args.target == "testpypi":
        gate_name = "testpypi-enabled"
    else:
        prerelease = re.search(r"(?:a|b|rc|dev)\d", project["version"]) is not None
        gate_name = "pypi-prerelease-enabled" if prerelease else "pypi-stable-enabled"
    if not gates[gate_name]:
        print(f"release gate {gate_name!r} is closed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
