#!/usr/bin/env python3
"""Validate an OpenClaw config and launch a command with canonical Caura env.

The launcher never writes secrets into JSON. It reads a local dotenv file,
resolves current names before supported non-empty aliases, exports only the
canonical names to the child process, and then uses an argv list (no shell).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Mapping


ROOT = Path(__file__).resolve().parents[1]
ALIASES = (
    ("CAURA_API_URL", "MEMCLAW_API_URL"),  # legacy-name-ok: supported non-empty env fallback
    ("CAURA_API_KEY", "MEMCLAW_API_KEY"),  # legacy-name-ok: supported non-empty env fallback
    ("CAURA_TENANT_ID", "MEMCLAW_TENANT_ID"),  # legacy-name-ok: supported non-empty env fallback
    ("CAURA_FLEET_ID", "MEMCLAW_FLEET_ID"),  # legacy-name-ok: supported non-empty env fallback
)
PASSTHROUGH_FROM_FILE = ("LLM_GATEWAY_API_KEY", "OPENCLAW_GATEWAY_URL")


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def resolve_child_env(
    process_env: Mapping[str, str], file_env: Mapping[str, str]
) -> tuple[dict[str, str], dict[str, str]]:
    child = dict(process_env)
    sources: dict[str, str] = {}
    for current, legacy in ALIASES:
        candidates = (
            (process_env.get(current), f"process:{current}"),
            (file_env.get(current), f"file:{current}"),
            (process_env.get(legacy), f"process:{legacy}"),
            (file_env.get(legacy), f"file:{legacy}"),
        )
        for value, source in candidates:
            if value:
                child[current] = value
                sources[current] = source
                break
        else:
            child.pop(current, None)
            sources[current] = "unset"
        child.pop(legacy, None)
    for name in PASSTHROUGH_FROM_FILE:
        if not child.get(name) and file_env.get(name):
            child[name] = file_env[name]
            sources[name] = f"file:{name}"
        elif child.get(name):
            sources[name] = f"process:{name}"
        else:
            sources[name] = "unset"
    return child, sources


def validate_config(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    servers = data.get("mcp_servers", [])
    if servers:
        caura = next((server for server in servers if server.get("name") == "caura"), None)
        if caura is None:
            raise ValueError("OpenClaw config has MCP servers but no server named 'caura'")
        if caura.get("headers", {}).get("X-API-Key") != "${CAURA_API_KEY}":
            raise ValueError("Caura MCP server must reference ${CAURA_API_KEY}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--config", type=Path, default=ROOT / "openclaw.json")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    validate_config(args.config.expanduser())
    child_env, sources = resolve_child_env(os.environ, parse_env_file(args.env_file))

    if args.check:
        for name in (*[current for current, _ in ALIASES], *PASSTHROUGH_FROM_FILE):
            state = "set" if child_env.get(name) else "unset"
            print(f"{name}: {state} ({sources[name]})")
        return 0

    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("provide --check or a command after --")
    return subprocess.run(command, env=child_env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
