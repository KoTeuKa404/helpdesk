"""Database state machine; Celery is delivery optimization, not source of truth."""
import logging
import secrets
import uuid
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from celery import shared_task
import httpx
import redis
from .models import Ticket, Delivery
from .knowledge import retrieve
from .llm import generate

log = logging.getLogger(__name__)
RETRY_DELAYS = [5, 15, 45, 120, 300]
RATE_SCRIPT = """
local key = KEYS[1]
local current = tonumber(ARGV[1])
redis.call('ZREMRANGEBYSCORE', key, '-inf', current - 60000)
if redis.call('ZCARD', key) >= 60 then return 0 end
redis.call('ZADD', key, current, ARGV[2])
redis.call('EXPIRE', key, 65)
return 1
"""

def reserve_llm_slot():
    client = redis.Redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=2, socket_timeout=2)
    now = round(timezone.now().timestamp() * 1000)
    return bool(client.eval(RATE_SCRIPT, 1, "helpdesk:llm:rate-window", now, secrets.token_hex(16)))

@shared_task(name="helpdesk.generate_draft")
def generate_draft(ticket_pk):
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update().filter(pk=ticket_pk).first()
        if ticket is None or ticket.status != Ticket.Status.QUEUED:
            return
        ticket.status = Ticket.Status.GENERATING
        ticket.generation_started_at = timezone.now()
        ticket.generation_token = token = uuid.uuid4()
        ticket.generation_attempts += 1
        ticket.save(update_fields=["status", "generation_started_at", "generation_token", "generation_attempts", "updated_at"])
    try:
        if not reserve_llm_slot():
            with transaction.atomic():
                current = Ticket.objects.select_for_update().get(pk=ticket_pk)
                if current.generation_token == token:
                    current.status = Ticket.Status.QUEUED
                    current.generation_attempts -= 1
                    current.save(update_fields=["status", "generation_attempts", "updated_at"])
            return
        articles = retrieve(ticket.message)
        draft = generate(ticket.message, articles)
        with transaction.atomic():
            current = Ticket.objects.select_for_update().get(pk=ticket_pk)
            if current.generation_token != token or current.status != Ticket.Status.GENERATING:
                return
            current.draft = draft[:5000]
            current.knowledge_sources = [{"slug": x.slug, "title": x.title} for x in articles]
            current.knowledge_context = [
                {"slug": x.slug, "title": x.title, "content": x.content}
                for x in articles
            ]
            current.generation_error = ""
            current.status = Ticket.Status.REVIEW
            current.save(update_fields=["draft", "knowledge_sources", "knowledge_context", "generation_error", "status", "updated_at"])
    except Exception as exc:
        log.warning("Generation failed for ticket %s: %s", ticket_pk, type(exc).__name__)
        with transaction.atomic():
            current = Ticket.objects.select_for_update().get(pk=ticket_pk)
            if current.generation_token != token:
                return
            current.generation_error = f"Provider error ({type(exc).__name__})"
            current.status = (Ticket.Status.GENERATION_FAILED if current.generation_attempts >= 3
                              else Ticket.Status.QUEUED)
            current.save(update_fields=["generation_error", "status", "updated_at"])

