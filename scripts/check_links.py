#!/usr/bin/env python3
"""Check local Markdown links and HTML href/src references without network I/O."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
HTML_LINK = re.compile(r"(?:href|src)=[\"']([^\"']+)[\"']", re.IGNORECASE)
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")


def heading_anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = HEADING.match(line)
        if not match:
            continue
        text = re.sub(r"<[^>]+>", "", match.group(1)).strip().lower()
        slug = re.sub(r"[^\w\- ]", "", text, flags=re.UNICODE)
        slug = re.sub(r"\s+", "-", slug).strip("-")
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        anchors.add(slug if count == 0 else f"{slug}-{count}")
    return anchors


def local_references(path: Path) -> list[tuple[int, str]]:
    references: list[tuple[int, str]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for regex in (MARKDOWN_LINK, HTML_LINK):
            references.extend((number, value.strip()) for value in regex.findall(line))
    return references


def failures() -> list[str]:
    problems: list[str] = []
    markdown_files = sorted(ROOT.rglob("*.md"))
    anchor_cache = {path: heading_anchors(path) for path in markdown_files}
    for source in markdown_files:
        for line, value in local_references(source):
            parsed = urlsplit(value)
            if parsed.scheme or parsed.netloc:
                continue
            raw_path = unquote(parsed.path)
            target = source if not raw_path else (source.parent / raw_path).resolve()
            try:
                target.relative_to(ROOT)
            except ValueError:
                problems.append(f"{source.relative_to(ROOT)}:{line}: link escapes repository: {value}")
                continue
            if raw_path and not target.exists():
                problems.append(f"{source.relative_to(ROOT)}:{line}: missing target: {value}")
                continue
            if parsed.fragment and target.suffix.lower() == ".md":
                anchors = anchor_cache.get(target)
                if anchors is None and target.exists():
                    anchors = heading_anchors(target)
                if parsed.fragment not in (anchors or set()):
                    problems.append(f"{source.relative_to(ROOT)}:{line}: missing anchor: {value}")
    return problems


def main() -> int:
    problems = failures()
    if problems:
        print("Local link check failed:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print("Local link check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
