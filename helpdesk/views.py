import hmac
from django.conf import settings
from django.contrib.auth.decorators import user_passes_test
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from rest_framework import status
from rest_framework import serializers
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from .models import Ticket
from .serializers import WebhookSerializer, TicketSerializer, ApproveSerializer
from .service import ingest, approve, reject


class WebhookAcceptedSerializer(serializers.Serializer):
    ticket_id = serializers.CharField()
    received = serializers.BooleanField()
    duplicate = serializers.BooleanField()


class ApprovalResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    delivery_id = serializers.IntegerField()


class RejectionResponseSerializer(serializers.Serializer):
    status = serializers.CharField(required=False)
    detail = serializers.CharField(required=False)

def is_operator(user):
    return user.is_authenticated and user.is_staff and not user.is_superuser


class IsOperator(BasePermission):
    def has_permission(self, request, view):
        return is_operator(request.user)


@user_passes_test(is_operator, login_url="/accounts/login/")
def dashboard(request):
    return render(request, "helpdesk/dashboard.html")

def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({"status": "ok"})
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)

class HelpdeskWebhook(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "webhook"

    @extend_schema(
        tags=["Helpdesk"],
        request=WebhookSerializer,
        parameters=[OpenApiParameter(
            name="X-Webhook-Secret", type=str, location=OpenApiParameter.HEADER,
            required=True, description="Секрет із WEBHOOK_SECRET у .env.",
        )],
        responses={
            202: WebhookAcceptedSerializer,
            401: OpenApiResponse(description="Невірний секрет webhook"),
            409: OpenApiResponse(description="Конфлікт event_id або ticket_id"),
        },
    )
    def post(self, request):
        presented = request.headers.get("X-Webhook-Secret", "")
        expected = settings.WEBHOOK_SECRET
        if not expected or not hmac.compare_digest(presented, expected):
            return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
        serializer = WebhookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket, new_event = ingest(serializer.validated_data)
        if ticket is None:
            return Response({"detail": "Conflicting event_id"}, status=409)
        return Response({"ticket_id": ticket.ticket_id, "received": True, "duplicate": not new_event}, status=202)

class TicketList(APIView):
    permission_classes = [IsOperator]

    @extend_schema(tags=["Tickets"], responses=TicketSerializer(many=True))
    def get(self, request):
        tickets = Ticket.objects.select_related("delivery").order_by("-created_at")[:1000]
        return Response(TicketSerializer(tickets, many=True).data)

class ApproveTicket(APIView):
    permission_classes = [IsOperator]

    @extend_schema(
        tags=["Tickets"], request=ApproveSerializer, responses={
            200: ApprovalResponseSerializer,
            404: OpenApiResponse(description="Звернення не знайдено"),
            409: OpenApiResponse(description="Звернення не очікує модерації"),
        },
    )
    def post(self, request, ticket_id):
        serializer = ApproveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            delivery = approve(ticket_id, serializer.validated_data.get("message", ""))
        except Ticket.DoesNotExist:
            return Response({"detail": "Not found"}, status=404)
        if delivery is None:
            return Response({"detail": "Ticket is not in review"}, status=409)
        return Response({"status": "approved", "delivery_id": delivery.pk})

class RejectTicket(APIView):
    permission_classes = [IsOperator]

    @extend_schema(
        tags=["Tickets"], request=None, responses={
            200: RejectionResponseSerializer,
            404: OpenApiResponse(description="Звернення не знайдено"),
            409: OpenApiResponse(description="Звернення не очікує модерації"),
        },
    )
    def post(self, request, ticket_id):
        try:
            rejected = reject(ticket_id)
        except Ticket.DoesNotExist:
            return Response({"detail": "Not found"}, status=404)
        return Response({"status": "rejected"} if rejected else {"detail": "Ticket is not in review"},
                        status=200 if rejected else 409)
