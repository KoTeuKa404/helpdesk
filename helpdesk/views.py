import hmac
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle
from .models import Ticket
from .serializers import WebhookSerializer, TicketSerializer, ApproveSerializer
from .service import ingest, approve, reject

@staff_member_required(login_url="/accounts/login/")
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
    permission_classes = [IsAdminUser]

    def get(self, request):
        tickets = Ticket.objects.select_related("delivery").order_by("-created_at")[:1000]
        return Response(TicketSerializer(tickets, many=True).data)

class ApproveTicket(APIView):
    permission_classes = [IsAdminUser]

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
    permission_classes = [IsAdminUser]

    def post(self, request, ticket_id):
        try:
            rejected = reject(ticket_id)
        except Ticket.DoesNotExist:
            return Response({"detail": "Not found"}, status=404)
        return Response({"status": "rejected"} if rejected else {"detail": "Ticket is not in review"},
                        status=200 if rejected else 409)
