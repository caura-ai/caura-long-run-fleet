"""
14-day fleet simulation runner for the Caura Long-Run Research Fleet.

Each simulated day:
  1. Sourcing Agent and Verification Agent run concurrently (threads)
  2. Synthesis Agent runs after both complete
  3. On Day 9: Sourcing Agent writes the $349 drift. The crystallizer only
     dedups near-duplicate memories to `archived` -- it never marks anything
     `outdated`. The $299 -> `outdated` transition is done by Caura's async
     contradiction detector, so after Sourcing + Verification finish we poll
     GET /memories/{memory_id}/contradictions until detection_status is
     "completed" before letting Synthesis run.

Usage:
    python simulate.py                 # run all 14 days
    python simulate.py --start 9       # resume from Day 9
    python simulate.py --days 1 9 10   # run specific days only
    python simulate.py --dry-run       # print prompts without calling the gateway
"""

import argparse
import os
import re
import sys
import threading
import time
from datetime import datetime
from typing import Mapping, Optional

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv() -> bool:
        """Allow dependency-free validation and dry runs."""
        return False

load_dotenv()


def read_compatible_env(
    primary: str,
    legacy: str,
    default: str = "",
    environ: Optional[Mapping[str, str]] = None,
) -> str:
    """Read a current setting, then its supported non-empty legacy alias.

    A blank current value must not shadow a working legacy value. This mirrors
    Caura's server and OpenClaw plugin precedence during the rename transition.
    """
    values = os.environ if environ is None else environ
    return values.get(primary) or values.get(legacy) or default


GATEWAY_URL = os.getenv("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789")
CAURA_API_URL = read_compatible_env(
    "CAURA_API_URL", "MEMCLAW_API_URL", "https://caura.ai/api/v1"  # legacy-name-ok: supported non-empty env fallback
)
CAURA_API_KEY = read_compatible_env(
    "CAURA_API_KEY", "MEMCLAW_API_KEY"  # legacy-name-ok: supported non-empty env fallback
)
CAURA_TENANT_ID = read_compatible_env(
    "CAURA_TENANT_ID", "MEMCLAW_TENANT_ID", "your_tenant_id_here"  # legacy-name-ok: supported non-empty env fallback
)
CAURA_FLEET_ID = read_compatible_env(
    "CAURA_FLEET_ID", "MEMCLAW_FLEET_ID", "fleet-longrun-research"  # legacy-name-ok: supported non-empty env fallback
)


SOURCING_PROMPT_DAYS_1_8 = """\
Run your Day {day} data collection workflow exactly as defined in your AGENTS.md.

Today is Day {day}. The competitor price is $299/month.

Execute all steps:
1. Call caura_recall (query: "competitor pricing current", fleet_ids: ["{fleet_id}"], agent_id: "sourcing-agent", include_brief: true) -- omit status so both active and confirmed memories are visible
2. Call caura_write with: content: "Competitor pricing page shows $299/month for the Pro plan as of Day {day}.", agent_id: "sourcing-agent", fleet_id: "{fleet_id}", visibility: "scope_team"
3. Call caura_recall (query: "competitor pricing", fleet_ids: ["{fleet_id}"], top_k: 3, agent_id: "sourcing-agent")

Print each tool call response including memory IDs and enrichment metadata.
"""

SOURCING_PROMPT_DAY_9 = """\
Run your Day 9 data collection workflow.

CRITICAL: The competitor has updated their pricing page. The new price is $349/month (was $299).

Execute all steps:
1. Call caura_recall (query: "competitor pricing current", fleet_ids: ["{fleet_id}"], agent_id: "sourcing-agent", include_brief: true) -- omit status so both active and confirmed memories are visible
2. Call caura_write with: content: "Competitor pricing page now shows $349/month for the Pro plan. Price increased from $299. Observed Day 9.", agent_id: "sourcing-agent", fleet_id: "{fleet_id}", visibility: "scope_team"
3. Call caura_recall (query: "competitor pricing", fleet_ids: ["{fleet_id}"], top_k: 5, agent_id: "sourcing-agent")

Print each tool call response. Note whether Caura flagged a contradiction automatically.
"""

