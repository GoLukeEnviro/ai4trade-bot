from unittest.mock import MagicMock, patch

import pytest

import core.llm as llm_module


class TestCreateProvider:
    @patch.object(llm_module, "config", MagicMock(LLM_PROVIDER="claude", CLAUDE_API_KEY="k", CLAUDE_MODEL="m"))
    @patch("core.llm.ClaudeProvider")
    def test_create_provider_claude_default(self, mock_claude):
        provider = llm_module.create_provider()
        mock_claude.assert_called_once()
        assert isinstance(provider, MagicMock)

    @patch.object(llm_module, "config", MagicMock(LLM_PROVIDER="openai", LLM_API_KEY="k", LLM_MODEL="m", LLM_BASE_URL="http://x"))
    @patch("core.llm.OpenAICompatibleProvider")
    def test_create_provider_openai(self, mock_openai):
        provider = llm_module.create_provider()
        mock_openai.assert_called_once()
        assert isinstance(provider, MagicMock)

    @patch.object(llm_module, "config", MagicMock(LLM_PROVIDER="unknown"))
    def test_create_provider_unknown_raises(self):
        with pytest.raises(ValueError, match="Unbekannter LLM-Provider: unknown"):
            llm_module.create_provider()

    @patch.object(llm_module, "config", MagicMock(LLM_PROVIDER="claude", CLAUDE_API_KEY="k", CLAUDE_MODEL="m"))
    @patch("core.llm.ClaudeProvider")
    def test_create_provider_explicit_claude(self, mock_claude):
        llm_module.create_provider(provider="claude")
        mock_claude.assert_called_once()

    @patch.object(llm_module, "config", MagicMock(LLM_PROVIDER="claude", CLAUDE_API_KEY="k", CLAUDE_MODEL="m"))
    @patch("core.llm.OpenAICompatibleProvider")
    def test_create_provider_explicit_openai_overrides_config(self, mock_openai):
        llm_module.create_provider(provider="openai")
        mock_openai.assert_called_once()


class TestClaudeProvider:
    @patch("core.llm.config", MagicMock(CLAUDE_API_KEY="test-key", CLAUDE_MODEL="test-model"))
    @patch("anthropic.Anthropic")
    def test_claude_provider_complete(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Positive")]
        mock_client.messages.create.return_value = mock_response

        provider = llm_module.ClaudeProvider()
        result = provider.complete("Analyze BTC sentiment", max_tokens=100)

        mock_client.messages.create.assert_called_once_with(
            model="test-model",
            messages=[{"role": "user", "content": "Analyze BTC sentiment"}],
            max_tokens=100,
        )
        assert result == "Positive"


class TestOpenAICompatibleProvider:
    @patch("core.llm.config", MagicMock(LLM_API_KEY="test-key", LLM_MODEL="test-model", LLM_BASE_URL="http://localhost"))
    @patch("openai.OpenAI")
    def test_openai_provider_complete(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_choice = MagicMock()
        mock_choice.message.content = "Bullish"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        provider = llm_module.OpenAICompatibleProvider()
        result = provider.complete("What is BTC trend?", max_tokens=150)

        mock_client.chat.completions.create.assert_called_once_with(
            model="test-model",
            messages=[{"role": "user", "content": "What is BTC trend?"}],
            max_tokens=150,
        )
        assert result == "Bullish"
