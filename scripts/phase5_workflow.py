"""Example local orchestration: explicit human decision, revision checks, no model transport."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any


class WorkflowFailure(Exception):
    def __init__(self, envelope: dict[str, Any]) -> None:
        super().__init__("local workflow stopped")
        self.envelope = envelope


def run_workflow(
    invoke: Callable[[list[str]], dict[str, Any]],
    *,
    query: str,
    scope: str,
    artifact_id: str,
    decision: str,
    reviewer: str,
    expected_checksum: str,
    note_id: str | None = None,
    section_id: str | None = None,
    actor: str | None = None,
    expected_note_checksum: str | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """Return the final command envelope; never choose a human decision or widen scope."""
    if scope not in {"trusted-local", "public-safe"} or decision not in {"accepted", "rejected"}:
        raise ValueError("explicit scope and human decision are required")
    if decision == "accepted" and not all((note_id, section_id, actor, expected_note_checksum)):
        raise ValueError(
            "accepted workflow requires an inspected Note and explicit promotion target"
        )
    if decision == "rejected" and apply:
        raise ValueError("a rejected candidate cannot be applied")

    def call(arguments: list[str]) -> dict[str, Any]:
        envelope = invoke([*arguments, "--json"])
        if not envelope["success"]:
            raise WorkflowFailure(envelope)
        return envelope

    call(["context", query, "--scope", scope])
    inspected = call(["get", artifact_id])["data"]
    if inspected["checksum"] != expected_checksum:
        raise ValueError(
            "Artifact changed: inspect the new revision and make a fresh human decision"
        )
    # A completed retry must not re-review an already promoted Artifact.
    already_promoted = inspected["object"].get("review_status") == "promoted"
    if already_promoted and decision != "accepted":
        raise ValueError("completed promotion cannot be rejected by this workflow")
    if not already_promoted:
        result = call(
            [
                "ai",
                "review",
                artifact_id,
                "--decision",
                decision,
                "--reviewer",
                reviewer,
                "--expect-checksum",
                expected_checksum,
            ]
        )
        if decision == "rejected":
            return result
    accepted = call(["get", artifact_id])["data"]
    assert note_id and section_id and actor and expected_note_checksum
    target = call(["get", note_id])["data"]
    if target["checksum"] != expected_note_checksum:
        raise ValueError("Note changed: inspect its current revision before promotion")
    arguments = [
        "ai",
        "promote",
        artifact_id,
        "--into",
        note_id,
        "--section",
        section_id,
        "--actor",
        actor,
        "--expect-artifact-checksum",
        accepted["checksum"],
        "--expect-note-checksum",
        expected_note_checksum,
    ]
    preview = call([*arguments, "--dry-run"])
    if not apply:
        return preview
    result = call([*arguments, "--apply"])
    persisted = call(["get", artifact_id])["data"]
    proof = persisted["object"].get("promotion", {})
    if (
        persisted["object"].get("review_status") != "promoted"
        or proof != result["data"]["promotion"]
        or (proof.get("note_id"), proof.get("section_id")) != (note_id, section_id)
        or proof.get("actor") != {"type": "human", "id": actor}
    ):
        raise ValueError("persisted promotion did not match the requested target")
    persisted_note = call(["get", note_id])["data"]
    sections = [
        section
        for section in persisted_note["body"]["sections"]
        if section["section_id"] == section_id
    ]
    if (
        persisted_note["checksum"] != proof["note_checksum"]
        or len(sections) != 1
        or sections[0]["role"] != "ai"
        or sections[0]["blocks"]
        != [{"kind": "ai", "text": persisted["body"], "artifact_id": artifact_id}]
        or not any(
            relation["from_id"] == note_id
            and relation["to_id"] == artifact_id
            and relation["relation_type"] == "promoted_from"
            and relation["actor"] == proof["actor"]
            and relation["created_at"] == proof["promoted_at"]
            for relation in persisted_note["relations"]["outgoing"]
        )
    ):
        raise ValueError("persisted Note or audit relation changed; inspect current state")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kb", default="kb", help="Installed kb executable")
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--scope", choices=("trusted-local", "public-safe"), required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--decision", choices=("accepted", "rejected"), required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--expect-checksum", required=True)
    parser.add_argument("--into")
    parser.add_argument("--section")
    parser.add_argument("--actor")
    parser.add_argument("--expect-note-checksum")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    environment = os.environ.copy()
    environment.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1")

    def invoke(arguments: list[str]) -> dict[str, Any]:
        process = subprocess.run(
            [args.kb, "--vault", str(args.vault), *arguments],
            capture_output=True,
            encoding="utf-8",
            env=environment,
            timeout=60,
        )
        envelope: dict[str, Any] = json.loads(process.stdout)
        if process.returncode != envelope["exit_code"]:
            raise ValueError("command exit did not match its envelope")
        return envelope

    try:
        result = run_workflow(
            invoke,
            query=args.query,
            scope=args.scope,
            artifact_id=args.artifact,
            decision=args.decision,
            reviewer=args.reviewer,
            expected_checksum=args.expect_checksum,
            note_id=args.into,
            section_id=args.section,
            actor=args.actor,
            expected_note_checksum=args.expect_note_checksum,
            apply=args.apply,
        )
    except WorkflowFailure as error:
        result = error.envelope
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        print(
            "Local workflow stopped; inspect results and current revisions before retrying.",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
