# Security and privacy

**Default controls:** offline demo; explicit real-send opt-in; signed webhooks; admin-key access; bounded payloads and context; immutable read-only tool allowlist; human handoff and opt-out; unique inbound message IDs. No WhatsApp Web login automation, mass outreach or number harvesting.

## Meta signatures

GET verification proves webhook ownership using a token. POST authenticity is a distinct concern: `X-Hub-Signature-256` is verified with HMAC-SHA256 over the **original bytes**, requiring `META_APP_SECRET`. The endpoint rejects unsigned or modified bodies. No public webhook is configured by this repository.

## Prompt injection and human approval

Incoming user messages are **never executable instructions**. The LLM adapter accepts only five read-only tool schemas, limits tool-call count, validates parsed JSON and rejects arbitrary tool names. A model response cannot directly create appointments, send messages, read files or approve cancellations. Booking confirmation is a deterministic state transition; cancellation enters the human queue.

## Data handling

A phone number is HMAC-pseudonymized for persistence. The in-memory sender value may be used to address a reply while the request is executing, but it is not written to the contact table. The **message body itself remains plaintext** in the local database and may contain identifying text. Use synthetic data only. `MESSAGE_RETENTION_DAYS` is a documented configuration placeholder until retention cleanup is implemented. Operators should treat database snapshots, logs, export artifacts and endpoint access as sensitive.

## Deployment restrictions

The demonstration interface is disabled when `APP_ENV` is not local; outside local mode, startup requires a strong admin key. In production, add managed authentication, TLS, proper credentials rotation, a queue, persistent rate limiting, audit retention, a data retention job, monitoring, security review, consent and legal assessment. Avoid exposing the local demonstration or SQLite file to the Internet. Never commit `.env`.

## Responsible Meta messaging

Only official WhatsApp Cloud API calls are supported. Free-text messaging checks the session window; outside-window template sending, Direct Send API and other message classes are not implemented. Before activating real sends, confirm current Meta documentation, business eligibility, applicable policies, opt-in and lawful basis.
