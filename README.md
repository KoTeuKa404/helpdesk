# AI-first Helpdesk · Django + DRF

Невеликий сервіс для тестового завдання AI-first Backend Engineer. Приймає webhook від умовного Helpdesk, шукає релевантні статті бази знань, генерує **чернетку** з LLM, чекає рішення оператора і тільки після підтвердження надсилає відповідь у mock Helpdesk.

## Стек

- **Django 5.2 LTS + Django REST Framework** — webhook, API, операторський кабінет і Django Admin.
- **PostgreSQL 16** — звернення, дедуплікація `event_id`, чернетки, переходи станів, надійний журнал доставки.
- **Celery + Redis** — асинхронна генерація та доставка, відновлення завислих/непоставлених задач через Celery Beat.
- **OpenAI API** (опціонально) або **mock LLM** зі штучною затримкою 5–30 секунд.
- **Gunicorn + Nginx + Docker Compose** — запуск однією командою.
- **Mock Helpdesk** — локальна HTTP-система з SQLite-журналом та підтримкою `Idempotency-Key`.

> Це окремий навчальний проєкт. Структуру Docker, Django settings, Gunicorn, Celery та PostgreSQL адаптовано за принципом прикладу `C:\Users\home\Desktop\project\alive\BackEnd\doker`, але без копіювання чужої бази, ключів або даних.

## Швидкий запуск (Windows / PowerShell)

Потрібні Docker Desktop із Linux-контейнерами та Windows PowerShell. Порти 8020 і 8021 мають бути вільними.

```powershell
# Відкрийте PowerShell у директорії цього репозиторію
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1

docker compose up -d --build
# Перевірити стан
docker compose ps
docker compose logs --tail=60 web worker beat migrate
```

Скрипт `setup.ps1` **один раз** створює `.env` із випадковими секретами. Не перезаписує існуючий `.env` і не друкує паролі. Щоб переглянути локальні облікові дані:

```powershell
Select-String '^(OPERATOR_USERNAME|OPERATOR_PASSWORD)=' .env
```

Система відкривається за адресами:

| Що | Адреса |
|---|---|
| Кабінет оператора | **http://127.0.0.1:8020/** |
| Django Admin / статті бази знань | http://127.0.0.1:8020/admin/ |
| Health check | http://127.0.0.1:8020/health/ |
| Прийом webhook | **POST http://127.0.0.1:8020/webhooks/helpdesk** |
| DRF API звернень (авторизований оператор) | http://127.0.0.1:8020/api/v1/tickets/ |
| Отримані mock Helpdesk відповіді | http://127.0.0.1:8021/replies |

Адміністраторський обліковий запис створюється з `.env` лише за відсутності. Користувач є `is_staff=True`, але **не** суперкористувач; для редагування статей через Django Admin знадобиться надати `is_superuser` або відповідні права командою Django. Для тестового середовища можна створити окремого суперкористувача:

```powershell
docker compose exec web python manage.py createsuperuser
```

