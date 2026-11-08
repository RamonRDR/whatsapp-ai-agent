# Architecture and boundaries

## Request flow

1. Meta's webhook handshake is a GET request using a shared verification token. A POST request verifies the SHA-256 signature against the untouched request body, using the separate app secret.
2. For a supported incoming text message, persist keyed pseudonym, contact, conversation, message and monotonic inbound timestamp. Unique `channel + external_id` provides basic idempotency. Unrecognized and status events are handled independently.
3. The same agent processes demo messages. A deterministic router handles supported intents and explicit booking commands. The optional LLM can only select the five allowlisted **read-only** tools.
4. Outputs are grounded in fictitious catalog data, not unvalidated generated claims.
5. Booking is a two-step state transition with an explicit CONFIRM. A unique slot prevents the same instant from being booked twice. Cancellations require human handoff.
6. Human handoff pauses automated responses. Authenticated operator APIs list work and resume processing.
7. Outgoing Graph API sends are disabled by default and require both explicit activation and an active service window.

## Dependency graph

- `config.py`: validated environment configuration and safe switches
- `database.py` / `models.py`: SQLAlchemy persistence and audit entities
- `catalog.py`: fictional structured catalog and read-only lookup functions
- `security.py`: message integrity and pseudonymization
- `llm.py`: opt-in compatible chat-completions tool selection
- `agent.py`: deterministic transitions, validated read-only tools and recording
- `meta.py`: opt-in Graph API HTTP client, with no browser automation
- `api.py`: FastAPI routes, webhook dispatch, demo and authenticated operator API
- `static/demo.html`: local UI with no external dependencies
- `evals`: offline scenario metrics and regression gate
- `migrations`: Alembic schema versioning

## Design trade-offs

The minimal code favors a single demo business and single local storage backend. Session and external transport interfaces can later be replaced with adapters without changing domain-level intent handling. PostgreSQL can be used by setting the URL and installing its DB driver separately; this configuration is **not** exercised in CI. The local SQLite startup bootstraps tables for convenience, while actual deployments should invoke Alembic explicitly.

LLM selection is currently **read only**. Sensitive actions are kept outside the LLM loop. Production-grade message handling should persist a durable outbox before sending, require acknowledgments and implement retries with platform-aware idempotency. Do not claim end-to-end exactly-once delivery based on this demo.

There is no integration with Donna Agenda, BethLash or other customer data.
