"""
Anthropic Backend
Claude 모델 연결 백엔드
"""

import os
import time

from .base import LLMBackend, LLMConfig, LLMResponse


class AnthropicBackend(LLMBackend):
    """
    Anthropic Claude API 백엔드

    Claude 3 Opus, Sonnet, Haiku 모델 지원.
    API Key는 환경변수 ANTHROPIC_API_KEY 또는 생성자 매개변수로 전달.
    """

    # 모델별 최대 토큰 수
    MODEL_MAX_TOKENS = {
        "claude-3-opus-20240229": 4096,
        "claude-3-sonnet-20240229": 4096,
        "claude-3-haiku-20240307": 4096,
        "claude-3-5-sonnet-20241022": 8192,
        "claude-3-5-sonnet-20240620": 8192,
        "claude-sonnet-4-20250514": 16384,
        "claude-opus-4-20250514": 16384,
        "claude-haiku-4-20250414": 8192,
    }

    def __init__(
        self,
        api_key: str | None = None,
        config: LLMConfig | None = None
    ):
        """
        Anthropic 백엔드 초기화

        Args:
            api_key: Anthropic API 키 (기본값: ANTHROPIC_API_KEY 환경변수)
            config: LLM 설정 (기본값: claude-3-sonnet)
        """
        if config is None:
            config = LLMConfig(model="claude-sonnet-4-20250514")

        super().__init__(config)
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client = None

    @property
    def name(self) -> str:
        return "anthropic"

    async def _get_client(self):
        """Anthropic 클라이언트 반환 (lazy initialization)"""
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic

                self._client = AsyncAnthropic(api_key=self.api_key)
            except ImportError:
                raise ImportError(
                    "anthropic 패키지가 필요합니다: pip install anthropic"
                )

        return self._client

    async def health_check(self) -> bool:
        """Anthropic API 상태 확인"""
        if not self.api_key:
            self.update_status(False)
            return False

        try:
            # 간단한 메시지로 API 연결 확인
            client = await self._get_client()

            # 최소 토큰으로 테스트
            await client.messages.create(
                model=self.config.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}]
            )

            self.update_status(True)
            return True

        except Exception as e:
            print(f"Anthropic health check 실패: {e}")
            self.update_status(False)
            return False

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs
    ) -> LLMResponse:
        """
        Anthropic API로 텍스트 생성

        Args:
            prompt: 입력 프롬프트
            system_prompt: 시스템 프롬프트
            **kwargs: 추가 옵션

        Returns:
            LLMResponse: 표준화된 응답
        """
        start_time = time.time()

        # 최대 토큰 결정
        model_max = self.MODEL_MAX_TOKENS.get(self.config.model, 4096)
        max_tokens = min(
            kwargs.get("max_tokens", self.config.max_tokens),
            model_max
        )

        try:
            client = await self._get_client()

            # 메시지 생성
            create_kwargs = {
                "model": self.config.model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }

            if system_prompt:
                create_kwargs["system"] = system_prompt

            response = await client.messages.create(**create_kwargs)

            latency_ms = (time.time() - start_time) * 1000

            # 응답에서 텍스트 추출
            content = ""
            for block in response.content:
                if hasattr(block, "text"):
                    content += block.text

            return LLMResponse(
                content=content,
                model=response.model,
                backend_name=self.name,
                success=True,
                latency_ms=latency_ms,
                tokens_used=response.usage.input_tokens + response.usage.output_tokens if response.usage else 0,
                raw_response={
                    "id": response.id,
                    "model": response.model,
                    "stop_reason": response.stop_reason,
                }
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

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs
    ):
        """
        스트리밍 텍스트 생성

        Yields:
            str: 텍스트 청크
        """
        model_max = self.MODEL_MAX_TOKENS.get(self.config.model, 4096)
        max_tokens = min(
            kwargs.get("max_tokens", self.config.max_tokens),
            model_max
        )

        create_kwargs = {
            "model": self.config.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }

        if system_prompt:
            create_kwargs["system"] = system_prompt

        try:
            client = await self._get_client()

            async with client.messages.stream(**create_kwargs) as stream:
                async for text in stream.text_stream:
                    yield text

        except Exception as e:
            print(f"스트리밍 생성 오류: {e}")
            raise

    async def close(self):
        """클라이언트 정리"""
        if self._client:
            await self._client.close()
            self._client = None
