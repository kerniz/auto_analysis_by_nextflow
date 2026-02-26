"""
OpenAI Backend
OpenAI GPT 모델 연결 백엔드
"""

import os
import time
from typing import Dict, Optional, Any

from .base import LLMBackend, LLMConfig, LLMResponse


class OpenAIBackend(LLMBackend):
    """
    OpenAI API 백엔드
    
    GPT-4, GPT-3.5-turbo 등 OpenAI 모델 사용.
    API Key는 환경변수 OPENAI_API_KEY 또는 생성자 매개변수로 전달.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        config: Optional[LLMConfig] = None,
        base_url: Optional[str] = None
    ):
        """
        OpenAI 백엔드 초기화
        
        Args:
            api_key: OpenAI API 키 (기본값: OPENAI_API_KEY 환경변수)
            config: LLM 설정 (기본값: gpt-4)
            base_url: 커스텀 API URL (Azure OpenAI 등)
        """
        if config is None:
            config = LLMConfig(model="gpt-4")
        
        super().__init__(config)
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url
        self._client = None
    
    @property
    def name(self) -> str:
        return "openai"
    
    async def _get_client(self):
        """OpenAI 클라이언트 반환 (lazy initialization)"""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                
                client_kwargs = {"api_key": self.api_key}
                if self.base_url:
                    client_kwargs["base_url"] = self.base_url
                
                self._client = AsyncOpenAI(**client_kwargs)
            except ImportError:
                raise ImportError(
                    "openai 패키지가 필요합니다: pip install openai"
                )
        
        return self._client
    
    async def health_check(self) -> bool:
        """OpenAI API 상태 확인"""
        if not self.api_key:
            self.update_status(False)
            return False
        
        try:
            client = await self._get_client()
            # 간단한 모델 목록 조회로 확인
            models = await client.models.list()
            self.update_status(True)
            return True
            
        except Exception as e:
            print(f"OpenAI health check 실패: {e}")
            self.update_status(False)
            return False
    
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        OpenAI API로 텍스트 생성
        
        Args:
            prompt: 입력 프롬프트
            system_prompt: 시스템 프롬프트
            **kwargs: 추가 옵션
            
        Returns:
            LLMResponse: 표준화된 응답
        """
        start_time = time.time()
        
        # 메시지 구성
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            client = await self._get_client()
            
            response = await client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=kwargs.get("temperature", self.config.temperature),
                top_p=kwargs.get("top_p", self.config.top_p),
                max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
            )
            
            latency_ms = (time.time() - start_time) * 1000
            
            choice = response.choices[0]
            
            return LLMResponse(
                content=choice.message.content or "",
                model=response.model,
                backend_name=self.name,
                success=True,
                latency_ms=latency_ms,
                tokens_used=response.usage.total_tokens if response.usage else 0,
                raw_response={
                    "id": response.id,
                    "model": response.model,
                    "finish_reason": choice.finish_reason,
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
        system_prompt: Optional[str] = None,
        **kwargs
    ):
        """
        스트리밍 텍스트 생성
        
        Yields:
            str: 텍스트 청크
        """
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
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            print(f"스트리밍 생성 오류: {e}")
            raise
    
    async def close(self):
        """클라이언트 정리"""
        if self._client:
            await self._client.close()
            self._client = None
