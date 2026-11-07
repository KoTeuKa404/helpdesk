from django.contrib import admin
from .models import KnowledgeArticle, Ticket, Delivery, WebhookEvent

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("ticket_id", "status", "customer_email", "created_at")
    search_fields = ("ticket_id", "customer_email")
    list_filter = ("status",)
    readonly_fields = ("ticket_id", "reply_url", "message", "customer_email")

@admin.register(KnowledgeArticle)
class KnowledgeArticleAdmin(admin.ModelAdmin):
    list_display = ("slug", "title")

@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ("ticket", "status", "attempts", "last_status_code")

@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "ticket", "created_at")
