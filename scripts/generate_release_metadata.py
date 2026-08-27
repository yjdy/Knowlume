from __future__ import annotations

import argparse
import hashlib
import json
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _component(package: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "library",
        "name": package["name"],
        "version": package["version"],
        "purl": f"pkg:pypi/{package['name']}@{package['version']}",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dist", type=Path)
    args = parser.parse_args()
    artifacts = sorted(
        path
        for path in args.dist.iterdir()
        if path.suffix == ".whl" or path.name.endswith(".tar.gz")
    )
    checksums = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
        for path in artifacts
    ]
    (args.dist / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8")

    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    components = sorted(
        (_component(package) for package in lock.get("package", [])),
        key=lambda component: (component["name"], component["version"]),
    )
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "components": components,
    }
    (args.dist / "sbom.cdx.json").write_text(
        json.dumps(sbom, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
