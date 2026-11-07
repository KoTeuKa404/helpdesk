"""Generation, human moderation, idempotent delivery and retry."""
from unittest.mock import MagicMock, patch
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from helpdesk.models import Ticket, Delivery
from helpdesk.service import ingest
from helpdesk.tasks import generate_draft, send_delivery, recover_pending
from helpdesk.management.commands.seed_kb import ARTICLES
from helpdesk.models import KnowledgeArticle
from helpdesk.knowledge import retrieve

SAMPLE = {
    "event_id": "evt-1", "ticket_id": "T-1042", "customer_email": "user@example.com",
    "message": "Не можу експортувати звіт у PDF",
    "reply_url": "http://mock-helpdesk:8001/tickets/T-1042/replies",
}

@override_settings(REPLY_ALLOWED_HOSTS={"mock-helpdesk"})
class WorkflowTests(TestCase):
    def setUp(self):
        self.ticket, _ = ingest(SAMPLE)
        self.operator = get_user_model().objects.create_user(
            username="operator", password="testpass123", is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.operator)

    def ready(self):
        with patch("helpdesk.tasks.reserve_llm_slot", return_value=True), \
                patch("helpdesk.tasks.generate", return_value="Чернетка про PDF") as model:
            generate_draft(self.ticket.pk)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Ticket.Status.REVIEW)
        model.assert_called_once()

    def test_retrieval_uses_relevant_articles(self):
        for slug, title, content, keywords in ARTICLES:
            KnowledgeArticle.objects.create(slug=slug, title=title, content=content, keywords=keywords)
        matches = retrieve(SAMPLE["message"])
        self.assertGreater(len(matches), 0)
        self.assertEqual(matches[0].slug, "export-pdf")

    def test_generation_requires_human_approval(self):
        self.ready()
        self.assertEqual(Delivery.objects.count(), 0)
        self.assertEqual(self.ticket.approved_message, "")
        response = self.client.post(reverse("approve", kwargs={"ticket_id": self.ticket.ticket_id}),
                                    {"message": "Ось інструкція."}, format="json")
        self.assertEqual(response.status_code, 200)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Ticket.Status.APPROVED)
        self.assertEqual(Delivery.objects.count(), 1)
        self.assertEqual(self.ticket.approved_message, "Ось інструкція.")
        repeat = self.client.post(reverse("approve", kwargs={"ticket_id": self.ticket.ticket_id}),
                                  {"message": "Надіслати вдруге"}, format="json")
        self.assertEqual(repeat.status_code, 409)
        self.assertEqual(Delivery.objects.count(), 1)

    def test_rejection_never_sends(self):
        self.ready()
        response = self.client.post(reverse("reject", kwargs={"ticket_id": self.ticket.ticket_id}), {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Ticket.Status.REJECTED)
        self.assertEqual(Delivery.objects.count(), 0)

    def test_delivery_201_and_duplicate_guard(self):
        self.ready()
        self.client.post(reverse("approve", kwargs={"ticket_id": self.ticket.ticket_id}), {}, format="json")
        response = MagicMock(status_code=201, headers={})
        with patch("helpdesk.tasks.httpx.Client") as client:
            client.return_value.__enter__.return_value.post.return_value = response
            send_delivery(self.ticket.pk)
            send_delivery(self.ticket.pk)
            self.assertEqual(client.return_value.__enter__.return_value.post.call_count, 1)
            sent = client.return_value.__enter__.return_value.post.call_args
            self.assertEqual(sent.kwargs["json"]["ticket_id"], self.ticket.ticket_id)
            self.assertTrue(sent.kwargs["headers"]["Idempotency-Key"])
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Ticket.Status.DELIVERED)
        self.assertEqual(Delivery.objects.get().status, Delivery.Status.SENT)

    def test_delivery_5xx_schedules_retry(self):
        self.ready()
        self.client.post(reverse("approve", kwargs={"ticket_id": self.ticket.ticket_id}), {}, format="json")
        with patch("helpdesk.tasks.httpx.Client") as client:
            client.return_value.__enter__.return_value.post.return_value = MagicMock(status_code=503)
            send_delivery(self.ticket.pk)
        delivery = Delivery.objects.get()
        self.assertEqual(delivery.status, Delivery.Status.FAILED)
        self.assertEqual(delivery.attempts, 1)
        self.assertGreater(delivery.next_attempt_at, timezone.now())

    def test_worker_cannot_create_duplicate_drafts(self):
        self.ready()
        with patch("helpdesk.tasks.generate") as gen:
            generate_draft(self.ticket.pk)
            gen.assert_not_called()

    def test_recovery_requeues_queued_work(self):
        with patch("helpdesk.service.enqueue_safely") as enqueue:
            recover_pending()
            self.assertGreaterEqual(enqueue.call_count, 1)
        self.ticket.refresh_from_db()
        self.assertIsNotNone(self.ticket.last_enqueued_at)
