#!/usr/bin/env python3
"""Reject unreviewed uses of the legacy Caura product name.

Compatibility identifiers are permitted only on lines carrying an explicit
``legacy-name-ok:`` marker. Binary files are ignored, but their paths are still
checked so stale branded asset names cannot return unnoticed.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEGACY_NAME = "memclaw"  # legacy-name-ok: scanner's required search term
ALLOW_MARKER = "legacy-name-ok:"
PATH_ALLOWLIST = {
    "docs/images/memclaw-architecture-updated-flow.png": "historical inbound image URL",  # legacy-name-ok: retained historical asset path
    "docs/images/memclaw-long-run-fleet-demo.gif": "historical inbound demo URL",  # legacy-name-ok: retained historical asset path
    "docs/images/memclaw_longrun_fleet_hero.svg": "historical inbound hero URL",  # legacy-name-ok: retained historical asset path
    "skills/memclaw-research-fleet.md": "historical inbound skill URL",  # legacy-name-ok: retained compatibility document path
}


def repository_paths() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    paths = [ROOT / line for line in result.stdout.splitlines() if line]
    return [path for path in paths if path.exists()]


def violations() -> list[str]:
    failures: list[str] = []
    paths = repository_paths()
    relative_paths = {path.relative_to(ROOT).as_posix() for path in paths}
    for allowed, reason in PATH_ALLOWLIST.items():
        if not reason.strip():
            failures.append(f"{allowed}: allowlist reason is empty")
        if allowed not in relative_paths:
            failures.append(f"{allowed}: allowlisted path does not exist")
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        if LEGACY_NAME in relative.casefold():
            reason = PATH_ALLOWLIST.get(relative)
            if not reason:
                failures.append(f"{relative}: legacy name in path without explicit allowlist reason")
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if LEGACY_NAME in line.casefold() and ALLOW_MARKER not in line:
                failures.append(f"{relative}:{number}: unallowlisted legacy name")
    return failures


def main() -> int:
    failures = violations()
    if failures:
        print("Legacy-brand check failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        print(
            "Use current Caura naming, or add a same-line legacy-name-ok: marker "
            "with a concrete compatibility reason.",
            file=sys.stderr,
        )
        return 1
    print("Legacy-brand check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
