# Generated for the AI-first Helpdesk Django take-home project.
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="KnowledgeArticle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(unique=True)),
                ("title", models.CharField(max_length=160)),
                ("content", models.TextField()),
                ("keywords", models.JSONField(default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="Ticket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ticket_id", models.CharField(max_length=100, unique=True)),
                ("customer_email", models.EmailField(max_length=254)),
                ("message", models.TextField(max_length=5000)),
                ("reply_url", models.URLField(max_length=1024)),
                ("status", models.CharField(choices=[("queued", "Queued"), ("generating", "Generating"), ("review", "Needs approval"), ("approved", "Approved"), ("rejected", "Rejected"), ("delivered", "Delivered"), ("generation_failed", "Generation failed"), ("delivery_failed", "Delivery failed")], db_index=True, default="queued", max_length=32)),
                ("draft", models.TextField(blank=True)),
                ("approved_message", models.TextField(blank=True)),
                ("knowledge_sources", models.JSONField(default=list)),
                ("generation_started_at", models.DateTimeField(blank=True, null=True)),
                ("generation_token", models.UUIDField(blank=True, null=True)),
                ("last_enqueued_at", models.DateTimeField(blank=True, null=True)),
                ("generation_attempts", models.PositiveSmallIntegerField(default=0)),
                ("generation_error", models.CharField(blank=True, max_length=300)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="WebhookEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_id", models.CharField(max_length=120, unique=True)),
                ("payload_hash", models.CharField(max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("ticket", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="helpdesk.ticket")),
            ],
        ),
        migrations.CreateModel(
            name="Delivery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("idempotency_key", models.CharField(max_length=180, unique=True)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("sending", "Sending"), ("sent", "Sent"), ("failed", "Failed"), ("permanent_failed", "Permanent failed")], db_index=True, default="pending", max_length=32)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("next_attempt_at", models.DateTimeField(blank=True, null=True)),
                ("sending_started_at", models.DateTimeField(blank=True, null=True)),
                ("sending_token", models.UUIDField(blank=True, null=True)),
                ("last_enqueued_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, max_length=300)),
                ("last_status_code", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("ticket", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="delivery", to="helpdesk.ticket")),
            ],
        ),
    ]
