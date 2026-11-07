# AI-first Helpdesk — Django REST Framework

AI-first Backend Engineer take-home project: accept incoming helpdesk webhooks, find relevant knowledge-base articles, generate AI **drafts** asynchronously, require operator approval, and only then deliver replies to a mock Helpdesk.

[Українська версія](README_UA.md) · [MIT License](LICENSE) · [Agent instructions](AGENTS.md)

## Stack

- Django 5.2 LTS, Django REST Framework, OpenAPI/Swagger UI
- PostgreSQL 16 for tickets, webhook events, moderation and delivery history
- Redis, Celery worker and Celery Beat for asynchronous jobs, retries and recovery
- Gemini, OpenAI, OpenAI-compatible providers or deterministic mock
- Gunicorn, Nginx, Docker Compose and a persistent mock Helpdesk receiver


## Quick start (Windows / PowerShell)

Install Docker Desktop and enable Linux containers. Ports **8020** and **8021** must be free.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
docker compose up -d --build
docker compose ps
```

The setup script creates a local `.env` with strong random secrets only if one does not already exist. The operator account is `operator`; the dedicated Django Admin account is `adminroot`. Generated passwords remain in your local `.env`.

| Interface | Local address |
| --- | --- |
| Operator dashboard | http://127.0.0.1:8020/ |
| Django Admin | http://127.0.0.1:8020/admin/ |
| Health | http://127.0.0.1:8020/health/ |
| Webhook | POST http://127.0.0.1:8020/webhooks/helpdesk |
| Operator API | http://127.0.0.1:8020/api/v1/tickets/ |
| API documentation | http://127.0.0.1:8020/api/docs/ |
| Mock Helpdesk replies | http://127.0.0.1:8021/replies |

PostgreSQL and Redis have no public host ports.

## End-to-end workflow

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo.ps1
```

Or POST to `/webhooks/helpdesk` with `Content-Type: application/json` and `X-Webhook-Secret: <WEBHOOK_SECRET from local .env>`:

```json
{
  "event_id": "evt-1042",
  "ticket_id": "T-1042",
  "customer_email": "user@example.com",
  "message": "How do I export a PDF report?",
  "reply_url": "http://mock-helpdesk:8001/tickets/T-1042/replies"
}
```

`mock-helpdesk:8001` is an **internal Docker hostname**. Do not use `127.0.0.1:8021` for the callback.

1. The webhook validates the payload, commits it to PostgreSQL and responds with HTTP **202** without waiting for AI.
2. Celery generates a draft using retrieved knowledge-base context.
3. An authenticated operator reviews and optionally edits the draft, then **approves or rejects** it.
4. Approval creates one delivery with an immutable `Idempotency-Key`; rejection never sends.
5. The mock receiver stores the approved reply. Duplicate webhook events do not trigger more drafts or deliveries; conflicting payloads return **409**.

The operator dashboard and API use a staff session and CSRF protection. Django Admin is limited to `adminroot`: knowledge-base articles are editable, while ticket, delivery and webhook logs are **read-only**.

## LLM providers

Choose a mode in your private `.env`, then recreate the worker:

```powershell
docker compose up -d --force-recreate worker
```

| Mode | Required configuration |
| --- | --- |
| Offline mock | `LLM_MODE=mock`, `LLM_BASE_URL=` |
| Gemini | `LLM_MODE=gemini`, `GEMINI_API_KEY`, `GEMINI_MODEL` |
| OpenAI | `LLM_MODE=openai`, `OPENAI_API_KEY`, `OPENAI_MODEL` |
| Compatible Chat Completions API | `LLM_MODE=openai_compatible`, `LLM_BASE_URL`, `LLM_MODEL`, optionally `LLM_API_KEY` |

The mock returns a stable KB-derived draft after a configurable **5–30 second** delay. If `LLM_BASE_URL` is configured, mock mode can optionally contact that compatible gateway but ignores its generated text. **Leave `LLM_BASE_URL` empty for offline tests.**

### Optional Local AI Gateway (not required)

The standard `compose.yml` has no dependency on an external network. A separate `compose.local-ai.yml` connects **only the worker** to an already existing gateway Docker network when explicitly requested.

For a separately running OpenAI-compatible gateway, set **local** `.env` values (placeholders only):

```dotenv
LLM_MODE=openai_compatible
LLM_BASE_URL=http://llm-api/v1
LLM_MODEL=your-model-id
LLM_API_KEY=your-local-gateway-token
```

If you already have that gateway network:

```powershell
docker network inspect local-ai-api
docker compose -f compose.yml -f compose.local-ai.yml up -d --build
```

Use `LOCAL_AI_NETWORK` to override the network name if yours differs. Without a gateway, just run `docker compose up -d --build`. You do **not** need to create `local-ai-api`, install a local model, or configure a local gateway token.

## Reliability and safeguards

- **Fast ACK:** database-first webhook ingestion, unique event/ticket IDs, immutable payload conflict detection.
- **Global throttling:** Redis sliding window allows at most **60 LLM calls in 60 seconds** across workers.
- **Recovery:** Celery Beat requeues work from durable database state after transient Redis/worker failure.
- **Human in the loop:** no outbound reply without explicit operator approval.
- **Idempotent delivery:** a permanent key per ticket, retries on transient failures, receiver-side deduplication. A real Helpdesk must implement its own idempotency for exactly-once semantics.
- **Security:** separate operator/Admin accounts, CSRF, webhook secret, callback host allowlist, safe outbound HTTP policies. Production remote callbacks additionally need DNS/IP rebinding protection.
- **Privacy:** the KB contains eight fictional demo articles. Do not submit real customer data to third-party LLMs without approval.
- **Trade-offs:** keyword matching instead of embeddings; operator API currently returns up to 1,000 newest tickets; this is a demo, not a fully hardened production deployment.


## Validation

```powershell
docker compose config -q
docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py makemigrations --check --dry-run
docker compose exec -T web python manage.py test tests --verbosity 2 --noinput
```

Tests use a temporary database and mocked network providers. They cover validation, duplicates and conflicts, 500 unique ingestions, operator access, retrieval, moderation, retry, Gemini and OpenAI-compatible modes. An end-to-end smoke test is available through `scripts/demo.ps1`; real provider calls may incur charges. Do not mistake test-client load for a full concurrent production benchmark.

## Project layout

```text
config/               Django configuration, routes, Celery
helpdesk/             REST API, data models, LLM, KB, background tasks
mock_helpdesk/        Separate persistent mock receiver
templates/            Operator UI and login
tests/                Regression tests
scripts/              Setup, demo and checks
nginx/                Local reverse proxy
compose.yml           Standalone stack (no external networks)
compose.local-ai.yml  Optional local AI network override
.env.example          Public configuration template
AGENTS.md             Canonical coding-agent instructions
CLAUDE.md             References AGENTS.md
LICENSE               MIT
```