SOURCING_PROMPT_DAYS_10_14 = """\
Run your Day {day} data collection workflow.

Today is Day {day}. The competitor price remains $349/month.

Execute all steps:
1. Call caura_recall (query: "competitor pricing current", fleet_ids: ["{fleet_id}"], agent_id: "sourcing-agent", include_brief: true) -- omit status so both active and confirmed memories are visible
2. Call caura_write with: content: "Competitor pricing page continues to show $349/month for the Pro plan as of Day {day}.", agent_id: "sourcing-agent", fleet_id: "{fleet_id}", visibility: "scope_team"
3. Call caura_recall (query: "competitor pricing", fleet_ids: ["{fleet_id}"], top_k: 3, agent_id: "sourcing-agent")

Print each tool call response including memory IDs.
"""

VERIFICATION_PROMPT = """\
Run your Day {day} verification workflow exactly as defined in your AGENTS.md.

Today is Day {day}.

Execute all steps:
1. Call caura_recall (query: "competitor pricing", fleet_ids: ["{fleet_id}"], filter_agent_id: "sourcing-agent", top_k: 5, agent_id: "verification-agent")
2. Print: "I see [N] memories about competitor pricing. Statuses: [list them]."
3. Call caura_manage (op: "transition", memory_id: "[ID from recall result]", status: "confirmed") on the most recent active memory
4. Call caura_write with your verification note (include memory ID and Day {day})

{conflict_instruction}

Show every tool call response.
"""

VERIFICATION_CONFLICT_INSTRUCTION = """\
IMPORTANT: You may see both $349 and $299 memories in the pool. If so, write an additional conflict note:
content: "CONFLICT DETECTED: Memory pool contains both $299 (Days 1-8, status: outdated) and $349 (Day 9, status: active) for competitor Pro plan. $349 is the current authoritative value."
"""

SYNTHESIS_PROMPT = """\
Run your Day {day} daily intelligence brief workflow exactly as defined in your AGENTS.md.

Today is Day {day}.

Execute all steps:
1. Call caura_recall (query: "competitor pricing current status", fleet_ids: ["{fleet_id}"], top_k: 5, agent_id: "synthesis-agent", include_brief: true) -- omit status so both active and confirmed memories are visible; passing status: "active" would drop confirmed memories too
2. Call caura_recall (query: "competitor pricing", fleet_ids: ["{fleet_id}"], status: "outdated", top_k: 10, agent_id: "synthesis-agent")
3. Print: "Suppressed [N] outdated memories from brief."
4. Produce the brief in this exact format:

---
DAILY INTELLIGENCE BRIEF - Day {day}
Generated by: synthesis-agent
Memory pool: {fleet_id}

## Competitor Pricing (Governed Recall)
Current price: $[X]/month (source memory IDs: [list])
Status of recalled memories: active / confirmed
Suppressed memories: [N] outdated $[old price] memories from Days 1-8

## Summary
[2-3 sentences based ONLY on active/confirmed memories]
---

5. Call caura_write with a brief-completion record. Omit memory_type so Caura classifies it; `outcome` is server-generated and cannot be supplied to caura_write.
"""


def log(label: str, msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{label}] {msg}", flush=True)


