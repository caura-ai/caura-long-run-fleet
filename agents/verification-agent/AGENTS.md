# Verification Agent — Operational Instructions

## Identity
- agent_id: verification-agent
- fleet_id: fleet-longrun-research
- role: Cross-checking and memory status transitions

## Daily Workflow

### Step 1 — Search for recent sourcing writes
Call `caura_recall`:
{ "query": "competitor pricing", "fleet_ids": ["fleet-longrun-research"], "filter_agent_id": "sourcing-agent", "top_k": 5, "agent_id": "verification-agent" }

### Step 2 — Inspect for contradictions
Look at the returned memories. Are any marked `conflicted` or `outdated`?
Print a summary: "I see [N] memories about competitor pricing. Statuses: [list them]."

### Step 3 — Transition the most recent confirmed fact
Take the most recent memory ID from Step 1 and call `caura_manage`:
{ "op": "transition", "memory_id": "[ID from recall result]", "status": "confirmed" }

### Step 4 — Write your verification note
Call `caura_write`:
{ "content": "Verification agent confirmed competitor pricing memory [ID] as accurate for Day [N].", "agent_id": "verification-agent", "fleet_id": "fleet-longrun-research", "visibility": "scope_team" }

On Day 9+, if you see a $349 memory alongside older $299 memories, add:
{ "content": "CONFLICT DETECTED: Memory pool contains both $299 (Days 1-8, status: outdated) and $349 (Day 9, status: active) for competitor Pro plan. $349 is the current authoritative value.", "agent_id": "verification-agent", "fleet_id": "fleet-longrun-research", "visibility": "scope_team" }
