# Local cross-agent smoke runbook

This runbook verifies the minimum fleet-memory path against a local Caura deployment:

1. An invalid API key is rejected when the local server has `CAURA_API_KEY` enabled.
2. A fleet is created, or an existing requested fleet is accepted, and then confirmed with `GET /fleet`.
3. Agent A writes a unique `scope_team` fact to that fleet.
4. Agent B recalls the unique marker from the same fleet.
5. The script asserts the returned memory ID or content matches Agent A's write.

The script is dry-run by default and refuses live execution against non-loopback hosts.

```bash
python scripts/cross_agent_smoke.py
```

To execute against a running local Caura:

```bash
CAURA_API_URL=http://127.0.0.1:8000/api/v1 \
CAURA_TENANT_ID=local \
CAURA_SMOKE_ALLOW_NETWORK=true \
python scripts/cross_agent_smoke.py --execute
```

If the local API is protected, also set `CAURA_API_KEY`. Never place a real key in the command itself, this document, or version control.

The live path intentionally leaves a uniquely named smoke fleet and one memory in the local database so the evidence remains inspectable. It never deletes data and it cannot target the managed Caura host. Use a disposable local database when repeatability matters.

`POST /recall` requires the local deployment's configured recall/summarization provider. If that provider is unavailable, the smoke test will fail after the write; restore the provider and rerun with a new default fleet ID.
