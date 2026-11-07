# Agent working notes — AI-first Helpdesk

## Goal / architecture
Django + DRF + PostgreSQL + Redis/Celery + local Nginx + persistent mock Helpdesk. The Django config follows the user's sample Docker + settings pattern, but is a distinct project.

## Non-negotiable invariants
1. `POST /webhooks/helpdesk` must acknowledge a valid event in <2 s without waiting for LLM, Redis, or HTTP delivery. Persist in PostgreSQL first; Celery Beat recovers queued work.
2. Unique `event_id` and `ticket_id`; duplicates must never regenerate or re-send. Conflicting payloads yield 409.
3. LLM output is **always** a draft requiring explicit operator approval; rejection never sends.
4. A single immutable `Delivery.idempotency_key` per ticket. Exactly-once delivery over HTTP requires server-side dedup, provided by the mock service.
5. No unrestricted POST to a user-supplied URL. Respect callback host allowlist and HTTPS for non-mock. Don't log or commit secrets.
6. The mock LLM must simulate latency 5–30 s by default. Global provider limiter ≤60 calls/minute.
7. Database is source of truth; task queues are at-least-once, with transactional state changes and recovery after outages.
8. Don't edit the user's `alive/BackEnd/doker` reference project.

## Typical commands
```sh
# Windows PowerShell in repository root
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
docker compose up -d --build
docker compose exec web python manage.py test tests --verbosity 2
powershell -ExecutionPolicy Bypass -File .\scripts\demo.ps1
```

## Where to look
- `config/settings.py`: env, PostgreSQL, DRF defaults, Celery settings, security.
- `helpdesk/service.py`: DB ingestion and moderation transitions.
- `helpdesk/tasks.py`: worker, provider-wide rolling rate limit, retry/recovery.
- `helpdesk/llm.py`, `helpdesk/knowledge.py`: mock/real generation and lightweight keyword retrieval.
- `helpdesk/views.py`, `helpdesk/serializers.py`: DRF API and SSRF restrictions.
- `mock_helpdesk/server.py`: persistent receiver idempotency implementation.
- `tests/`: regression tests. Extend tests whenever changing state transitions.

## Known limitations / future improvements
- No public deployment provided; Compose binds HTTP to loopback only.
- Real Helpdesk must implement idempotency on its API to guarantee no duplicate customer replies.
- Production callback URLs need DNS/IP validation or a protected egress proxy to prevent DNS rebinding.
- The demo allows a maximum of 1000 visible tickets and a simple keyword-based KB search. For higher load use pagination and full-text search/pgvector.
- Generation failures after 3 attempts need a manual retry endpoint if desired.
- Provider API and actual Docker runtime tests are not guaranteed from an offline code-generation environment; test on target PC before submitting.
