#!/usr/bin/env python3
"""Verify documented HTTP contracts against a pinned Caura OSS checkout."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PINNED_SHA = "80a733e68260e179fcdebcb988486de56d6bc747"


def require(pattern: str, text: str, label: str, errors: list[str]) -> None:
    if not re.search(pattern, text, re.MULTILINE | re.DOTALL):
        errors.append(label)


def committed_text(oss: Path, path: str) -> str:
    return subprocess.run(
        ["git", "show", f"{PINNED_SHA}:{path}"],
        cwd=oss,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oss-root", type=Path, required=True)
    args = parser.parse_args(argv)
    oss = args.oss_root.resolve()
    errors: list[str] = []

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=oss, check=True, capture_output=True, text=True
    ).stdout.strip()
    if head != PINNED_SHA:
        errors.append(f"OSS checkout is {head}, expected {PINNED_SHA}")

    app = committed_text(oss, "core-api/src/core_api/app.py")
    fleet = committed_text(oss, "core-api/src/core_api/routes/fleet.py")
    memories = committed_text(oss, "core-api/src/core_api/routes/memories.py")
    schemas = committed_text(oss, "core-api/src/core_api/schemas.py")
    responses = committed_text(oss, "core-api/src/core_api/openapi_responses.py")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    smoke = (ROOT / "scripts/cross_agent_smoke.py").read_text(encoding="utf-8")

    require(r'app\.include_router\(fleet_router, prefix="/api/v1"\)', app, "fleet router prefix", errors)
    require(r'app\.include_router\(memories_router, prefix="/api/v1"\)', app, "memory router prefix", errors)
    require(r'@router\.post\(\s*"/fleet",\s*status_code=201', fleet, "POST /fleet 201", errors)
    require(r'class FleetCreateIn\(TenantScopedBody\):.*?fleet_id: str.*?display_name: str \| None.*?description: str \| None', fleet, "fleet body fields", errors)
    require(r'class FleetCreateResponse\(BaseModel\):\s+ok: bool\s+fleet_id: str\s+tenant_id: str', responses, "fleet response fields", errors)
    require(r'@router\.post\("/memories".*?status_code=201\)', memories, "POST /memories 201", errors)
    require(r'class MemoryCreate\(TenantScopedBody\):.*?fleet_id: str \| None.*?agent_id: str \| None.*?content: str.*?visibility: str \| None', schemas, "memory write fields", errors)
    require(r'@router\.post\("/recall"', memories, "POST /recall", errors)
    require(r'class RecallRequest\(SearchRequest\)', schemas, "RecallRequest", errors)
    require(r'class SearchRequest\(TenantScopedBody\):.*?fleet_ids: list\[str\] \| None.*?query: str.*?caller_agent_id: str \| None', schemas, "recall request fields", errors)
    require(r'class RecallResponse\(BaseModel\):\s+query: str\s+summary: str\s+memory_count: int\s+memories: list\[MemoryOut\]', responses, "recall response fields", errors)
    require(r'@router\.get\(\s*"/memories/\{memory_id\}/contradictions"', memories, "contradiction GET route", errors)
    require(r'async def get_contradictions\(.*?tenant_id: str = Query\(\.\.\.\)', memories, "contradiction tenant query", errors)
    for field in (
        "memory_id",
        "status",
        "superseded_by",
        "superseded_memories",
        "detection_status",
        "contradictions",
    ):
        require(rf'class MemoryContradictionsResponse\(BaseModel\):.*?^    {field}:', responses, f"contradiction response field {field}", errors)

    for path in (
        "/api/v1/fleet",
        "/api/v1/memories/{memory_id}/contradictions",
    ):
        if path not in readme:
            errors.append(f"README missing {path}")
    for path in ("/fleet", "/memories", "/recall"):
        if path not in smoke:
            errors.append(f"smoke script missing {path}")

    if errors:
        for error in errors:
            print(f"oss-contract: {error}", file=sys.stderr)
        return 1
    print(f"OSS contract check passed at {PINNED_SHA}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