@shared_task(name="helpdesk.send_delivery")
def send_delivery(ticket_pk):
    with transaction.atomic():
        item = Delivery.objects.select_for_update().select_related("ticket").filter(ticket_id=ticket_pk).first()
        if item is None or item.status not in (Delivery.Status.PENDING, Delivery.Status.FAILED):
            return
        if item.next_attempt_at and item.next_attempt_at > timezone.now():
            return
        item.status = Delivery.Status.SENDING
        item.sending_started_at = timezone.now()
        item.sending_token = token = uuid.uuid4()
        item.attempts += 1
        item.save(update_fields=["status", "sending_started_at", "sending_token", "attempts", "updated_at"])
        reply_url = item.ticket.reply_url
        payload = {"ticket_id": item.ticket.ticket_id, "message": item.ticket.approved_message}
        key = item.idempotency_key
    try:
        # Destination is validated during webhook ingestion, but records may be
        # imported/edited later. Deny unsafe destinations at delivery time too.
        from .serializers import WebhookSerializer
        validator = WebhookSerializer()
        validator.validate_reply_url(reply_url)
        with httpx.Client(timeout=10.0, follow_redirects=False, trust_env=False) as client:
            response = client.post(reply_url, json=payload, headers={"Idempotency-Key": key})
        code = response.status_code
        success = code == 201 or (code == 200 and response.headers.get("X-Idempotent-Replay") == "1")
        permanent = 400 <= code < 500 and code != 429
        error = "" if success else f"Helpdesk returned HTTP {code}"
    except httpx.HTTPError as exc:
        code, success, permanent = None, False, False
        error = f"Network error ({type(exc).__name__})"
    except Exception as exc:
        # Invalid/unallowlisted destination: never attempt repeated network calls.
        code, success, permanent = None, False, True
        error = f"Delivery blocked ({type(exc).__name__})"
    with transaction.atomic():
        item = Delivery.objects.select_for_update().select_related("ticket").get(ticket_id=ticket_pk)
        if item.sending_token != token:
            return
        item.last_error = error
        item.last_status_code = code
        item.next_attempt_at = None
        if success:
            item.status = Delivery.Status.SENT
            item.ticket.status = Ticket.Status.DELIVERED
        elif permanent or item.attempts >= len(RETRY_DELAYS):
            item.status = Delivery.Status.PERMANENT_FAILED
            item.ticket.status = Ticket.Status.DELIVERY_FAILED
        else:
            item.status = Delivery.Status.FAILED
            item.next_attempt_at = timezone.now() + timedelta(seconds=RETRY_DELAYS[min(item.attempts-1, len(RETRY_DELAYS)-1)])
        item.ticket.save(update_fields=["status", "updated_at"])
        item.save(update_fields=["last_error", "last_status_code", "status", "next_attempt_at", "updated_at"])

@shared_task(name="helpdesk.recover_pending")
def recover_pending():
    """Repair Redis outages, worker crashes, and delayed deliveries."""
    now = timezone.now()
    with transaction.atomic():
        stale_tickets = Ticket.objects.select_for_update(skip_locked=True).filter(
            status=Ticket.Status.GENERATING, generation_started_at__lt=now - timedelta(seconds=120))[:100]
        for ticket in stale_tickets:
            ticket.status = Ticket.Status.QUEUED if ticket.generation_attempts < 3 else Ticket.Status.GENERATION_FAILED
            ticket.save(update_fields=["status", "updated_at"])
        stale_deliveries = Delivery.objects.select_for_update(skip_locked=True).filter(
            status=Delivery.Status.SENDING, sending_started_at__lt=now - timedelta(seconds=45))[:100]
        for delivery in stale_deliveries:
            delivery.status = Delivery.Status.FAILED
            delivery.next_attempt_at = now
            delivery.save(update_fields=["status", "next_attempt_at", "updated_at"])
    # Record enqueue leases, so frequent sweeps never flood Redis with duplicate tasks.
    generation_ids = []
    delivery_ids = []
    with transaction.atomic():
        due = Q(last_enqueued_at__isnull=True) | Q(last_enqueued_at__lte=now - timedelta(seconds=15))
        for ticket in Ticket.objects.select_for_update(skip_locked=True).filter(status=Ticket.Status.QUEUED).filter(due)[:100]:
            ticket.last_enqueued_at = now
            ticket.save(update_fields=["last_enqueued_at", "updated_at"])
            generation_ids.append(ticket.pk)
        for item in Delivery.objects.select_for_update(skip_locked=True).filter(
                status__in=[Delivery.Status.PENDING, Delivery.Status.FAILED]).filter(
                Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now)).filter(due)[:100]:
            item.last_enqueued_at = now
            item.save(update_fields=["last_enqueued_at", "updated_at"])
            delivery_ids.append(item.ticket_id)
    from .service import enqueue_safely
    for pk in generation_ids:
        enqueue_safely(generate_draft, pk)
    for pk in delivery_ids:
        enqueue_safely(send_delivery, pk)
