# Architecture decision log

## ADR-001: Offline by default
Demo and mandatory CI are entirely credential-free and avoid external costs. `ENABLE_REAL_SEND=false` is the enforced default.

## ADR-002: Official Meta API only
The adapter uses Graph API and signed HTTP webhooks. WhatsApp Web automation and personal browser sessions are excluded.

## ADR-003: Deterministic write commands
Language model tool calls are limited to read-only catalog functions. Booking writes require a dedicated, explicit confirmation step. Cancellations require a human operator.

## ADR-004: Small interchangeable components
FastAPI transport, SQLAlchemy persistence, Meta HTTP sending and LLM selection are separate modules. Single fictional business and no multi-tenancy.

## ADR-005: Auditability and limits
Unique message IDs, conversation transitions, tool-execution audit records, minimal pseudonymized identifiers and configurable switches. Production-grade outbox, distributed rate limiting and retention enforcement are deferred and documented.
