# Pinned Caura OSS contract verification

The commands in this reference fleet were verified on 5 October 2026 against Caura OSS commit [`80a733e68260e179fcdebcb988486de56d6bc747`](https://github.com/caura-ai/caura/commit/80a733e68260e179fcdebcb988486de56d6bc747).

Verified surfaces:

| Reference-fleet operation | OSS source contract |
| --- | --- |
| Create fleet | `POST /api/v1/fleet`; body includes `tenant_id`, required `fleet_id`, optional `display_name` and `description`; success is `201` with `ok`, `fleet_id`, and `tenant_id` |
| Write as Agent A | `POST /api/v1/memories`; body accepts `tenant_id`, `fleet_id`, `agent_id`, `content`, and `visibility`; success is `201` |
| Recall as Agent B | `POST /api/v1/recall`; body accepts `tenant_id`, `fleet_ids`, `query`, and `caller_agent_id`; response includes `memory_count` and `memories` |
| Poll contradiction evidence | `GET /api/v1/memories/{memory_id}/contradictions`; required query field is `tenant_id`; response includes `memory_id`, `status`, `superseded_by`, `superseded_memories`, `detection_status`, and `contradictions` |

The `/api/v1` prefix is verified where the fleet and memory routers are mounted in `core-api/src/core_api/app.py`. Route bodies are verified in `routes/fleet.py`, `routes/memories.py`, `schemas.py`, and `openapi_responses.py` at the pinned commit.

Run the source-backed check against a checkout of that exact commit:

```bash
python scripts/check_oss_contract.py --oss-root /path/to/caura
```

CI checks out the exact commit and runs the same verifier. Updating the pinned SHA requires re-reading these source contracts and updating this document in the same pull request.
