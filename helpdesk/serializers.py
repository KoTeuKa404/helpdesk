from urllib.parse import urlsplit
from django.conf import settings
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import Ticket

class WebhookSerializer(serializers.Serializer):
    event_id = serializers.RegexField(r"^[A-Za-z0-9_.:-]{1,120}$", max_length=120)
    ticket_id = serializers.RegexField(r"^[A-Za-z0-9_.:-]{1,100}$", max_length=100)
    customer_email = serializers.EmailField(max_length=254)
    message = serializers.CharField(max_length=5000, trim_whitespace=True, allow_blank=False)
    # A local Docker hostname (mock-helpdesk) is valid for this exercise,
    # though Django URLValidator rejects many single-label service names.
    reply_url = serializers.CharField(max_length=1024, trim_whitespace=True)

    def validate_reply_url(self, value):
        if any(ord(c) < 33 or ord(c) == 127 for c in value):
            raise serializers.ValidationError("Whitespace and control characters are forbidden")
        try:
            parsed = urlsplit(value)
            host = (parsed.hostname or "").lower()
            port = parsed.port
        except ValueError as exc:
            raise serializers.ValidationError("Invalid reply URL") from exc
        if (parsed.scheme not in ("http", "https") or not parsed.path.startswith("/")
                or parsed.username or parsed.password or parsed.fragment or not host
                or host not in settings.REPLY_ALLOWED_HOSTS):
            raise serializers.ValidationError("Reply URL hostname or scheme is not permitted")
        if parsed.scheme != "https" and host != "mock-helpdesk":
            raise serializers.ValidationError("HTTPS is mandatory for real helpdesks")
        if port not in (None, 443, 8001) or (host != "mock-helpdesk" and port not in (None, 443)):
            raise serializers.ValidationError("Unexpected reply URL port")
        return value

class TicketSerializer(serializers.ModelSerializer):
    attempts = serializers.SerializerMethodField()
    delivery_status = serializers.SerializerMethodField()

    class Meta:
        model = Ticket
        fields = ["ticket_id", "customer_email", "message", "status", "draft", "approved_message",
                  "knowledge_sources", "generation_attempts", "generation_error", "attempts", "delivery_status", "created_at", "updated_at"]
        read_only_fields = fields

    @extend_schema_field(serializers.IntegerField())
    def get_attempts(self, obj):
        delivery = getattr(obj, "delivery", None)
        return delivery.attempts if delivery else 0

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_delivery_status(self, obj):
        delivery = getattr(obj, "delivery", None)
        return delivery.status if delivery else None

class ApproveSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=5000, allow_blank=False, trim_whitespace=True, required=False)
