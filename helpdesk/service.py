"""State transitions and safe message publication."""
import hashlib
import json
import logging
from django.db import transaction
from .models import Ticket, WebhookEvent, Delivery

logger = logging.getLogger(__name__)

def enqueue_safely(task, ticket_pk):
    try:
        task.delay(ticket_pk)
    except Exception:
        # DB state is durable; periodic recovery will enqueue after Redis returns.
        logger.exception("Broker unavailable; periodic recovery will retry")

def ingest(data):
    """Persist event and ticket in one transaction; same event never creates new work.

    event_id identifies the delivery event, ticket_id identifies a single customer
    message in this small demo. Subsequent identical events are safe replays.
    """
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    fields = ("customer_email", "message", "reply_url")
    with transaction.atomic():
        # Check an event replay *before* any ticket insert. This prevents
        # identical retries from accidentally creating a new ticket.
        existing = WebhookEvent.objects.select_related("ticket").filter(event_id=data["event_id"]).first()
        if existing is not None:
            t = existing.ticket
            if (existing.payload_hash != digest or t.ticket_id != data["ticket_id"] or
                    any(getattr(t, name) != data[name] for name in fields)):
                return None, False
            return t, False
        ticket, created = Ticket.objects.get_or_create(
            ticket_id=data["ticket_id"],
            defaults={name: data[name] for name in fields},
        )
        # Distinct events may refer to the same ticket only with the exact
        # immutable content, so no delivered message is silently replaced.
        if any(getattr(ticket, name) != data[name] for name in fields):
            return None, False
        event, new_event = WebhookEvent.objects.get_or_create(
            event_id=data["event_id"], defaults={"ticket": ticket, "payload_hash": digest},
        )
        if event.payload_hash != digest or event.ticket_id != ticket.pk:
            if created and not WebhookEvent.objects.filter(ticket=ticket).exists():
                ticket.delete()  # Undo a losing concurrent conflict if safe.
            return None, False
        return ticket, new_event

def approve(ticket_id, message):
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update().get(ticket_id=ticket_id)
        if ticket.status != Ticket.Status.REVIEW:
            return None
        ticket.approved_message = (message or ticket.draft).strip()
        if not ticket.approved_message:
            return None
        ticket.status = Ticket.Status.APPROVED
        ticket.save(update_fields=["approved_message", "status", "updated_at"])
        delivery = Delivery.objects.create(
            ticket=ticket,
            idempotency_key="ticket:" + hashlib.sha256(ticket.ticket_id.encode()).hexdigest(),
        )
        return delivery

def reject(ticket_id):
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update().get(ticket_id=ticket_id)
        if ticket.status != Ticket.Status.REVIEW:
            return False
        ticket.status = Ticket.Status.REJECTED
        ticket.save(update_fields=["status", "updated_at"])
        return True