### Перевірка повного сценарію

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo.ps1
```

Скрипт згенерує випадкові `ticket_id` / `event_id`, візьме `WEBHOOK_SECRET` із `.env` і надішле запит. Webhook повертає HTTP **202** одразу після збереження в PostgreSQL, **не чекаючи** генерації. Далі:

1. Відкрийте http://127.0.0.1:8020/, увійдіть як оператор.
2. Через 5–30 секунд mock LLM сформує чернетку (або реальний LLM, якщо налаштований ключ).
3. Відредагуйте текст, натисніть **Підтвердити** або **Відхилити**.
4. У випадку підтвердження перевірте результат у http://127.0.0.1:8021/replies — рівно один запис для цього тикета.
5. Надішліть той самий webhook ще раз: нова чернетка та повторна відповідь не створюються.

Формат JSON події:

```json
{
  "event_id": "evt_8f2a",
  "ticket_id": "T-1042",
  "customer_email": "user@example.com",
  "message": "Не можу експортувати звіт у PDF",
  "reply_url": "http://mock-helpdesk:8001/tickets/T-1042/replies"
}
```

Вимога до заголовка webhook: `X-Webhook-Secret: <WEBHOOK_SECRET з .env>`. Для mock reply_url важлива **внутрішня** адреса Docker `mock-helpdesk:8001`, а не зовнішня `127.0.0.1:8021`.

Успішна відповідь mock Helpdesk на `POST <reply_url>` — **201 Created** і тіло:

```json
{"ticket_id":"T-1042","message":"Щоб експортувати звіт у PDF, відкрийте..."}
```

## API

| Метод | URL | Хто може | Результат |
|---|---|---|---|
| POST | `/webhooks/helpdesk` | Сервіс із правильним `X-Webhook-Secret` | HTTP 202; `duplicate: true` для повтору |
| GET | `/api/v1/tickets/` | Staff-сесія оператора | Список до 1000 останніх звернень |
| POST | `/api/v1/tickets/{ticket_id}/approve/` | Staff-сесія + CSRF | Погоджує чернетку (можна передати `{"message":"..."}`) |
| POST | `/api/v1/tickets/{ticket_id}/reject/` | Staff-сесія + CSRF | Відхиляє чернетку, **без доставки** |
| GET | `/health/` | Публічно | Перевірка з'єднання з БД |

Django Admin та операторський UI використовують сесію / CSRF. Анонімні користувачі й звичайні (не `staff`) облікові записи не можуть переглядати клієнтські дані.

## Обробка надійності та захист від дублікатів

**Webhook:** Транзакція PostgreSQL створює `Ticket` і `WebhookEvent`. Поле `event_id` унікальне, так само як `ticket_id`. Повтор тієї самої події → 202, без нової генерації. Спроба повторити той самий `event_id` з іншим payload або змінити вміст існуючого `ticket_id` → 409. Валідація обмежує розміри полів і дозволені вузли callback.

**Фонова обробка:** Celery Beat сканує PostgreSQL кожні 3 секунди й планує задачі, що залишилися в черзі (зокрема після збою Redis). Worker використовує транзакції з `SELECT FOR UPDATE` і UUID-токени, тому одночасні задачі не переписують одна одну. Зависла генерація відновлюється після 120 секунд; зникла доставка — після 45 секунд.

**LLM:** Одне вікно rate limit — до **60 викликів за 60 секунд** на весь сервіс (Redis Lua + sliding window). Не включено реальних API-запитів без ключа; mock режим працює із затримкою `MOCK_MIN_DELAY=5`, `MOCK_MAX_DELAY=30` секунд. Після 3 помилок генерація отримує стан `generation_failed` і **не губиться** з БД. Prompt injection обмежується тим, що і текст клієнта, і статті KB вважаються недовіреними даними; кожна відповідь потребує ручного погодження.

**Delivery:** Надсилання тільки після переходу у `approved`. Створюється один `Delivery` на тикет із постійним `Idempotency-Key`. Повтори при HTTP 5xx/429 або помилці мережі здійснюються із backoff; HTTP 4xx (крім 429) позначаються постійною помилкою. Mock Helpdesk дедуплікує по `Idempotency-Key` у власному SQLite-сховищі. Для зовнішнього реального Helpdesk гарантія «не отримати двічі» **залежить від підтримки ідемпотентності на його боці** — лише мережевим HTTP-клієнтом забезпечити exactly-once неможливо.

**Навантаження:** 500 нових webhook за 10 хвилин приймаються без очікування LLM, за наявності ресурсів PostgreSQL. Celery worker налаштований на 24 I/O-потоки для затримки 5–30 секунд; глобальна квота LLM не перевищує 60/хв. Немає твердження, що всі 500 LLM-відповідей завершаться за 10 хвилин: фактична пропускна здатність залежить від затримки LLM, квоти й ресурсів.

## Режим реального LLM

У `.env` встановіть:

```env
LLM_MODE=openai
OPENAI_API_KEY=власний_ключ
OPENAI_MODEL=gpt-4.1-mini
```

Далі:

```powershell
docker compose up -d --force-recreate web worker beat
```

Сервіс використовує Chat Completions API із тайм-аутом 35 с, передає релевантні статті та текст повідомлення. Не логує ключ або вміст відповіді. Перш ніж використовувати реальні дані клієнтів, узгодьте обробку персональних даних стороннім LLM-провайдером.

## Тести й інструменти

Запуск в Docker (тести користуються окремою тестовою PostgreSQL БД):

```powershell
docker compose exec web python manage.py check
docker compose exec web python manage.py test tests --verbosity 2
# Або одним скриптом:
powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1
```

Репозиторій містить автоматичні тести: автентифікація, валідація та дедуплікація webhook, конфліктні події, 500 записів, пошук KB, генерація, підтвердження/відхилення, повторна доставка, відновлення після збоїв.

**Обмеження перевірки:** у середовищі складання архіву Django-залежності неможливо завантажити через недоступність мережі, тому виконано синтаксичну перевірку Python; повний запуск Django-тестів і `docker compose up` необхідно виконати на вашому ПК. Це не варто плутати із «тести пройшли».

## Безпека та конфігурація

- `.env` виключено з Git та Docker build context. Усі випадкові секрети створює `scripts/setup.ps1`.
- Система з Docker Compose доступна **лише на `127.0.0.1`**, а не у публічному інтернеті.
- `DJANGO_DEBUG=0` за замовчуванням; обов'язкова перевірка наявності сильних ключів при старті.
- Необхідна операторська автентифікація й CSRF-захист; webhook захищено спільним секретом.
- `reply_url` — лише з `REPLY_ALLOWED_HOSTS`, заборонені вбудовані credentials, fragments та нестандартні порти. Для реальної інтеграції необхідний `https://` і розширена перевірка DNS/IP (щоб унеможливити DNS-rebinding), а також секрет підпису запитів за специфікацією зовнішнього Helpdesk.
- У реальному продакшні потрібен HTTPS reverse proxy, `SESSION_COOKIE_SECURE=1`, `CSRF_COOKIE_SECURE=1`, правильні `DJANGO_ALLOWED_HOSTS` / `DJANGO_CSRF_TRUSTED_ORIGINS`, резервні копії PostgreSQL, обмеження доступу до панелі, централізовані логи та спостережність.
- База знань містить **демонстраційні, вигадані інструкції** для умовного продукту — це не документація реально існуючої платформи.

## Структура

```text
config/                   Django settings, URL routing, Celery
helpdesk/                 Models, DRF serializers/views, KB, worker, state machine
helpdesk/management/      seed_kb, bootstrap_operator
helpdesk/migrations/      Стартова міграція PostgreSQL
mock_helpdesk/            Сервіс емуляції прийому відповіді з SQLite дедуплікацією
templates/                Вебкабінет, форма входу
nginx/                    Reverse proxy
scripts/                  Windows setup, demo request, checks
tests/                    Тести API та workflow
compose.yml               Docker Compose
Dockerfile                Python/Gunicorn application
.env.example              Шаблон конфігурації без секретів
CLAUDE.md                 Нотатки для coding agents
```

## Git / доставка

Архів містить історію змістовних локальних Git-комітів. **Репозиторій не опубліковано в GitHub і не виконано публічний деплой.** Після перевірки на власному ПК можна створити GitHub-репозиторій та зробити push звичайним `git remote add origin ...`, `git push -u origin main` (без squash).

Щоб зупинити тестову систему, використовуйте `docker compose down` — дані бази і mock Helpdesk залишаться у Docker volumes. `docker compose down -v` **видалить дані без можливості відновлення**, тому не використовуйте його випадково.
