"""API validation, deduplication and fast acknowledgment tests."""
import time
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from helpdesk.models import Ticket, WebhookEvent

SAMPLE = {
    "event_id": "evt_8f2a", "ticket_id": "T-1042", "customer_email": "user@example.com",
    "message": "Не можу експортувати звіт у PDF",
    "reply_url": "http://mock-helpdesk:8001/tickets/T-1042/replies",
}

@override_settings(WEBHOOK_SECRET="local-test-secret", REPLY_ALLOWED_HOSTS={"mock-helpdesk"})
class WebhookTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.endpoint = reverse("helpdesk-webhook")

    def post(self, payload=None, secret="local-test-secret"):
        return self.client.post(self.endpoint, data=payload or SAMPLE,
                                format="json", HTTP_X_WEBHOOK_SECRET=secret)

    def test_rejects_missing_or_wrong_secret(self):
        self.assertEqual(self.post(secret="wrong").status_code, 401)
        self.assertEqual(Ticket.objects.count(), 0)

    def test_fast_ack_and_duplicate_replay(self):
        start = time.perf_counter()
        first = self.post()
        elapsed = time.perf_counter() - start
        self.assertEqual(first.status_code, 202)
        self.assertLess(elapsed, 2)
        self.assertFalse(first.data["duplicate"])
        self.assertEqual(self.post().status_code, 202)
        self.assertTrue(self.post().data["duplicate"])
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertEqual(WebhookEvent.objects.count(), 1)
        self.assertEqual(Ticket.objects.get().status, Ticket.Status.QUEUED)

    def test_conflicting_event_rejected(self):
        self.assertEqual(self.post().status_code, 202)
        altered = {**SAMPLE, "message": "Зовсім інший текст"}
        self.assertEqual(self.post(altered).status_code, 409)
        self.assertEqual(WebhookEvent.objects.count(), 1)
        self.assertEqual(Ticket.objects.get().message, SAMPLE["message"])

    def test_new_event_id_same_ticket_cannot_change_message(self):
        self.assertEqual(self.post().status_code, 202)
        altered = {**SAMPLE, "event_id": "evt_2", "message": "Інше звернення"}
        self.assertEqual(self.post(altered).status_code, 409)
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertEqual(Ticket.objects.get().message, SAMPLE["message"])
        self.assertEqual(WebhookEvent.objects.count(), 1)

    def test_new_event_id_same_ticket_identical_payload_is_not_new_ticket(self):
        self.assertEqual(self.post().status_code, 202)
        self.assertEqual(self.post({**SAMPLE, "event_id": "evt_2"}).status_code, 202)
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertEqual(WebhookEvent.objects.count(), 2)

    def test_destination_ssrf_guard(self):
        for destination in (
            "http://127.0.0.1:8001/private",
            "http://localhost:8001/private",
            "http://169.254.169.254/latest/meta-data/",
            "https://external.example/submit",
            "http://mock-helpdesk:4444/replies",
        ):
            payload = {**SAMPLE, "reply_url": destination}
            with self.subTest(destination=destination):
                self.assertEqual(self.post(payload).status_code, 400)
        self.assertEqual(Ticket.objects.count(), 0)

    def test_malformed_payload_not_stored(self):
        invalid = {**SAMPLE, "event_id": "some bad id", "message": ""}
        self.assertEqual(self.post(invalid).status_code, 400)
        self.assertEqual(Ticket.objects.count(), 0)

    def test_burst_ingestion_retains_500_unique_events(self):
        # Exercise the public webhook endpoint: it persists events without waiting
        # for a broker, LLM call, or delivery task.
        started = time.perf_counter()
        for i in range(500):
            item = {**SAMPLE, "event_id": f"e-{i}", "ticket_id": f"T-{i}"}
            request_started = time.perf_counter()
            response = self.post(item)
            self.assertEqual(response.status_code, 202)
            self.assertFalse(response.data["duplicate"])
            self.assertLess(time.perf_counter() - request_started, 2)
        self.assertLess(time.perf_counter() - started, 600)
        self.assertEqual(Ticket.objects.count(), 500)
        self.assertEqual(WebhookEvent.objects.count(), 500)

    def test_api_requires_staff_session(self):
        self.assertEqual(self.client.get(reverse("tickets")).status_code, 403)
        user = get_user_model().objects.create_user(username="regular", password="testpass123")
        self.client.force_authenticate(user=user)
        self.assertEqual(self.client.get(reverse("tickets")).status_code, 403)
