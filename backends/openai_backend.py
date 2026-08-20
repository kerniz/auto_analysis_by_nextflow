"""
OpenAI Backend & Gateway-first OpenAI-compatible Routing
OpenAI GPT 및 Melchizedek Gateway 호환 백엔드
"""

import os
import time
from typing import Any

from .base import LLMBackend, LLMConfig, LLMResponse


class OpenAIBackend(LLMBackend):
    """
    OpenAI 및 OpenAI-compatible (Melchizedek Gateway 등) 백엔드

    GPT-4, GPT-3.5-turbo 및 Melchizedek Gateway 호환 모델 사용.
    API Key는 환경변수 OPENAI_API_KEY 또는 생성자 매개변수로 전달.
    """

    def __init__(
        self,
        api_key: str | None = None,
        config: LLMConfig | None = None,
        base_url: str | None = None,
        default_headers: dict[str, str] | None = None,
        client_label: str = "bioauto/general",
    ):
        """
        OpenAI 백엔드 초기화

        Args:
            api_key: OpenAI API 키 (기본값: OPENAI_API_KEY 환경변수 또는 gateway dummy key)
            config: LLM 설정 (기본값: gpt-4)
            base_url: 커스텀 API URL (Melchizedek Gateway, Azure OpenAI 등)
            default_headers: HTTP 기본 헤더
            client_label: Melchizedek 클라이언트 식별 라벨 (기본값: bioauto/general)
        """
        if config is None:
            config = LLMConfig(model="gpt-4")

        super().__init__(config)

        if base_url:
            self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or "dummy-gateway-key"
            self.default_headers = default_headers.copy() if default_headers else {}
            if "X-Melchizedek-Client" not in self.default_headers:
                self.default_headers["X-Melchizedek-Client"] = client_label or "bioauto/pipeline"
        else:
            self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
            self.default_headers = default_headers.copy() if default_headers else {}

        self.base_url = base_url
        self.client_label = client_label
        self._client = None

    @property
    def name(self) -> str:
        return "openai"

    async def _get_client(self):
        """OpenAI 클라이언트 반환 (lazy initialization)"""
        if self._client is None:
            try:
                from openai import AsyncOpenAI

                client_kwargs: dict[str, Any] = {
                    "api_key": self.api_key,
                    "default_headers": self.default_headers,
                }
                if self.base_url:
                    client_kwargs["base_url"] = self.base_url

                self._client = AsyncOpenAI(**client_kwargs)
            except ImportError:
                raise ImportError(
                    "openai 패키지가 필요합니다: pip install openai"
                )

        return self._client

    async def health_check(self) -> bool:
        """OpenAI / Gateway API 상태 확인"""
        try:
            client = await self._get_client()
            await client.models.list()
            self.update_status(True)
            return True
        except Exception as e:
            print(f"OpenAI health check 실패: {e}")
            self.update_status(False)
            return False

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs
    ) -> LLMResponse:
        """
        OpenAI/Gateway API로 텍스트 생성

        Args:
            prompt: 입력 프롬프트
            system_prompt: 시스템 프롬프트
            **kwargs: 추가 옵션 (extra_body, routing 등)

        Returns:
            LLMResponse: 표준화된 응답
        """
        start_time = time.time()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Gateway routing & extra body handling
        extra_body = kwargs.get("extra_body", {})
        if not extra_body and self.config.extra_params:
            extra_body = self.config.extra_params.get("extra_body", self.config.extra_params)

        create_kwargs: dict[str, Any] = {
            "model": kwargs.get("model", self.config.model),
            "messages": messages,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "top_p": kwargs.get("top_p", self.config.top_p),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
        }
        if extra_body:
            create_kwargs["extra_body"] = extra_body

        try:
            client = await self._get_client()
            response = await client.chat.completions.create(**create_kwargs)

            latency_ms = (time.time() - start_time) * 1000
            choice = response.choices[0]

            raw_resp: dict[str, Any] = {
                "id": getattr(response, "id", None),
                "model": response.model,
                "finish_reason": getattr(choice, "finish_reason", None),
            }
            # Extract route provenance if returned by gateway
            if hasattr(response, "route"):
                raw_resp["route"] = getattr(response, "route")
            elif isinstance(getattr(response, "model_extra", None), dict) and "route" in response.model_extra:
                raw_resp["route"] = response.model_extra["route"]

            return LLMResponse(
                content=choice.message.content or "",
                model=response.model,
                backend_name=self.name,
                success=True,
                latency_ms=latency_ms,
                tokens_used=response.usage.total_tokens if getattr(response, "usage", None) else 0,
                raw_response=raw_resp,
            )

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000

            return LLMResponse(
                content="",
                model=self.config.model,
                backend_name=self.name,
                success=False,
                latency_ms=latency_ms,
                error_message=str(e),
            )

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs
    ):
        """스트리밍 텍스트 생성"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            client = await self._get_client()

            stream = await client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=kwargs.get("temperature", self.config.temperature),
                stream=True,
            )

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            print(f"스트리밍 생성 오류: {e}")
            raise

    async def close(self):
        """클라이언트 정리"""
        if self._client:
            await self._client.close()
            self._client = None
