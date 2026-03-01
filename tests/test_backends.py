"""
Tests for LLM Backends
LLM 백엔드 테스트
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backends import (
    AnthropicBackend,
    LLMBackend,
    LLMConfig,
    LLMResponse,
    LLMRouter,
    OllamaBackend,
    OpenAIBackend,
)
from backends.base import BackendStatus
from backends.router import RouterConfig, RouterMetrics


class TestLLMConfig:

    def test_default_config(self):
        config = LLMConfig(model="test-model")
        assert config.model == "test-model"
        assert config.temperature == 0.1
        assert config.max_tokens == 2000
        assert config.timeout == 60

    def test_custom_config(self):
        config = LLMConfig(
            model="custom-model",
            temperature=0.5,
            max_tokens=4000,
            timeout=120
        )
        assert config.temperature == 0.5
        assert config.max_tokens == 4000

    def test_extra_params(self):
        config = LLMConfig(model="m", extra_params={"foo": "bar"})
        assert config.extra_params["foo"] == "bar"

    def test_max_retries(self):
        config = LLMConfig(model="m", max_retries=5)
        assert config.max_retries == 5


class TestLLMResponse:

    def test_success_response(self):
        response = LLMResponse(
            content="Test response",
            model="test-model",
            backend_name="test",
            success=True,
            latency_ms=100.5
        )

        assert response.success is True
        assert response.content == "Test response"
        assert response.error_message == ""

    def test_error_response(self):
        response = LLMResponse(
            content="",
            model="test-model",
            backend_name="test",
            success=False,
            latency_ms=0,
            error_message="Connection failed"
        )

        assert response.success is False
        assert response.error_message == "Connection failed"

    def test_to_dict(self):
        response = LLMResponse(
            content="Test",
            model="model",
            backend_name="backend",
            success=True,
            latency_ms=50.0,
            tokens_used=100
        )

        result = response.to_dict()
        assert result["content"] == "Test"
        assert result["success"] is True
        assert result["tokens_used"] == 100
        assert "timestamp" in result


class TestBackendStatus:
    def test_enum_values(self):
        assert BackendStatus.HEALTHY.value == "healthy"
        assert BackendStatus.DEGRADED.value == "degraded"
        assert BackendStatus.UNHEALTHY.value == "unhealthy"
        assert BackendStatus.UNKNOWN.value == "unknown"


class TestLLMBackendBase:
    """Tests for the base LLMBackend abstract class methods."""

    def _make_concrete_backend(self, config=None):
        """Create a concrete subclass for testing base class methods."""
        class ConcreteBackend(LLMBackend):
            @property
            def name(self):
                return "concrete"

            async def health_check(self):
                return True

            async def generate(self, prompt, system_prompt=None, **kwargs):
                return LLMResponse(
                    content="ok",
                    model=self.config.model,
                    backend_name=self.name,
                    success=True,
                    latency_ms=1.0,
                )

        return ConcreteBackend(config or LLMConfig(model="test"))

    def test_initial_status(self):
        backend = self._make_concrete_backend()
        assert backend.status == BackendStatus.UNKNOWN

    def test_health_score_no_requests(self):
        backend = self._make_concrete_backend()
        assert backend.health_score == 1.0

    def test_health_score_with_errors(self):
        backend = self._make_concrete_backend()
        backend._request_count = 10
        backend._error_count = 3
        assert backend.health_score == pytest.approx(0.7)

    def test_update_status_healthy(self):
        backend = self._make_concrete_backend()
        backend.update_status(True)
        assert backend.status == BackendStatus.HEALTHY
        assert backend._last_health_check is not None

    def test_update_status_unhealthy(self):
        backend = self._make_concrete_backend()
        backend.update_status(False)
        assert backend.status == BackendStatus.UNHEALTHY

    def test_get_metrics(self):
        backend = self._make_concrete_backend()
        backend._request_count = 5
        backend._error_count = 1
        backend.update_status(True)
        metrics = backend.get_metrics()
        assert metrics["name"] == "concrete"
        assert metrics["status"] == "healthy"
        assert metrics["request_count"] == 5
        assert metrics["error_count"] == 1
        assert metrics["health_score"] == pytest.approx(0.8)
        assert metrics["last_health_check"] is not None

    @pytest.mark.asyncio
    async def test_generate_with_retry_success(self):
        backend = self._make_concrete_backend()
        resp = await backend.generate_with_retry("hello")
        assert resp.success is True
        assert resp.content == "ok"
        assert backend._request_count == 1

    @pytest.mark.asyncio
    async def test_generate_with_retry_all_fail(self):
        backend = self._make_concrete_backend(LLMConfig(model="test", max_retries=2))

        call_count = 0
        async def failing_generate(prompt, system_prompt=None, **kwargs):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("fail")

        backend.generate = failing_generate
        resp = await backend.generate_with_retry("hello")
        assert resp.success is False
        assert "모든 재시도 실패" in resp.error_message
        assert call_count == 2
        assert backend._error_count == 2


class TestOllamaBackend:

    def test_init(self):
        config = LLMConfig(model="deepseek-coder:33b")
        backend = OllamaBackend(base_url="http://localhost:11434", config=config)

        assert backend.name == "ollama"
        assert backend.config.model == "deepseek-coder:33b"
        assert backend.base_url == "http://localhost:11434"

    def test_init_default_config(self):
        backend = OllamaBackend()
        assert backend.config.model == "deepseek-coder:33b"
        assert backend.base_url == "http://localhost:11434"

    def test_init_strips_trailing_slash(self):
        backend = OllamaBackend(base_url="http://localhost:11434/")
        assert backend.base_url == "http://localhost:11434"

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        backend = OllamaBackend(
            base_url="http://localhost:11434",
            config=LLMConfig(model="test-model")
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [{"name": "test-model"}]
        }

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.is_closed = False
        backend._client = mock_client

        result = await backend.health_check()
        assert result is True
        assert backend.status == BackendStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_health_check_model_not_found(self):
        backend = OllamaBackend(config=LLMConfig(model="missing-model"))
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [{"name": "other-model"}]
        }

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.is_closed = False
        backend._client = mock_client

        result = await backend.health_check()
        assert result is False
        assert backend.status == BackendStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_health_check_exception(self):
        backend = OllamaBackend(config=LLMConfig(model="test"))
        mock_client = AsyncMock()
        mock_client.get.side_effect = ConnectionError("refused")
        mock_client.is_closed = False
        backend._client = mock_client

        result = await backend.health_check()
        assert result is False
        assert backend.status == BackendStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_generate_success(self):
        backend = OllamaBackend(
            base_url="http://localhost:11434",
            config=LLMConfig(model="test-model")
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": "Generated text",
            "eval_count": 50,
            "prompt_eval_count": 20
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.is_closed = False
        backend._client = mock_client

        response = await backend.generate("Test prompt")

        assert response.success is True
        assert response.content == "Generated text"
        assert response.tokens_used == 70

    @pytest.mark.asyncio
    async def test_generate_with_system_prompt(self):
        backend = OllamaBackend(config=LLMConfig(model="test"))

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "sys response", "eval_count": 10, "prompt_eval_count": 5}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.is_closed = False
        backend._client = mock_client

        response = await backend.generate("hello", system_prompt="You are helpful")
        assert response.success is True
        # Verify system prompt was included in the body
        call_kwargs = mock_client.post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert body["system"] == "You are helpful"

    @pytest.mark.asyncio
    async def test_generate_http_error(self):
        backend = OllamaBackend(config=LLMConfig(model="test"))

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.is_closed = False
        backend._client = mock_client

        response = await backend.generate("test")
        assert response.success is False
        assert "500" in response.error_message

    @pytest.mark.asyncio
    async def test_generate_timeout(self):
        backend = OllamaBackend(config=LLMConfig(model="test"))

        mock_client = AsyncMock()
        mock_client.post.side_effect = asyncio.TimeoutError()
        mock_client.is_closed = False
        backend._client = mock_client

        response = await backend.generate("test")
        assert response.success is False
        assert "타임아웃" in response.error_message

    @pytest.mark.asyncio
    async def test_generate_generic_exception(self):
        backend = OllamaBackend(config=LLMConfig(model="test"))

        mock_client = AsyncMock()
        mock_client.post.side_effect = RuntimeError("connection refused")
        mock_client.is_closed = False
        backend._client = mock_client

        response = await backend.generate("test")
        assert response.success is False
        assert "connection refused" in response.error_message

    @pytest.mark.asyncio
    async def test_pull_model_success(self):
        backend = OllamaBackend(config=LLMConfig(model="test"))

        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.is_closed = False
        backend._client = mock_client

        result = await backend.pull_model()
        assert result is True

    @pytest.mark.asyncio
    async def test_pull_model_custom_name(self):
        backend = OllamaBackend(config=LLMConfig(model="default"))

        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.is_closed = False
        backend._client = mock_client

        result = await backend.pull_model("custom-model")
        assert result is True
        call_kwargs = mock_client.post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert body["name"] == "custom-model"

    @pytest.mark.asyncio
    async def test_pull_model_failure(self):
        backend = OllamaBackend(config=LLMConfig(model="test"))

        mock_client = AsyncMock()
        mock_client.post.side_effect = ConnectionError("refused")
        mock_client.is_closed = False
        backend._client = mock_client

        result = await backend.pull_model()
        assert result is False

    @pytest.mark.asyncio
    async def test_close(self):
        backend = OllamaBackend(config=LLMConfig(model="test"))
        mock_client = AsyncMock()
        mock_client.is_closed = False
        backend._client = mock_client

        await backend.close()
        mock_client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_already_closed(self):
        backend = OllamaBackend(config=LLMConfig(model="test"))
        mock_client = AsyncMock()
        mock_client.is_closed = True
        backend._client = mock_client

        await backend.close()
        mock_client.aclose.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_client_creates_new(self):
        backend = OllamaBackend(config=LLMConfig(model="test"))
        backend._client = None
        with patch("backends.ollama_backend.httpx") as mock_httpx:
            mock_instance = AsyncMock()
            mock_instance.is_closed = False
            mock_httpx.AsyncClient.return_value = mock_instance
            client = await backend._get_client()
            assert client is not None


class TestOpenAIBackend:

    def test_init(self):
        backend = OpenAIBackend(
            api_key="test-key",
            config=LLMConfig(model="gpt-4")
        )

        assert backend.name == "openai"
        assert backend.config.model == "gpt-4"

    def test_init_default_config(self):
        backend = OpenAIBackend(api_key="key")
        assert backend.config.model == "gpt-4"

    def test_init_from_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "env-key")

        backend = OpenAIBackend()
        assert backend.api_key == "env-key"

    def test_init_with_base_url(self):
        backend = OpenAIBackend(api_key="k", base_url="https://custom.api.com")
        assert backend.base_url == "https://custom.api.com"

    @pytest.mark.asyncio
    async def test_health_check_no_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        backend = OpenAIBackend(api_key=None)
        backend.api_key = None
        result = await backend.health_check()
        assert result is False
        assert backend.status == BackendStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        backend = OpenAIBackend(api_key="test-key")

        mock_client = AsyncMock()
        mock_client.models.list = AsyncMock(return_value=["gpt-4"])
        backend._client = mock_client

        result = await backend.health_check()
        assert result is True
        assert backend.status == BackendStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_health_check_exception(self):
        backend = OpenAIBackend(api_key="test-key")

        mock_client = AsyncMock()
        mock_client.models.list = AsyncMock(side_effect=Exception("auth fail"))
        backend._client = mock_client

        result = await backend.health_check()
        assert result is False
        assert backend.status == BackendStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_generate_success(self):
        backend = OpenAIBackend(api_key="test-key", config=LLMConfig(model="gpt-4"))

        mock_choice = MagicMock()
        mock_choice.message.content = "Hello world"
        mock_choice.finish_reason = "stop"

        mock_usage = MagicMock()
        mock_usage.total_tokens = 42

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.model = "gpt-4"
        mock_response.id = "chatcmpl-123"
        mock_response.usage = mock_usage

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        backend._client = mock_client

        response = await backend.generate("Say hello")
        assert response.success is True
        assert response.content == "Hello world"
        assert response.tokens_used == 42
        assert response.model == "gpt-4"
        assert response.raw_response["finish_reason"] == "stop"

    @pytest.mark.asyncio
    async def test_generate_with_system_prompt(self):
        backend = OpenAIBackend(api_key="test-key", config=LLMConfig(model="gpt-4"))

        mock_choice = MagicMock()
        mock_choice.message.content = "Yes"
        mock_choice.finish_reason = "stop"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.model = "gpt-4"
        mock_response.id = "chatcmpl-456"
        mock_response.usage = MagicMock(total_tokens=10)

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        backend._client = mock_client

        response = await backend.generate("Hi", system_prompt="Be brief")
        assert response.success is True
        # Verify system message was included
        call_kwargs = mock_client.chat.completions.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "Be brief"

    @pytest.mark.asyncio
    async def test_generate_no_usage(self):
        backend = OpenAIBackend(api_key="test-key", config=LLMConfig(model="gpt-4"))

        mock_choice = MagicMock()
        mock_choice.message.content = "text"
        mock_choice.finish_reason = "stop"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.model = "gpt-4"
        mock_response.id = "x"
        mock_response.usage = None

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        backend._client = mock_client

        response = await backend.generate("test")
        assert response.tokens_used == 0

    @pytest.mark.asyncio
    async def test_generate_exception(self):
        backend = OpenAIBackend(api_key="test-key", config=LLMConfig(model="gpt-4"))

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("rate limit"))
        backend._client = mock_client

        response = await backend.generate("test")
        assert response.success is False
        assert "rate limit" in response.error_message

    @pytest.mark.asyncio
    async def test_generate_none_content(self):
        backend = OpenAIBackend(api_key="test-key", config=LLMConfig(model="gpt-4"))

        mock_choice = MagicMock()
        mock_choice.message.content = None
        mock_choice.finish_reason = "stop"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.model = "gpt-4"
        mock_response.id = "x"
        mock_response.usage = MagicMock(total_tokens=5)

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        backend._client = mock_client

        response = await backend.generate("test")
        assert response.success is True
        assert response.content == ""

    @pytest.mark.asyncio
    async def test_generate_stream(self):
        backend = OpenAIBackend(api_key="test-key", config=LLMConfig(model="gpt-4"))

        chunk1 = MagicMock()
        chunk1.choices = [MagicMock()]
        chunk1.choices[0].delta.content = "Hello"

        chunk2 = MagicMock()
        chunk2.choices = [MagicMock()]
        chunk2.choices[0].delta.content = " world"

        async def mock_stream_iter():
            yield chunk1
            yield chunk2

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_stream_iter())
        backend._client = mock_client

        chunks = []
        async for text in backend.generate_stream("test"):
            chunks.append(text)
        assert chunks == ["Hello", " world"]

    @pytest.mark.asyncio
    async def test_generate_stream_error(self):
        backend = OpenAIBackend(api_key="test-key", config=LLMConfig(model="gpt-4"))

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("stream fail"))
        backend._client = mock_client

        with pytest.raises(Exception, match="stream fail"):
            async for _ in backend.generate_stream("test"):
                pass

    @pytest.mark.asyncio
    async def test_close(self):
        backend = OpenAIBackend(api_key="test-key")
        mock_client = AsyncMock()
        backend._client = mock_client

        await backend.close()
        mock_client.close.assert_called_once()
        assert backend._client is None

    @pytest.mark.asyncio
    async def test_close_no_client(self):
        backend = OpenAIBackend(api_key="test-key")
        backend._client = None
        await backend.close()  # should not raise

    @pytest.mark.asyncio
    async def test_get_client_import_error(self):
        backend = OpenAIBackend(api_key="test-key")
        backend._client = None
        with patch.dict("sys.modules", {"openai": None}):
            with patch("builtins.__import__", side_effect=ImportError("no openai")):
                with pytest.raises(ImportError, match="openai"):
                    await backend._get_client()


class TestAnthropicBackend:

    def test_init(self):
        backend = AnthropicBackend(
            api_key="test-key",
            config=LLMConfig(model="claude-3-5-sonnet-20241022")
        )

        assert backend.name == "anthropic"
        assert backend.config.model == "claude-3-5-sonnet-20241022"

    def test_init_default_config(self):
        backend = AnthropicBackend(api_key="key")
        assert backend.config.model == "claude-3-5-sonnet-20241022"

    def test_model_max_tokens(self):
        backend = AnthropicBackend(config=LLMConfig(model="claude-3-5-sonnet-20241022"))
        assert backend.MODEL_MAX_TOKENS["claude-3-5-sonnet-20241022"] == 8192
        assert backend.MODEL_MAX_TOKENS["claude-opus-4-20250514"] == 16384

    def test_init_from_env(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
        backend = AnthropicBackend()
        assert backend.api_key == "env-key"

    @pytest.mark.asyncio
    async def test_health_check_no_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        backend = AnthropicBackend(api_key=None)
        backend.api_key = None
        result = await backend.health_check()
        assert result is False
        assert backend.status == BackendStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        backend = AnthropicBackend(api_key="test-key")

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=MagicMock())
        backend._client = mock_client

        result = await backend.health_check()
        assert result is True
        assert backend.status == BackendStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_health_check_exception(self):
        backend = AnthropicBackend(api_key="test-key")

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("auth error"))
        backend._client = mock_client

        result = await backend.health_check()
        assert result is False
        assert backend.status == BackendStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_generate_success(self):
        backend = AnthropicBackend(
            api_key="test-key",
            config=LLMConfig(model="claude-3-5-sonnet-20241022")
        )

        mock_block = MagicMock()
        mock_block.text = "Hello from Claude"

        mock_usage = MagicMock()
        mock_usage.input_tokens = 10
        mock_usage.output_tokens = 20

        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_response.model = "claude-3-5-sonnet-20241022"
        mock_response.id = "msg_123"
        mock_response.stop_reason = "end_turn"
        mock_response.usage = mock_usage

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        backend._client = mock_client

        response = await backend.generate("Say hello")
        assert response.success is True
        assert response.content == "Hello from Claude"
        assert response.tokens_used == 30
        assert response.model == "claude-3-5-sonnet-20241022"
        assert response.raw_response["stop_reason"] == "end_turn"

    @pytest.mark.asyncio
    async def test_generate_with_system_prompt(self):
        backend = AnthropicBackend(api_key="test-key", config=LLMConfig(model="claude-3-5-sonnet-20241022"))

        mock_block = MagicMock()
        mock_block.text = "Yes"

        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_response.model = "claude-3-5-sonnet-20241022"
        mock_response.id = "msg_456"
        mock_response.stop_reason = "end_turn"
        mock_response.usage = MagicMock(input_tokens=5, output_tokens=5)

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        backend._client = mock_client

        response = await backend.generate("Hi", system_prompt="Be brief")
        assert response.success is True
        # Verify system was passed
        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs.get("system") == "Be brief"

    @pytest.mark.asyncio
    async def test_generate_no_usage(self):
        backend = AnthropicBackend(api_key="test-key", config=LLMConfig(model="claude-3-5-sonnet-20241022"))

        mock_block = MagicMock()
        mock_block.text = "text"

        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_response.model = "claude-3-5-sonnet-20241022"
        mock_response.id = "x"
        mock_response.stop_reason = "end_turn"
        mock_response.usage = None

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        backend._client = mock_client

        response = await backend.generate("test")
        assert response.tokens_used == 0

    @pytest.mark.asyncio
    async def test_generate_multiple_blocks(self):
        backend = AnthropicBackend(api_key="test-key", config=LLMConfig(model="claude-3-5-sonnet-20241022"))

        block1 = MagicMock()
        block1.text = "Hello "
        block2 = MagicMock()
        block2.text = "World"
        # A block without text attr
        block3 = MagicMock(spec=[])

        mock_response = MagicMock()
        mock_response.content = [block1, block2, block3]
        mock_response.model = "claude-3-5-sonnet-20241022"
        mock_response.id = "x"
        mock_response.stop_reason = "end_turn"
        mock_response.usage = MagicMock(input_tokens=5, output_tokens=10)

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        backend._client = mock_client

        response = await backend.generate("test")
        assert response.content == "Hello World"

    @pytest.mark.asyncio
    async def test_generate_exception(self):
        backend = AnthropicBackend(api_key="test-key", config=LLMConfig(model="claude-3-5-sonnet-20241022"))

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("rate limited"))
        backend._client = mock_client

        response = await backend.generate("test")
        assert response.success is False
        assert "rate limited" in response.error_message

    @pytest.mark.asyncio
    async def test_generate_max_tokens_capped(self):
        """max_tokens should be capped to model max."""
        backend = AnthropicBackend(
            api_key="test-key",
            config=LLMConfig(model="claude-3-haiku-20240307", max_tokens=50000)
        )

        mock_block = MagicMock()
        mock_block.text = "ok"
        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_response.model = "claude-3-haiku-20240307"
        mock_response.id = "x"
        mock_response.stop_reason = "end_turn"
        mock_response.usage = MagicMock(input_tokens=1, output_tokens=1)

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        backend._client = mock_client

        await backend.generate("test")
        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["max_tokens"] == 4096  # capped to model max

    @pytest.mark.asyncio
    async def test_generate_stream(self):
        backend = AnthropicBackend(api_key="test-key", config=LLMConfig(model="claude-3-5-sonnet-20241022"))

        async def mock_text_stream():
            yield "Hello"
            yield " world"

        mock_stream_ctx = MagicMock()
        mock_stream_ctx.text_stream = mock_text_stream()

        # messages.stream() returns an async context manager (not a coroutine)
        class MockStreamCM:
            async def __aenter__(self):
                return mock_stream_ctx
            async def __aexit__(self, *args):
                pass

        mock_client = AsyncMock()
        mock_client.messages.stream = MagicMock(return_value=MockStreamCM())
        backend._client = mock_client

        chunks = []
        async for text in backend.generate_stream("test"):
            chunks.append(text)
        assert chunks == ["Hello", " world"]

    @pytest.mark.asyncio
    async def test_generate_stream_error(self):
        backend = AnthropicBackend(api_key="test-key", config=LLMConfig(model="claude-3-5-sonnet-20241022"))

        class MockStreamCMError:
            async def __aenter__(self):
                raise Exception("stream fail")
            async def __aexit__(self, *args):
                pass

        mock_client = AsyncMock()
        mock_client.messages.stream = MagicMock(return_value=MockStreamCMError())
        backend._client = mock_client

        with pytest.raises(Exception, match="stream fail"):
            async for _ in backend.generate_stream("test"):
                pass

    @pytest.mark.asyncio
    async def test_close(self):
        backend = AnthropicBackend(api_key="test-key")
        mock_client = AsyncMock()
        backend._client = mock_client

        await backend.close()
        mock_client.close.assert_called_once()
        assert backend._client is None

    @pytest.mark.asyncio
    async def test_close_no_client(self):
        backend = AnthropicBackend(api_key="test-key")
        backend._client = None
        await backend.close()  # should not raise

    @pytest.mark.asyncio
    async def test_get_client_import_error(self):
        backend = AnthropicBackend(api_key="test-key")
        backend._client = None
        with patch.dict("sys.modules", {"anthropic": None}):
            with patch("builtins.__import__", side_effect=ImportError("no anthropic")):
                with pytest.raises(ImportError, match="anthropic"):
                    await backend._get_client()


class TestRouterConfig:
    def test_defaults(self):
        config = RouterConfig()
        assert config.strategy == "priority"
        assert config.health_check_interval == 60
        assert config.enable_auto_failover is True
        assert config.max_concurrent_requests == 10


class TestRouterMetrics:
    def test_defaults(self):
        metrics = RouterMetrics()
        assert metrics.total_requests == 0
        assert metrics.successful_requests == 0
        assert metrics.failed_requests == 0
        assert metrics.fallback_count == 0
        assert metrics.last_request_time is None
        assert metrics.backend_usage == {}


class TestLLMRouter:

    @pytest.fixture
    def mock_backends(self):
        backend1 = MagicMock(spec=LLMBackend)
        backend1.name = "backend1"
        backend1.status = BackendStatus.HEALTHY
        backend1.health_score = 0.9
        backend1.generate_with_retry = AsyncMock(return_value=LLMResponse(
            content="Response 1",
            model="model1",
            backend_name="backend1",
            success=True,
            latency_ms=100
        ))
        backend1.health_check = AsyncMock(return_value=True)
        backend1.update_status = MagicMock()
        backend1.get_metrics = MagicMock(return_value={"name": "backend1", "status": "healthy"})

        backend2 = MagicMock(spec=LLMBackend)
        backend2.name = "backend2"
        backend2.status = BackendStatus.HEALTHY
        backend2.health_score = 0.8
        backend2.generate_with_retry = AsyncMock(return_value=LLMResponse(
            content="Response 2",
            model="model2",
            backend_name="backend2",
            success=True,
            latency_ms=150
        ))
        backend2.health_check = AsyncMock(return_value=True)
        backend2.update_status = MagicMock()
        backend2.get_metrics = MagicMock(return_value={"name": "backend2", "status": "healthy"})

        return [backend1, backend2]

    def test_init(self, mock_backends):
        router = LLMRouter(mock_backends)

        assert len(router.backends) == 2
        assert "backend1" in router.backends
        assert "backend2" in router.backends

    def test_init_default_config(self, mock_backends):
        router = LLMRouter(mock_backends)
        assert router.config.strategy == "priority"

    def test_init_custom_config(self, mock_backends):
        config = RouterConfig(strategy="round_robin", max_concurrent_requests=5)
        router = LLMRouter(mock_backends, config)
        assert router.config.strategy == "round_robin"
        assert router.config.max_concurrent_requests == 5

    def test_available_backends(self, mock_backends):
        router = LLMRouter(mock_backends)
        assert "backend1" in router.available_backends
        assert "backend2" in router.available_backends

    def test_available_backends_one_unhealthy(self, mock_backends):
        mock_backends[0].status = BackendStatus.UNHEALTHY
        router = LLMRouter(mock_backends)
        avail = router.available_backends
        assert "backend1" not in avail
        assert "backend2" in avail

    @pytest.mark.asyncio
    async def test_generate_priority(self, mock_backends):
        router = LLMRouter(mock_backends, RouterConfig(strategy="priority"))

        response = await router.generate("Test prompt")

        assert response.success is True
        assert response.backend_name == "backend1"
        mock_backends[0].generate_with_retry.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_with_preferred_backend(self, mock_backends):
        router = LLMRouter(mock_backends, RouterConfig(strategy="priority"))

        response = await router.generate("Test", preferred_backend="backend2")

        assert response.success is True
        assert response.backend_name == "backend2"
        mock_backends[1].generate_with_retry.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_preferred_backend_not_found(self, mock_backends):
        router = LLMRouter(mock_backends, RouterConfig(strategy="priority"))

        response = await router.generate("Test", preferred_backend="nonexistent")

        # Should fall back to normal order
        assert response.success is True

    @pytest.mark.asyncio
    async def test_fallback_on_failure(self, mock_backends):
        mock_backends[0].generate_with_retry = AsyncMock(return_value=LLMResponse(
            content="",
            model="model1",
            backend_name="backend1",
            success=False,
            latency_ms=0,
            error_message="Failed"
        ))

        router = LLMRouter(mock_backends, RouterConfig(enable_auto_failover=True))

        response = await router.generate("Test prompt")

        assert response.success is True
        assert response.backend_name == "backend2"

    @pytest.mark.asyncio
    async def test_fallback_on_exception(self, mock_backends):
        mock_backends[0].generate_with_retry = AsyncMock(side_effect=RuntimeError("crash"))

        router = LLMRouter(mock_backends, RouterConfig(enable_auto_failover=True))

        response = await router.generate("Test")
        assert response.success is True
        assert response.backend_name == "backend2"
        assert router.metrics.fallback_count == 1
        mock_backends[0].update_status.assert_called_with(False)

    @pytest.mark.asyncio
    async def test_all_backends_fail(self, mock_backends):
        mock_backends[0].generate_with_retry = AsyncMock(side_effect=RuntimeError("crash1"))
        mock_backends[1].generate_with_retry = AsyncMock(side_effect=RuntimeError("crash2"))

        router = LLMRouter(mock_backends, RouterConfig(enable_auto_failover=True))
        response = await router.generate("Test")

        assert response.success is False
        assert "모든 백엔드 실패" in response.error_message
        assert router.metrics.failed_requests == 1

    @pytest.mark.asyncio
    async def test_skip_unhealthy_backend(self, mock_backends):
        mock_backends[0].status = BackendStatus.UNHEALTHY

        router = LLMRouter(mock_backends, RouterConfig(enable_auto_failover=True))
        response = await router.generate("Test")

        assert response.success is True
        assert response.backend_name == "backend2"
        mock_backends[0].generate_with_retry.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_failover_disabled(self, mock_backends):
        """With failover disabled, exception is still caught but continues."""
        mock_backends[0].generate_with_retry = AsyncMock(side_effect=RuntimeError("crash"))

        router = LLMRouter(mock_backends, RouterConfig(enable_auto_failover=False))
        response = await router.generate("Test")
        # With failover disabled, unhealthy backends are not skipped,
        # and the exception path does not 'continue', so backend2 is still tried
        assert response.success is True

    @pytest.mark.asyncio
    async def test_health_check_all(self, mock_backends):
        router = LLMRouter(mock_backends)

        results = await router.health_check_all()

        assert results["backend1"] is True
        assert results["backend2"] is True

    @pytest.mark.asyncio
    async def test_health_check_all_with_exception(self, mock_backends):
        mock_backends[1].health_check = AsyncMock(side_effect=RuntimeError("check failed"))

        router = LLMRouter(mock_backends)
        results = await router.health_check_all()

        assert results["backend1"] is True
        assert results["backend2"] is False

    @pytest.mark.asyncio
    async def test_start_and_stop(self, mock_backends):
        router = LLMRouter(mock_backends, RouterConfig(health_check_interval=1000))

        await router.start()
        assert router._health_check_task is not None

        await router.stop()
        assert router._health_check_task.cancelled() or router._health_check_task.done()

    @pytest.mark.asyncio
    async def test_stop_no_task(self, mock_backends):
        router = LLMRouter(mock_backends)
        router._health_check_task = None
        await router.stop()  # should not raise

    @pytest.mark.asyncio
    async def test_stop_calls_close(self, mock_backends):
        mock_backends[0].close = AsyncMock()
        mock_backends[1].close = AsyncMock()

        router = LLMRouter(mock_backends)
        await router.stop()

        mock_backends[0].close.assert_called_once()
        mock_backends[1].close.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_no_periodic_health_check(self, mock_backends):
        """health_check_interval=0 disables periodic checks."""
        router = LLMRouter(mock_backends, RouterConfig(health_check_interval=0))
        await router.start()
        assert router._health_check_task is None

    def test_metrics(self, mock_backends):
        router = LLMRouter(mock_backends)

        metrics = router.get_metrics()

        assert metrics["total_requests"] == 0
        assert metrics["success_rate"] == 0
        assert "backend1" in metrics["backend_metrics"]

    def test_metrics_with_requests(self, mock_backends):
        router = LLMRouter(mock_backends)
        router.metrics.total_requests = 10
        router.metrics.successful_requests = 8
        router.metrics.failed_requests = 2
        router.metrics.fallback_count = 3
        router.metrics.backend_usage = {"backend1": 6, "backend2": 2}

        metrics = router.get_metrics()
        assert metrics["success_rate"] == 80.0
        assert metrics["fallback_count"] == 3

    def test_add_backend(self, mock_backends):
        router = LLMRouter(mock_backends)

        new_backend = MagicMock(spec=LLMBackend)
        new_backend.name = "backend3"
        router.add_backend(new_backend)

        assert "backend3" in router.backends
        assert router.backend_order[-1] == "backend3"

    def test_add_backend_with_priority(self, mock_backends):
        router = LLMRouter(mock_backends)

        new_backend = MagicMock(spec=LLMBackend)
        new_backend.name = "backend3"
        router.add_backend(new_backend, priority=0)

        assert router.backend_order[0] == "backend3"

    def test_remove_backend(self, mock_backends):
        router = LLMRouter(mock_backends)
        router.remove_backend("backend1")

        assert "backend1" not in router.backends
        assert "backend1" not in router.backend_order

    def test_remove_nonexistent_backend(self, mock_backends):
        router = LLMRouter(mock_backends)
        router.remove_backend("nonexistent")  # should not raise
        assert len(router.backends) == 2

    def test_repr(self, mock_backends):
        router = LLMRouter(mock_backends)
        r = repr(router)
        assert "LLMRouter" in r
        assert "backend1" in r
        assert "priority" in r

    def test_select_backend_priority(self, mock_backends):
        router = LLMRouter(mock_backends, RouterConfig(strategy="priority"))
        selected = router._select_backend()
        assert selected == "backend1"

    def test_select_backend_priority_first_unhealthy(self, mock_backends):
        mock_backends[0].status = BackendStatus.UNHEALTHY
        router = LLMRouter(mock_backends, RouterConfig(strategy="priority"))
        selected = router._select_backend()
        assert selected == "backend2"

    def test_select_backend_round_robin(self, mock_backends):
        router = LLMRouter(mock_backends, RouterConfig(strategy="round_robin"))
        selected1 = router._select_backend()
        selected2 = router._select_backend()
        # Round robin should cycle
        assert selected1 is not None
        assert selected2 is not None

    def test_select_backend_health_based(self, mock_backends):
        mock_backends[0].health_score = 0.5
        mock_backends[1].health_score = 0.9
        router = LLMRouter(mock_backends, RouterConfig(strategy="health_based"))
        selected = router._select_backend()
        assert selected == "backend2"

    def test_select_backend_random(self, mock_backends):
        router = LLMRouter(mock_backends, RouterConfig(strategy="random"))
        selected = router._select_backend()
        assert selected in ["backend1", "backend2"]

    def test_select_backend_no_available(self, mock_backends):
        mock_backends[0].status = BackendStatus.UNHEALTHY
        mock_backends[1].status = BackendStatus.UNHEALTHY
        router = LLMRouter(mock_backends, RouterConfig(strategy="priority"))
        selected = router._select_backend()
        assert selected is None

    def test_select_backend_round_robin_no_available(self, mock_backends):
        mock_backends[0].status = BackendStatus.UNHEALTHY
        mock_backends[1].status = BackendStatus.UNHEALTHY
        router = LLMRouter(mock_backends, RouterConfig(strategy="round_robin"))
        assert router._select_backend() is None

    def test_select_backend_health_based_no_available(self, mock_backends):
        mock_backends[0].status = BackendStatus.UNHEALTHY
        mock_backends[1].status = BackendStatus.UNHEALTHY
        router = LLMRouter(mock_backends, RouterConfig(strategy="health_based"))
        assert router._select_backend() is None

    def test_select_backend_random_no_available(self, mock_backends):
        mock_backends[0].status = BackendStatus.UNHEALTHY
        mock_backends[1].status = BackendStatus.UNHEALTHY
        router = LLMRouter(mock_backends, RouterConfig(strategy="random"))
        assert router._select_backend() is None

    @pytest.mark.asyncio
    async def test_generate_updates_metrics(self, mock_backends):
        router = LLMRouter(mock_backends)
        await router.generate("test")

        assert router.metrics.total_requests == 1
        assert router.metrics.successful_requests == 1
        assert router.metrics.last_request_time is not None
        assert router.metrics.backend_usage.get("backend1", 0) == 1
