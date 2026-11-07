from types import SimpleNamespace
from unittest.mock import patch
import httpx
from django.test import SimpleTestCase, override_settings
from helpdesk.llm import ProviderError, generate


@override_settings(LLM_MODE="gemini", GEMINI_API_KEY="test-key", GEMINI_MODEL="gemini-2.5-flash")
class GeminiTests(SimpleTestCase):
    @patch("helpdesk.llm.httpx.post")
    def test_gemini_draft(self, post):
        post.return_value.json.return_value = {"candidates": [{"content": {
            "parts": [{"text": "Ось відповідь"}]}}]}
        result = generate("Питання", [SimpleNamespace(title="FAQ", content="Факти")])
        self.assertEqual(result, "Ось відповідь")
        self.assertEqual(post.call_args.kwargs["headers"]["x-goog-api-key"], "test-key")
        self.assertIn("FAQ", str(post.call_args.kwargs["json"]))
        self.assertFalse(post.call_args.kwargs["follow_redirects"])

    @patch("helpdesk.llm.httpx.post")
    def test_ignores_thought_parts(self, post):
        post.return_value.json.return_value = {"candidates": [{"content": {"parts": [
            {"text": "Internal reasoning", "thought": True}, {"text": "Відповідь клієнту"},
        ]}}]}
        self.assertEqual(generate("Питання", []), "Відповідь клієнту")

    @patch("helpdesk.llm.httpx.post")
    def test_blocked_response_becomes_provider_error(self, post):
        post.return_value.json.return_value = {"candidates": []}
        with self.assertRaises(ProviderError):
            generate("Питання", [])

    @patch("helpdesk.llm.httpx.post", side_effect=httpx.ConnectError("unavailable"))
    def test_network_failure_becomes_provider_error(self, post):
        with self.assertRaises(ProviderError):
            generate("Питання", [])

    @override_settings(GEMINI_API_KEY="")
    @patch("helpdesk.llm.httpx.post")
    def test_missing_key_does_not_call_provider(self, post):
        with self.assertRaises(ProviderError):
            generate("Питання", [])
        post.assert_not_called()

    @override_settings(GEMINI_MODEL="../../invalid")
    @patch("helpdesk.llm.httpx.post")
    def test_invalid_model_does_not_call_provider(self, post):
        with self.assertRaises(ProviderError):
            generate("Питання", [])
        post.assert_not_called()
