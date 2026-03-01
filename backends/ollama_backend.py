"""
Ollama Backend
로컬 Ollama 서버 연결 백엔드 (DeepSeek 포함)
"""

import asyncio
import time

try:
    import httpx
    ASYNC_CLIENT = True
except ImportError:
    import requests
    ASYNC_CLIENT = False

from .base import LLMBackend, LLMConfig, LLMResponse


class OllamaBackend(LLMBackend):
    """
    Ollama API 백엔드

    로컬 또는 원격 Ollama 서버에 연결하여 텍스트 생성을 수행합니다.
    DeepSeek, Llama, Mistral 등 Ollama가 지원하는 모든 모델 사용 가능.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        config: LLMConfig | None = None
    ):
        """
        Ollama 백엔드 초기화

        Args:
            base_url: Ollama 서버 URL
            config: LLM 설정 (기본값: deepseek-coder:33b)
        """
        if config is None:
            config = LLMConfig(model="deepseek-coder:33b")

        super().__init__(config)
        self.base_url = base_url.rstrip("/")
        self._client = None

    @property
    def name(self) -> str:
        return "ollama"

    async def _get_client(self):
        """비동기 HTTP 클라이언트 반환"""
        if ASYNC_CLIENT:
            if self._client is None or self._client.is_closed:
                self._client = httpx.AsyncClient(timeout=self.config.timeout)
            return self._client
        return None

    async def health_check(self) -> bool:
        """Ollama 서버 상태 확인"""
        try:
            if ASYNC_CLIENT:
                client = await self._get_client()
                response = await client.get(f"{self.base_url}/api/tags")

                if response.status_code == 200:
                    models = response.json().get("models", [])
                    model_names = [m.get("name", "") for m in models]

                    # 요청한 모델이 있는지 확인
                    model_available = any(
                        self.config.model in name or name.startswith(self.config.model.split(":")[0])
                        for name in model_names
                    )

                    self.update_status(model_available)
                    return model_available

            self.update_status(False)
            return False

        except Exception as e:
            print(f"Ollama health check 실패: {e}")
            self.update_status(False)
            return False

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs
    ) -> LLMResponse:
        """
        Ollama API로 텍스트 생성

        Args:
            prompt: 입력 프롬프트
            system_prompt: 시스템 프롬프트
            **kwargs: 추가 옵션 (temperature, top_p 등)

        Returns:
            LLMResponse: 표준화된 응답
        """
        start_time = time.time()

        # 요청 본문 구성
        body = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", self.config.temperature),
                "top_p": kwargs.get("top_p", self.config.top_p),
                "num_predict": kwargs.get("max_tokens", self.config.max_tokens),
            }
        }

        if system_prompt:
            body["system"] = system_prompt

        try:
            if ASYNC_CLIENT:
                client = await self._get_client()
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json=body,
                    timeout=self.config.timeout
                )

                latency_ms = (time.time() - start_time) * 1000

                if response.status_code == 200:
                    data = response.json()

                    return LLMResponse(
                        content=data.get("response", ""),
                        model=self.config.model,
                        backend_name=self.name,
                        success=True,
                        latency_ms=latency_ms,
                        tokens_used=data.get("eval_count", 0) + data.get("prompt_eval_count", 0),
                        raw_response=data
                    )
                else:
                    return LLMResponse(
                        content="",
                        model=self.config.model,
                        backend_name=self.name,
                        success=False,
                        latency_ms=latency_ms,
                        error_message=f"HTTP {response.status_code}: {response.text}"
                    )
            else:
                # Fallback to sync requests
                response = requests.post(
                    f"{self.base_url}/api/generate",
                    json=body,
                    timeout=self.config.timeout
                )

                latency_ms = (time.time() - start_time) * 1000

                if response.status_code == 200:
                    data = response.json()

                    return LLMResponse(
                        content=data.get("response", ""),
                        model=self.config.model,
                        backend_name=self.name,
                        success=True,
                        latency_ms=latency_ms,
                        tokens_used=data.get("eval_count", 0),
                        raw_response=data
                    )
                else:
                    return LLMResponse(
                        content="",
                        model=self.config.model,
                        backend_name=self.name,
                        success=False,
                        latency_ms=latency_ms,
                        error_message=f"HTTP {response.status_code}"
                    )

        except asyncio.TimeoutError:
            latency_ms = (time.time() - start_time) * 1000
            return LLMResponse(
                content="",
                model=self.config.model,
                backend_name=self.name,
                success=False,
                latency_ms=latency_ms,
                error_message="요청 타임아웃"
            )

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return LLMResponse(
                content="",
                model=self.config.model,
                backend_name=self.name,
                success=False,
                latency_ms=latency_ms,
                error_message=str(e)
            )

    async def pull_model(self, model_name: str | None = None) -> bool:
        """
        모델 다운로드

        Args:
            model_name: 다운로드할 모델 이름 (기본값: config.model)

        Returns:
            bool: 성공 여부
        """
        model = model_name or self.config.model

        try:
            if ASYNC_CLIENT:
                client = await self._get_client()
                response = await client.post(
                    f"{self.base_url}/api/pull",
                    json={"name": model, "stream": False},
                    timeout=600  # 10분 타임아웃
                )
                return response.status_code == 200

            response = requests.post(
                f"{self.base_url}/api/pull",
                json={"name": model, "stream": False},
                timeout=600
            )
            return response.status_code == 200

        except Exception as e:
            print(f"모델 다운로드 실패: {e}")
            return False

    async def close(self):
        """클라이언트 정리"""
        if ASYNC_CLIENT and self._client and not self._client.is_closed:
            await self._client.aclose()
