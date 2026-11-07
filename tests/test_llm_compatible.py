from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from helpdesk.llm import ProviderError, generate


@override_settings(
    LLM_MODE="openai_compatible",
    LLM_BASE_URL="https://llm.example.test/v1/",
    LLM_API_KEY="test-token",
    LLM_MODEL="provider/model-a",
)
class OpenAICompatibleTests(SimpleTestCase):
    @patch("helpdesk.llm.httpx.post")
    def test_uses_configured_url_model_and_key(self, post):
        post.return_value.json.return_value = {
            "choices": [{"message": {"content": "Підготовлена відповідь"}}],
        }

        result = generate("Питання клієнта", [])

        self.assertEqual(result, "Підготовлена відповідь")
        self.assertEqual(post.call_args.args[0], "https://llm.example.test/v1/chat/completions")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer test-token")
        self.assertEqual(post.call_args.kwargs["json"]["model"], "provider/model-a")
        self.assertFalse(post.call_args.kwargs["follow_redirects"])

    @override_settings(LLM_API_KEY="")
    @patch("helpdesk.llm.httpx.post")
    def test_local_provider_can_omit_api_key(self, post):
        post.return_value.json.return_value = {
            "choices": [{"message": {"content": "Локальна відповідь"}}],
        }

        self.assertEqual(generate("Питання", []), "Локальна відповідь")
        self.assertEqual(post.call_args.kwargs["headers"], {})

    @override_settings(LLM_BASE_URL="file:///etc/passwd")
    @patch("helpdesk.llm.httpx.post")
    def test_rejects_non_http_base_url(self, post):
        with self.assertRaises(ProviderError):
            generate("Питання", [])
        post.assert_not_called()

    @override_settings(LLM_MODEL="")
    @patch("helpdesk.llm.httpx.post")
    def test_requires_model(self, post):
        with self.assertRaises(ProviderError):
            generate("Питання", [])
        post.assert_not_called()


@override_settings(
    LLM_MODE="mock", LLM_BASE_URL="http://llm-api/v1",
    LLM_API_KEY="local-gateway-token", LLM_MODEL="local-main",
    MOCK_MIN_DELAY=5, MOCK_MAX_DELAY=30,
)
class MockLLMTests(SimpleTestCase):
    @patch("helpdesk.llm.httpx.post")
    @patch("helpdesk.llm.time.sleep")
    @patch("helpdesk.llm.time.monotonic", side_effect=[10.0, 11.0])
    @patch("helpdesk.llm.random.uniform", return_value=12.5)
    def test_no_cloud_key_mode_calls_local_gateway_but_uses_static_draft(self, uniform, monotonic, sleep, post):
        article = SimpleNamespace(title="Довідка", content="Інструкція з бази знань")
        post.return_value.status_code = 200
        post.return_value.json.return_value = {
            "choices": [{"message": {"content": "Цю відповідь навмисно ігноруємо"}}],
        }

        draft = generate("Питання", [article])

        self.assertEqual(draft, "Вітаємо! Дякуємо за звернення. Щодо вашого питання: Інструкція з бази знань Якщо проблема залишилась, надішліть, будь ласка, деталі.")
        uniform.assert_called_once_with(5, 30)
        sleep.assert_called_once_with(11.5)
        self.assertEqual(post.call_args.args[0], "http://llm-api/v1/chat/completions")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer local-gateway-token")
        self.assertEqual(post.call_args.kwargs["json"]["model"], "local-main")
        self.assertEqual(post.call_args.kwargs["timeout"], 12.5)

    @override_settings(LLM_BASE_URL="")
    @patch("helpdesk.llm.httpx.post")
    @patch("helpdesk.llm.time.sleep")
    @patch("helpdesk.llm.time.monotonic", side_effect=[1.0, 1.0])
    @patch("helpdesk.llm.random.uniform", return_value=5.0)
    def test_mock_mode_still_works_offline_without_gateway(self, uniform, monotonic, sleep, post):
        self.assertIn("Дякуємо", generate("Питання", []))
        post.assert_not_called()
        sleep.assert_called_once_with(5.0)
