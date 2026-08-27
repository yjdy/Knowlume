from __future__ import annotations

import argparse
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
AUTHORITATIVE_ASSETS = [
    *sorted((ROOT / "schemas").rglob("*")),
    *sorted((ROOT / "templates" / "config").rglob("*")),
    *sorted((ROOT / "templates" / "v1").rglob("*")),
    *sorted((ROOT / "templates" / "v2").rglob("*")),
]
AUTHORITATIVE_ASSETS = [path for path in AUTHORITATIVE_ASSETS if path.is_file()]


def _wheel_asset_name(path: Path) -> str:
    if path.is_relative_to(ROOT / "schemas"):
        relative = path.relative_to(ROOT / "schemas")
        return f"knowlume/_assets/schemas/{relative.as_posix()}"
    relative = path.relative_to(ROOT / "templates")
    return f"knowlume/_assets/templates/{relative.as_posix()}"


def verify_wheel(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.name.endswith("-py3-none-any.whl"):
        errors.append(f"wheel is not platform independent: {path.name}")
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        for name in names:
            normalized = PurePosixPath(name)
            if normalized.is_absolute() or ".." in normalized.parts:
                errors.append(f"unsafe wheel member: {name}")
            if name.startswith(("tests/", "plan/", "fixtures/", "tmp/")):
                errors.append(f"forbidden wheel member: {name}")
        for source in AUTHORITATIVE_ASSETS:
            packaged_name = _wheel_asset_name(source)
            if packaged_name not in names:
                errors.append(f"missing packaged asset: {packaged_name}")
                continue
            if archive.read(packaged_name) != source.read_bytes():
                errors.append(f"packaged asset differs from authority: {packaged_name}")
    return errors


def verify_sdist(path: Path) -> list[str]:
    errors: list[str] = []
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        names = [PurePosixPath(member.name) for member in members]
        if any("tmp" in name.parts for name in names):
            errors.append("source distribution contains tmp data")
        if not any(
            "src" in name.parts
            and "knowlume" in name.parts
            and name.suffix == ".py"
            for name in names
        ):
            errors.append("source distribution has no src/knowlume package")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dist", type=Path)
    args = parser.parse_args()
    wheels = sorted(args.dist.glob("*.whl"))
    sdists = sorted(args.dist.glob("*.tar.gz"))
    errors: list[str] = []
    if len(wheels) != 1:
        errors.append(f"expected one wheel, found {len(wheels)}")
    else:
        errors.extend(verify_wheel(wheels[0]))
    if len(sdists) != 1:
        errors.append(f"expected one sdist, found {len(sdists)}")
    else:
        errors.extend(verify_sdist(sdists[0]))
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("distribution artifacts verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
