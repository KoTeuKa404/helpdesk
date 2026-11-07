# AI-first Helpdesk — Django + DRF

[English README](README.md) · [Ліцензія MIT](LICENSE) · [Інструкції для AI-агентів](AGENTS.md)

Тестовий backend-проєкт для **AI-first Backend Engineer**: отримує webhook від Helpdesk, шукає статті бази знань, асинхронно формує **чернетку** через LLM і надсилає відповідь лише після підтвердження оператором.

## Технології

- Django 5.2 LTS + Django REST Framework, OpenAPI/Swagger;
- PostgreSQL 16 для звернень, дедуплікації, статусів і журналів;
- Celery + Redis + Celery Beat для генерації, доставки, повторних спроб і відновлення;
- Gemini, OpenAI, OpenAI-compatible API або mock LLM;
- Gunicorn, Nginx, Docker Compose; окремий Mock Helpdesk із SQLite.

**Звичайний запуск не потребує Local AI Gateway, зовнішніх Docker-мереж чи API-ключів.**

## Початок роботи

Встанови Docker Desktop (Linux-контейнери). Порти 8020 і 8021 мають бути вільні.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
docker compose up -d --build
docker compose ps
```

`setup.ps1` створює приватний `.env` із випадковими секретами, якщо його ще немає, і не перезаписує наявні паролі. Оператор має логін `operator`, окремий адміністратор — `adminroot`. Їхні паролі зберігаються **лише** у локальному `.env`.

| Компонент | Локальна адреса |
| --- | --- |
| Кабінет оператора | http://127.0.0.1:8020/ |
| Django Admin | http://127.0.0.1:8020/admin/ |
| Перевірка стану | http://127.0.0.1:8020/health/ |
| Webhook | POST http://127.0.0.1:8020/webhooks/helpdesk |
| API звернень | http://127.0.0.1:8020/api/v1/tickets/ |
| Swagger | http://127.0.0.1:8020/api/docs/ |
| Отримані відповіді mock | http://127.0.0.1:8021/replies |

PostgreSQL і Redis не відкриваються на портах ПК. Mock Helpdesk монтує **лише власний вихідний код**, не всю директорію з `.env`.

## Перевірка сценарію

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo.ps1
```

Або надішли `POST /webhooks/helpdesk` із заголовками `Content-Type: application/json` та `X-Webhook-Secret: <секрет із локального .env>`:

```json
{
  "event_id": "evt-1042",
  "ticket_id": "T-1042",
  "customer_email": "user@example.com",
  "message": "Не можу експортувати звіт у PDF",
  "reply_url": "http://mock-helpdesk:8001/tickets/T-1042/replies"
}
```

Тут `mock-helpdesk:8001` — внутрішня адреса Docker, а не порт 8021 на комп'ютері.

1. Webhook записує подію в PostgreSQL і швидко повертає HTTP **202**.
2. Celery отримує статті KB та генерує чернетку.
3. Оператор входить у кабінет, редагує текст і підтверджує або відхиляє його.
4. Лише підтверджена відповідь надсилається до Mock Helpdesk з постійним `Idempotency-Key`.
5. Повторна подія не викликає нової генерації чи доставки; конфліктні дані отримують **409**.

Оператор працює через окрему staff-сесію з CSRF-захистом. `adminroot` має доступ до Django Admin: статті KB можна редагувати, а звернення, доставки та webhook-журнали доступні **лише для читання**.

## Моделі й провайдери

У приватному `.env` вибери `LLM_MODE`:
- `mock` — без хмарного API-ключа, затримка 5–30 секунд; для повністю локального режиму залиш `LLM_BASE_URL=`;
- `gemini` — `GEMINI_API_KEY` + `GEMINI_MODEL`;
- `openai` — `OPENAI_API_KEY` + `OPENAI_MODEL`;
- `openai_compatible` — `LLM_BASE_URL`, `LLM_MODEL`, за потреби `LLM_API_KEY`.

Після зміни провайдера виконай `docker compose up -d --force-recreate worker`.

### Опціональний Local AI Gateway

`compose.yml` **не** має залежності від мережі `local-ai-api`. Якщо власний шлюз уже працює й має зовнішню Docker-мережу, можна підключити worker окремим файлом `compose.local-ai.yml`.

Приклад **лише шаблонних** значень локального `.env`:

```dotenv
LLM_MODE=openai_compatible
LLM_BASE_URL=http://llm-api/v1
LLM_MODEL=your-model-id
LLM_API_KEY=your-local-gateway-token
```

```powershell
docker network inspect local-ai-api
docker compose -f compose.yml -f compose.local-ai.yml up -d --build
```

Для звичайного запуску використовуй лише `docker compose up -d --build`. Тоді Local AI Gateway і його мережа **не потрібні**.

## Надійність і безпека

- Дедуплікація за `event_id`, конфлікти `ticket_id`, транзакції PostgreSQL.
- Не більше **60 LLM-викликів за 60 секунд** на сервіс; Celery Beat відновлює чергу після збоїв.
- Жодних відповідей без схвалення оператора; retry та ідемпотентність доставки.
- `.env*` не потрапляють до Docker build і Git (виняток для Git — публічний `.env.example`).
- URL доставки обмежений allowlist; для реальних зовнішніх сервісів потрібні HTTPS та додаткова перевірка DNS/IP.
- База знань містить вісім вигаданих статей. Не надсилай справжні персональні дані стороннім моделям без дозволу.

Обмеження: пошук за ключовими словами, до 1000 останніх звернень в API, відсутність повністю налаштованого публічного продакшену. Для відкриття HTTPS потрібні безпечні cookies, правильні налаштування проксі, хостів і CSRF, резервні копії та моніторинг.

## Автоматичні тести

```powershell
docker compose config -q
docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py makemigrations --check --dry-run
docker compose exec -T web python manage.py test tests --verbosity 2 --noinput
```

Тести використовують тимчасову БД та імітовані відповіді сторонніх API. Для ручного наскрізного тесту використовуй `scripts/demo.ps1` та підтвердження в кабінеті. Реальний Gemini може мати обмеження квоти або вартість.

**Публікація:** створюй порожній GitHub-репозиторій без автоматичного README/.gitignore, перевір `git status`, потім завантажуй гілку `main`. Файл `.env` не публікуй.

**Зупинка:** `docker compose down` зберігає дані. `docker compose down -v` видаляє persistent volumes — не використовуй без потреби.