def call_agent(agent_name: str, prompt: str, day: int, dry_run: bool) -> str:
    """Send a prompt to a named OpenClaw agent and return its reply."""
    import subprocess

    label = f"Day {day:02d} | {agent_name}"

    if dry_run:
        log(label, f"DRY RUN -- prompt ({len(prompt)} chars)")
        print(f"\n{'-'*60}\n{prompt.strip()}\n{'-'*60}\n", flush=True)
        return "[dry-run: no response]"

    log(label, "Sending prompt to gateway...")

    try:
        import shutil
        import platform
        openclaw_cmd = shutil.which("openclaw") or (
            os.path.expandvars(r"%APPDATA%\npm\openclaw.cmd")
            if platform.system() == "Windows"
            else "openclaw"
        )
        result = subprocess.run(
            [openclaw_cmd, "agent", "--agent", agent_name, "--message", prompt, "--json"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            log(label, f"ERROR (exit {result.returncode}): {result.stderr[:500]}")
            sys.exit(1)
        import json as _json
        try:
            data = _json.loads(result.stdout)
            reply = data.get("reply") or data.get("content") or data.get("text") or result.stdout
        except _json.JSONDecodeError:
            reply = result.stdout
        log(label, f"Done ({len(reply)} chars)")
        print(f"\n{'-'*60}\n[{label}] RESPONSE:\n{reply}\n{'-'*60}\n", flush=True)
        return reply
    except subprocess.TimeoutExpired:
        log(label, "ERROR: Agent timed out after 300s")
        sys.exit(1)
    except FileNotFoundError:
        log(label, "ERROR: 'openclaw' CLI not found in PATH")
        sys.exit(1)


MEMORY_ID_RE = re.compile(r'"(?:memory_)?id"\s*:\s*"([a-zA-Z0-9_-]{8,})"')
# UUIDs are what Caura issues; prefer them over other id-shaped tokens.
UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def extract_memory_id_candidates(sourcing_reply: str) -> list:
    """Extract candidate memory IDs for the Day 9 write, best guess first.

    The sourcing reply contains IDs from three tool calls: a pre-write recall
    (old $299 memories), the caura_write result (the new $349 memory we
    actually need), and a post-write recall. To find the write's ID rather
    than the first ID in the reply, anchor on the text after the last "349"
    mention (the write result and post-write recall both follow it), preferring
    UUID-shaped IDs. Remaining IDs are kept as fallbacks, later-first.
    """
    anchor = sourcing_reply.rfind("349")
    tail = sourcing_reply[anchor:] if anchor != -1 else sourcing_reply

    candidates = []
    for text in (tail, sourcing_reply):
        for regex in (UUID_RE, MEMORY_ID_RE):
            for mid in regex.findall(text):
                if mid not in candidates:
                    candidates.append(mid)
    return candidates


def wait_for_contradiction_detection(day: int, sourcing_reply: str, dry_run: bool) -> None:
    """Poll GET /memories/{memory_id}/contradictions until detection_status is 'completed'.

    Don't reach for the crystallizer here: it only dedups near-duplicate
    memories to `archived` and never sets `outdated`. The $299 -> `outdated`
    transition on the Day 9 drift is made by the async contradiction
    detector, so Synthesis must wait on that signal, not on crystallization.
    """
    label = f"Day {day:02d} | contradiction-detection"

    if dry_run:
        log(label, f"DRY RUN -- would poll {CAURA_API_URL}/memories/{{memory_id}}/contradictions")
        return

    import requests

    candidates = extract_memory_id_candidates(sourcing_reply)
    if not candidates:
        log(label, "WARNING: Could not find a memory_id in Sourcing Agent's reply. Skipping poll; Synthesis may run before contradiction detection finishes.")
        log(label, f"Reply excerpt for debugging: {sourcing_reply[:300]!r}")
        return

    log(label, f"Candidate memory IDs (best guess first): {candidates}")

    headers = {"Content-Type": "application/json"}
    if CAURA_API_KEY:
        headers["X-API-Key"] = CAURA_API_KEY

    memory_id = candidates[0]
    log(label, f"Polling contradiction detection for memory {memory_id}...")

    for _ in range(12):  # up to 60s
        time.sleep(5)
        try:
            resp = requests.get(
                f"{CAURA_API_URL}/memories/{memory_id}/contradictions",
                headers=headers,
                params={"tenant_id": CAURA_TENANT_ID},
                timeout=30,
            )
            if resp.ok and resp.json().get("detection_status") == "completed":
                log(label, f"Contradiction detection completed for memory {memory_id}.")
                return
            if resp.status_code == 404:
                # Extracted token isn't a real memory ID -- fall back to the next candidate
                remaining = [c for c in candidates if c != memory_id]
                if remaining:
                    candidates = remaining
                    memory_id = candidates[0]
                    log(label, f"Memory ID not found (404); trying next candidate {memory_id}...")
                else:
                    log(label, "WARNING: No extracted ID resolves to a real memory. Skipping poll; Synthesis may run before contradiction detection finishes.")
                    return
            elif not resp.ok:
                log(label, f"Poll returned HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as exc:
            log(label, f"Poll attempt failed: {exc}")
    log(label, "WARNING: Contradiction detection did not confirm completion within 60s. Synthesis may run before the $299 memory is marked outdated.")


def run_day(day: int, dry_run: bool) -> None:
    print(f"\n{'='*60}", flush=True)
    print(f"  SIMULATED DAY {day}", flush=True)
    print(f"{'='*60}\n", flush=True)

    if day <= 8:
        sourcing_prompt = SOURCING_PROMPT_DAYS_1_8.format(
            day=day, fleet_id=CAURA_FLEET_ID
        )
    elif day == 9:
        sourcing_prompt = SOURCING_PROMPT_DAY_9.format(fleet_id=CAURA_FLEET_ID)
    else:
        sourcing_prompt = SOURCING_PROMPT_DAYS_10_14.format(
            day=day, fleet_id=CAURA_FLEET_ID
        )

    conflict_instruction = VERIFICATION_CONFLICT_INSTRUCTION if day >= 9 else ""
    verification_prompt = VERIFICATION_PROMPT.format(
        day=day,
        fleet_id=CAURA_FLEET_ID,
        conflict_instruction=conflict_instruction,
    )
    synthesis_prompt = SYNTHESIS_PROMPT.format(day=day, fleet_id=CAURA_FLEET_ID)

    # Sourcing and Verification run concurrently
    sourcing_result: dict = {}
    verification_result: dict = {}

    def run_sourcing():
        sourcing_result["reply"] = call_agent("sourcing-agent", sourcing_prompt, day, dry_run)

    def run_verification():
        verification_result["reply"] = call_agent(
            "verification-agent", verification_prompt, day, dry_run
        )

    log(f"Day {day:02d}", "Starting Sourcing Agent and Verification Agent in parallel...")
    t_source = threading.Thread(target=run_sourcing, name=f"sourcing-day{day}")
    t_verify = threading.Thread(target=run_verification, name=f"verification-day{day}")
    t_source.start()
    t_verify.start()
    t_source.join()
    t_verify.join()
    log(f"Day {day:02d}", "Both agents complete.")

    # After Day 9 parallel run: wait for contradiction detection before Synthesis reads
    if day == 9:
        log(f"Day {day:02d}", "Day 9 drift detected -- waiting for contradiction detection...")
        wait_for_contradiction_detection(day, sourcing_result.get("reply", ""), dry_run)
        log(f"Day {day:02d}", "Contradiction detection resolved. Synthesis Agent will now recall governed memory.")

    # Synthesis runs after both agents and, on Day 9, after contradiction detection resolves
    log(f"Day {day:02d}", "Starting Synthesis Agent...")
    call_agent("synthesis-agent", synthesis_prompt, day, dry_run)

    log(f"Day {day:02d}", "Day complete.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the 14-day Caura fleet simulation")
    parser.add_argument(
        "--start", type=int, default=1, metavar="DAY",
        help="Start from this day (default: 1)"
    )
    parser.add_argument(
        "--end", type=int, default=14, metavar="DAY",
        help="End on this day inclusive (default: 14)"
    )
    parser.add_argument(
        "--days", type=int, nargs="+", metavar="DAY",
        help="Run only these specific days (overrides --start/--end)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print prompts without calling the gateway"
    )
    parser.add_argument(
        "--delay", type=float, default=2.0, metavar="SECONDS",
        help="Seconds to pause between days (default: 2)"
    )
    args = parser.parse_args()

    days_to_run = args.days if args.days else list(range(args.start, args.end + 1))
    if not days_to_run:
        parser.error("day selection is empty; ensure --start is not greater than --end")
    invalid_days = [day for day in days_to_run if not 1 <= day <= 14]
    if invalid_days:
        parser.error(f"days must be between 1 and 14; got {invalid_days}")

    print("\nCaura Long-Run Research Fleet -- 14-Day Simulation", flush=True)
    print(f"Gateway:    {GATEWAY_URL}", flush=True)
    print(f"Fleet:      {CAURA_FLEET_ID}", flush=True)
    print(f"Days:       {days_to_run}", flush=True)
    print(f"Dry run:    {args.dry_run}", flush=True)
    print(f"Contradiction detection endpoint: {CAURA_API_URL}/memories/{{memory_id}}/contradictions", flush=True)
    print(flush=True)

    if not args.dry_run:
        import requests

        # Verify gateway is reachable before starting
        try:
            requests.get(f"{GATEWAY_URL}/health", timeout=5)
        except Exception:
            try:
                # Some OpenClaw versions don't have /health — try the models list
                requests.get(f"{GATEWAY_URL}/v1/models", timeout=5)
            except Exception:
                print(
                    f"ERROR: OpenClaw gateway not reachable at {GATEWAY_URL}\n"
                    "Run: openclaw gateway restart",
                    flush=True,
                )
                sys.exit(1)

    for i, day in enumerate(days_to_run):
        run_day(day, args.dry_run)
        if i < len(days_to_run) - 1 and args.delay > 0:
            time.sleep(args.delay)

    print("\nSimulation complete.", flush=True)


if __name__ == "__main__":
    main()
