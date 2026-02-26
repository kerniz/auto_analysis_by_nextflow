"""
Tests for LLM Backends
LLM 백엔드 테스트
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

from backends import (
    LLMBackend, 
    LLMConfig, 
    LLMResponse,
    OllamaBackend,
    OpenAIBackend,
    AnthropicBackend,
    LLMRouter
)
from backends.router import RouterConfig
from backends.base import BackendStatus


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


class TestLLMResponse:
    
    def test_success_response(self):
        response = LLMResponse(
            content="Test response",
            model="test-model",
            backend_name="test",
            success=True,
            latency_ms=100.5
        )
        
        assert response.success == True
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
        
        assert response.success == False
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
        assert result["success"] == True
        assert result["tokens_used"] == 100


class TestOllamaBackend:
    
    def test_init(self):
        config = LLMConfig(model="deepseek-coder:33b")
        backend = OllamaBackend(base_url="http://localhost:11434", config=config)
        
        assert backend.name == "ollama"
        assert backend.config.model == "deepseek-coder:33b"
        assert backend.base_url == "http://localhost:11434"
    
    @pytest.mark.asyncio
    async def test_health_check_success(self):
        backend = OllamaBackend(
            base_url="http://localhost:11434",
            config=LLMConfig(model="test-model")
        )
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "models": [{"name": "test-model"}]
            }
            
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_instance.is_closed = False
            mock_client.return_value = mock_instance
            
            result = await backend.health_check()
            assert result == True
    
    @pytest.mark.asyncio
    async def test_generate_success(self):
        backend = OllamaBackend(
            base_url="http://localhost:11434",
            config=LLMConfig(model="test-model")
        )
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "response": "Generated text",
                "eval_count": 50,
                "prompt_eval_count": 20
            }
            
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.is_closed = False
            mock_client.return_value = mock_instance
            
            response = await backend.generate("Test prompt")
            
            assert response.success == True
            assert response.content == "Generated text"


class TestOpenAIBackend:
    
    def test_init(self):
        backend = OpenAIBackend(
            api_key="test-key",
            config=LLMConfig(model="gpt-4")
        )
        
        assert backend.name == "openai"
        assert backend.config.model == "gpt-4"
    
    def test_init_from_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "env-key")
        
        backend = OpenAIBackend()
        assert backend.api_key == "env-key"


class TestAnthropicBackend:
    
    def test_init(self):
        backend = AnthropicBackend(
            api_key="test-key",
            config=LLMConfig(model="claude-3-5-sonnet-20241022")
        )
        
        assert backend.name == "anthropic"
        assert backend.config.model == "claude-3-5-sonnet-20241022"
    
    def test_model_max_tokens(self):
        backend = AnthropicBackend(config=LLMConfig(model="claude-3-5-sonnet-20241022"))
        
        assert backend.MODEL_MAX_TOKENS["claude-3-5-sonnet-20241022"] == 8192


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
        
        return [backend1, backend2]
    
    def test_init(self, mock_backends):
        router = LLMRouter(mock_backends)
        
        assert len(router.backends) == 2
        assert "backend1" in router.backends
        assert "backend2" in router.backends
    
    @pytest.mark.asyncio
    async def test_generate_priority(self, mock_backends):
        router = LLMRouter(mock_backends, RouterConfig(strategy="priority"))
        
        response = await router.generate("Test prompt")
        
        assert response.success == True
        assert response.backend_name == "backend1"
        mock_backends[0].generate_with_retry.assert_called_once()
    
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
        
        assert response.success == True
        assert response.backend_name == "backend2"
    
    @pytest.mark.asyncio
    async def test_health_check_all(self, mock_backends):
        router = LLMRouter(mock_backends)
        
        results = await router.health_check_all()
        
        assert results["backend1"] == True
        assert results["backend2"] == True
    
    def test_metrics(self, mock_backends):
        router = LLMRouter(mock_backends)
        
        metrics = router.get_metrics()
        
        assert metrics["total_requests"] == 0
        assert "backend1" in metrics["backend_metrics"]
