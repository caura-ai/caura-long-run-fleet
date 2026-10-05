# Caura Research Fleet — Shared Governance Skill

## Your Memory Identity
- fleet_id: fleet-longrun-research
- tenant_id: default (omit if using managed cloud — inferred from API key)
- visibility: scope_team (all agents share this pool)

## BEFORE every task
1. Call `caura_recall` with your query, `fleet_ids: ["fleet-longrun-research"]`, and `include_brief: true`
2. Omit `status` entirely. Default recall already excludes `outdated`/`conflicted`/`archived`/`deleted` rows while keeping both `active` and `confirmed` memories. Do NOT pass `status: "active"` explicitly — that excludes `confirmed` memories too, which drops verified facts from governed recall.
3. Never act on recalled memories with status `outdated` or `conflicted`

## AFTER every task
1. Call `caura_write` with your finding
2. Always set `fleet_id: "fleet-longrun-research"` and `visibility: "scope_team"`
3. Include `agent_id` matching your own agent identity
4. You only need to send `content` — Caura auto-infers type, weight, and tags

## Contradiction Rule
If you discover a fact that contradicts what you previously wrote:
- Write the NEW fact with `caura_write`
- Caura's async contradiction detector will auto-flag the old memory as `outdated` once it finishes running (poll `GET /memories/{memory_id}/contradictions` for `detection_status: "completed"` if you need to wait on it)
- Do NOT manually delete old memories — let contradiction detection resolve them

## Status Transitions You Should Know
- `pending → confirmed` — when you verify a fact from another agent
- `active → outdated` — when you discover a superseding fact (Caura does this automatically)
- `active → archived` — when data is stale and not expected to update

## Nightly Crystallizer
Caura runs a background crystallizer that deduplicates near-identical memories
into a canonical fact with provenance. It does NOT resolve contradiction chains
and never sets `outdated` — that transition is made by the async contradiction
detector. After Day 9 of any drift scenario, don't reach for the crystallizer;
instead poll `GET /memories/{memory_id}/contradictions` until `detection_status`
is `completed` so the Synthesis agent gets a clean recall surface.
