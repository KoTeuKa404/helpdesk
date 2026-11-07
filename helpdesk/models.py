import uuid
from django.db import models

class KnowledgeArticle(models.Model):
    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=160)
    content = models.TextField()
    keywords = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class Ticket(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        GENERATING = "generating", "Generating"
        REVIEW = "review", "Needs approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        DELIVERED = "delivered", "Delivered"
        GENERATION_FAILED = "generation_failed", "Generation failed"
        DELIVERY_FAILED = "delivery_failed", "Delivery failed"

    ticket_id = models.CharField(max_length=100, unique=True)
    customer_email = models.EmailField(max_length=254)
    message = models.TextField(max_length=5000)
    reply_url = models.URLField(max_length=1024)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.QUEUED, db_index=True)
    draft = models.TextField(blank=True)
    approved_message = models.TextField(blank=True)
    knowledge_sources = models.JSONField(default=list)
    generation_started_at = models.DateTimeField(null=True, blank=True)
    generation_token = models.UUIDField(null=True, blank=True)
    last_enqueued_at = models.DateTimeField(null=True, blank=True)
    generation_attempts = models.PositiveSmallIntegerField(default=0)
    generation_error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.ticket_id

class WebhookEvent(models.Model):
    event_id = models.CharField(max_length=120, unique=True)
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="events")
    payload_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

class Delivery(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        PERMANENT_FAILED = "permanent_failed", "Permanent failed"

    ticket = models.OneToOneField(Ticket, related_name="delivery", on_delete=models.CASCADE)
    idempotency_key = models.CharField(max_length=180, unique=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    sending_started_at = models.DateTimeField(null=True, blank=True)
    sending_token = models.UUIDField(null=True, blank=True)
    last_enqueued_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=300, blank=True)
    last_status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
