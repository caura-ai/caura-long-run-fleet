#!/usr/bin/env python3
"""Local-only cross-agent Caura smoke test; dry-run unless explicitly enabled."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from simulate import read_compatible_env  # noqa: E402


def request_plan(api_url: str, tenant_id: str, fleet_id: str, auth_enabled: bool) -> list[str]:
    return [
        f"auth: {'verify wrong-key rejection' if auth_enabled else 'skip (keyless local server)'}",
        f"create: POST {api_url}/fleet tenant={tenant_id} fleet={fleet_id}",
        f"confirm: GET {api_url}/fleet?tenant_id={tenant_id}",
        f"agent-a: POST {api_url}/memories with one unique shared fact",
        f"agent-b: POST {api_url}/recall scoped to fleet {fleet_id}",
        "assert: Agent B's response contains Agent A's memory id or unique marker",
    ]


def ensure_local_url(api_url: str) -> None:
    parsed = urlsplit(api_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("CAURA_API_URL must use http or https")
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("live smoke execution is restricted to a loopback Caura deployment")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Perform local HTTP requests")
    parser.add_argument("--fleet-id", default=f"smoke-{uuid.uuid4().hex[:12]}")
    args = parser.parse_args(argv)

    api_url = read_compatible_env(  # legacy-name-ok: supported non-empty env fallback
        "CAURA_API_URL", "MEMCLAW_API_URL", "http://127.0.0.1:8000/api/v1"  # legacy-name-ok: supported non-empty env fallback
    ).rstrip("/")
    api_key = read_compatible_env(  # legacy-name-ok: supported non-empty env fallback
        "CAURA_API_KEY", "MEMCLAW_API_KEY"  # legacy-name-ok: supported non-empty env fallback
    )
    tenant_id = read_compatible_env(  # legacy-name-ok: supported non-empty env fallback
        "CAURA_TENANT_ID", "MEMCLAW_TENANT_ID", "default"  # legacy-name-ok: supported non-empty env fallback
    )
    plan = request_plan(api_url, tenant_id, args.fleet_id, bool(api_key))
    print("Caura cross-agent smoke plan:")
    for step in plan:
        print(f"- {step}")

    if not args.execute:
        print("Dry run only. No network requests were made.")
        return 0
    if os.environ.get("CAURA_SMOKE_ALLOW_NETWORK") != "true":
        print("Refusing network access: set CAURA_SMOKE_ALLOW_NETWORK=true with --execute.", file=sys.stderr)
        return 2
    try:
        ensure_local_url(api_url)
    except ValueError as exc:
        print(f"Refusing network access: {exc}", file=sys.stderr)
        return 2

    import requests

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
        rejected = requests.get(
            f"{api_url}/fleet",
            headers={"X-API-Key": "caura-intentionally-wrong-smoke-key"},
            params={"tenant_id": tenant_id},
            timeout=10,
        )
        if rejected.status_code not in {401, 403}:
            raise RuntimeError(f"wrong API key returned HTTP {rejected.status_code}, expected 401/403")

    create = requests.post(
        f"{api_url}/fleet",
        headers=headers,
        json={
            "tenant_id": tenant_id,
            "fleet_id": args.fleet_id,
            "display_name": "Cross-Agent Smoke Fleet",
        },
        timeout=30,
    )
    if create.status_code not in {201, 409}:
        raise RuntimeError(f"fleet create failed: HTTP {create.status_code} {create.text[:300]}")

    fleets = requests.get(
        f"{api_url}/fleet",
        headers=headers,
        params={"tenant_id": tenant_id},
        timeout=30,
    )
    fleets.raise_for_status()
    if args.fleet_id not in {row.get("fleet_id") for row in fleets.json()}:
        raise RuntimeError("created fleet was not returned by GET /fleet")

    marker = f"caura-cross-agent-smoke-{uuid.uuid4().hex}"
    write = requests.post(
        f"{api_url}/memories",
        headers=headers,
        json={
            "tenant_id": tenant_id,
            "fleet_id": args.fleet_id,
            "agent_id": "smoke-agent-a",
            "content": f"Agent A wrote the unique verification marker {marker}.",
            "memory_type": "fact",
            "visibility": "scope_team",
            "write_mode": "fast",
        },
        timeout=60,
    )
    write.raise_for_status()
    memory_id = str(write.json().get("id") or "")
    if not memory_id:
        raise RuntimeError(f"memory write returned no id: {json.dumps(write.json())[:300]}")

    recall = requests.post(
        f"{api_url}/recall",
        headers=headers,
        json={
            "tenant_id": tenant_id,
            "fleet_ids": [args.fleet_id],
            "query": marker,
            "caller_agent_id": "smoke-agent-b",
            "top_k": 5,
            "items_alias": False,
        },
        timeout=90,
    )
    recall.raise_for_status()
    memories = recall.json().get("memories", [])
    if not any(str(row.get("id")) == memory_id or marker in row.get("content", "") for row in memories):
        raise RuntimeError("Agent B recall did not contain Agent A's memory")

    print(f"PASS: Agent B recalled Agent A memory {memory_id} in fleet {args.fleet_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
