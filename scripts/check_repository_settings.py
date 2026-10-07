#!/usr/bin/env python3
"""Validate the human-only GitHub settings handoff file."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = ROOT / ".github" / "repository-settings-checklist.json"
REQUIRED_IDS = {"description", "topics", "social-preview"}
REQUIRED_TOPICS = {"agent-memory", "ai-agents", "caura", "multi-agent-systems"}


def main() -> int:
    data = json.loads(CHECKLIST.read_text(encoding="utf-8"))
    errors: list[str] = []
    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if data.get("automation") != "human-only":
        errors.append("automation must remain human-only")
    if data.get("repository") != "caura-ai/caura-long-run-fleet":
        errors.append("repository must be caura-ai/caura-long-run-fleet")
    items = {item.get("id"): item for item in data.get("items", [])}
    if set(items) != REQUIRED_IDS:
        errors.append(f"items must be exactly {sorted(REQUIRED_IDS)}")
    for item in items.values():
        if item.get("status") not in {"pending", "verified"}:
            errors.append(f"{item.get('id')}: status must be pending or verified")
        if not item.get("verify"):
            errors.append(f"{item.get('id')}: verify instruction is required")
    description = items.get("description", {}).get("expected", "")
    if len(description) > 350:
        errors.append("description exceeds GitHub's 350-character limit")
    if not all(term in description.casefold() for term in ("caura", "multi-agent", "memory")):
        errors.append("description must identify Caura, multi-agent use, and memory")
    topics = set(items.get("topics", {}).get("expected", []))
    if not REQUIRED_TOPICS.issubset(topics):
        errors.append(f"topics missing {sorted(REQUIRED_TOPICS - topics)}")
    preview = items.get("social-preview", {}).get("source", "")
    if not preview or not (ROOT / preview).is_file():
        errors.append("social-preview source must exist")
    if errors:
        for error in errors:
            print(f"repository-settings: {error}", file=sys.stderr)
        return 1
    print("Repository-settings checklist passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
