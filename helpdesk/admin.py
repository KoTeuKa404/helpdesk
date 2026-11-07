from django.contrib import admin
from django.contrib.admin import AdminSite

from .models import Delivery, KnowledgeArticle, Ticket, WebhookEvent


class RootAdminSite(AdminSite):
    def has_permission(self, request):
        user = request.user
        return user.is_active and user.is_superuser and user.get_username() == "adminroot"


admin_site = RootAdminSite(name="admin")


class ReadOnlyAuditAdmin:
    """Expose operational records for inspection, never for mutation via Admin."""

    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class WebhookEventInline(admin.TabularInline):
    model = WebhookEvent
    extra = 0
    can_delete = False
    fields = ("event_id", "payload_hash", "created_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


class DeliveryInline(admin.StackedInline):
    model = Delivery
    extra = 0
    can_delete = False
    fields = (
        "status", "attempts", "last_status_code", "last_error",
        "idempotency_key", "next_attempt_at", "created_at", "updated_at",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Ticket, site=admin_site)
class TicketAdmin(ReadOnlyAuditAdmin, admin.ModelAdmin):
    list_display = ("ticket_id", "customer_email", "status", "delivery_state", "created_at")
    list_select_related = ("delivery",)
    search_fields = ("ticket_id", "customer_email", "message", "draft", "approved_message")
    list_filter = ("status", "created_at")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    inlines = (DeliveryInline, WebhookEventInline)
    readonly_fields = (
        "ticket_id", "customer_email", "message", "reply_url", "status",
        "draft", "approved_message", "knowledge_sources", "knowledge_context",
        "generation_started_at", "generation_attempts", "generation_error",
        "created_at", "updated_at",
    )
    fieldsets = (
        ("Звернення", {"fields": ("ticket_id", "customer_email", "status", "created_at", "updated_at")}),
        ("Вхідне повідомлення", {"fields": ("message", "reply_url")}),
        ("Відповіді", {"fields": ("draft", "approved_message")}),
        ("RAG: використані матеріали бази знань", {"fields": ("knowledge_sources", "knowledge_context")}),
        ("Генерація", {"fields": ("generation_started_at", "generation_attempts", "generation_error")}),
    )

    @admin.display(description="Доставка", ordering="delivery__status")
    def delivery_state(self, obj):
        try:
            return obj.delivery.get_status_display()
        except Delivery.DoesNotExist:
            return "—"

    def has_add_permission(self, request):
        return False


@admin.register(KnowledgeArticle, site=admin_site)
class KnowledgeArticleAdmin(admin.ModelAdmin):
    list_display = ("slug", "title", "created_at")
    search_fields = ("slug", "title", "content")
    readonly_fields = ("created_at",)


@admin.register(Delivery, site=admin_site)
class DeliveryAdmin(ReadOnlyAuditAdmin, admin.ModelAdmin):
    list_display = ("ticket", "status", "attempts", "last_status_code", "updated_at")
    list_filter = ("status", "updated_at")
    search_fields = ("ticket__ticket_id", "ticket__customer_email", "last_error")
    readonly_fields = tuple(field.name for field in Delivery._meta.fields)

    def has_add_permission(self, request):
        return False


@admin.register(WebhookEvent, site=admin_site)
class WebhookEventAdmin(ReadOnlyAuditAdmin, admin.ModelAdmin):
    list_display = ("event_id", "ticket", "created_at")
    search_fields = ("event_id", "ticket__ticket_id", "ticket__customer_email")
    readonly_fields = tuple(field.name for field in WebhookEvent._meta.fields)

    def has_add_permission(self, request):
        return False
