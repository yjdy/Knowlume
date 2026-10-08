"""Offline synthetic tutorial, shipped with source/sdist, never a model or Zotero run."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

SAMPLES = Path(__file__).resolve().parents[1] / "tests/fixtures/daily-workflow"
PAPER_A = "src_01JSTAG7N9Q3V5X8Y2Z4A6B8C0"
PAPER_B = "src_01JSTAG7N9Q3V5X8Y2Z4A6B8C4"
PROJECT = "src_01JSTAG7N9Q3V5X8Y2Z4A6B8C3"
ARTIFACT = "ai_01JSTAG7N9Q3V5X8Y2Z4A6B8E1"
type Invoke = Callable[[list[str], int], str]


def run_demo(vault: Path, *, invoke: Invoke) -> dict[str, Any]:
    """Only create a brand-new tutorial Vault; all authored content is labelled synthetic."""
    if vault.exists():
        raise ValueError("demo requires a new, nonexistent vault directory")
    invoke(["init", str(vault)], 0)
    for name in ("paper-a.md", "paper-b.md", "project.md"):
        folder = "oss" if name == "project.md" else "papers"
        shutil.copyfile(SAMPLES / "sources" / name, vault / "sources" / folder / name)
    base = ["--vault", str(vault)]

    def command(*args: str, code: int = 0) -> dict[str, Any]:
        document: dict[str, Any] = json.loads(invoke([*base, *args, "--json"], code))
        assert document["exit_code"] == code and document["success"] is (code == 0), document
        return document

    notes = []
    for kind, title, source in (
        ("literature", "演示：论文 A 阅读", PAPER_A),
        ("literature", "演示：论文 B 阅读", PAPER_B),
        ("idea", "演示：知识回顾想法", None),
        ("synthesis", "演示：跨来源综合", None),
    ):
        args = ["note", "new", "--type", kind, "--title", title]
        if source:
            args += ["--source", source]
        data = command(*args)["data"]
        notes.append(data)
        path = vault / data["path"]
        path.write_text(
            path.read_text(encoding="utf-8")
            + "\n演示 human 文本（非用户观点）：知识积累需要定期回顾。Knowledge review demo.\n",
            encoding="utf-8",
        )
        if source:
            with path.open("a", encoding="utf-8") as stream:
                stream.write(
                    "\n<!-- knowlume:section id=sec_demo_facts role=fact -->\n"
                    "## 合成来源事实演示\n\n<!-- knowlume:fact\ncitations:\n"
                    f"  - source_id: {source}\n"
                    "    locator:\n      locator_version: 2\n      source_type: paper\n"
                    '      page: 1\n      section: "demo"\n-->\n'
                    "演示 fact 文本（非真实论文结论）：合成资料展示知识回顾。\n"
                )
    first, second, idea, synthesis = (data["object_id"] for data in notes)
    invoke([*base, "note", "evolve", idea, "--to", "concept"], 0)
    for target in (first, second):
        invoke([*base, "relation", "add", synthesis, target, "--type", "synthesizes"], 0)
    invoke([*base, "relation", "add", idea, PROJECT, "--type", "cites"], 0)
    invoke(
        [
            *base,
            "relation",
            "add",
            second,
            first,
            "--type",
            "supports",
            "--section",
            "sec_demo_facts",
        ],
        0,
    )
    for source in (PAPER_A, PAPER_B):
        command("process", source, "--to", "reading")
    invoke([*base, "lint"], 0)
    command("index", "build")
    for query in ("知识", "Knowledge"):
        result = command("search", query)["data"]
        assert result["count"] > 0 and any(hit["section_id"] for hit in result["hits"])
    command("context", "知识", "--scope", "trusted-local")
    command("grep", "知识")
    command("get", first)

    shutil.copyfile(SAMPLES / "artifact.md", vault / "ai/artifacts/demo.md")
    inspected = command("get", ARTIFACT)["data"]["checksum"]
    command("ai", "list")
    command(
        "ai",
        "review",
        ARTIFACT,
        "--decision",
        "accepted",
        "--reviewer",
        "demo-human",
        "--expect-checksum",
        inspected,
    )
    accepted = command("get", ARTIFACT)["data"]["checksum"]
    inspected_note = command("get", idea)["data"]["checksum"]
    promotion = [
        "ai",
        "promote",
        ARTIFACT,
        "--into",
        idea,
        "--section",
        "sec_demo_ai",
        "--actor",
        "demo-human",
        "--expect-artifact-checksum",
        accepted,
        "--expect-note-checksum",
        inspected_note,
    ]
    command(*promotion, "--dry-run")
    idea_path = vault / notes[2]["path"]
    with idea_path.open("a", encoding="utf-8") as stream:
        stream.write("\n演示 human 文本：模拟预览之后编辑，要求过期校验值被拒绝。\n")
    before = {p.relative_to(vault): p.read_bytes() for p in vault.rglob("*") if p.is_file()}
    conflict = command(*promotion, "--apply", code=4)
    assert conflict["errors"][0]["code"] == "VAULT_WRITE_CONFLICT", conflict
    assert before == {p.relative_to(vault): p.read_bytes() for p in vault.rglob("*") if p.is_file()}
    stale = command("search", "Knowledge", code=4)
    assert stale["errors"][0]["code"] == "INDEX_SOURCE_CHANGED"
    invoke([*base, "lint"], 0)
    command("index", "build")
    command("search", "知识")
    return {
        "synthetic": True,
        "notes": notes,
        "bilingual_search": "passed",
        "ai_conflict": "VAULT_WRITE_CONFLICT",
        "real_trial": "not_run",
        "section_url": f"/notes/{first}#sec_demo_facts",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path, required=True, help="New synthetic test vault only")
    parser.add_argument("--kb", default="kb", help="Installed kb executable")
    args = parser.parse_args()

    def invoke(arguments: list[str], expected: int) -> str:
        result = subprocess.run([args.kb, *arguments], capture_output=True, encoding="utf-8")
        if result.returncode != expected:
            raise RuntimeError(f"tutorial step failed: {result.stdout}{result.stderr}")
        return result.stdout

    report = run_demo(args.vault.resolve(), invoke=invoke)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
