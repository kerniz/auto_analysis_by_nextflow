"""
LLM Backend Abstract Base Class
모든 LLM 백엔드의 추상 기본 클래스
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum


class BackendStatus(Enum):
    """백엔드 상태"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class LLMConfig:
    """LLM 백엔드 설정"""
    model: str
    temperature: float = 0.1
    top_p: float = 0.9
    max_tokens: int = 2000
    timeout: int = 60
    max_retries: int = 3
    extra_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """LLM 응답 표준화 구조"""
    content: str
    model: str
    backend_name: str
    success: bool
    latency_ms: float
    tokens_used: int = 0
    error_message: str = ""
    raw_response: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "model": self.model,
            "backend_name": self.backend_name,
            "success": self.success,
            "latency_ms": self.latency_ms,
            "tokens_used": self.tokens_used,
            "error_message": self.error_message,
            "timestamp": self.timestamp.isoformat(),
        }


class LLMBackend(ABC):
    """
    LLM 백엔드 추상 기본 클래스
    
    모든 LLM 백엔드(Ollama, OpenAI, Anthropic 등)는 이 클래스를 상속받아 구현해야 합니다.
    """
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self._status = BackendStatus.UNKNOWN
        self._last_health_check: Optional[datetime] = None
        self._request_count = 0
        self._error_count = 0
    
    @property
    @abstractmethod
    def name(self) -> str:
        """백엔드 이름 (예: 'ollama', 'openai', 'anthropic')"""
        pass
    
    @property
    def status(self) -> BackendStatus:
        """현재 백엔드 상태"""
        return self._status
    
    @property
    def health_score(self) -> float:
        """0.0 ~ 1.0 사이의 건강 점수"""
        if self._request_count == 0:
            return 1.0
        return 1.0 - (self._error_count / self._request_count)
    
    @abstractmethod
    async def health_check(self) -> bool:
        """
        백엔드 건강 상태 확인
        
        Returns:
            bool: 백엔드가 정상 동작하면 True
        """
        pass
    
    @abstractmethod
    async def generate(
        self, 
        prompt: str, 
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        텍스트 생성
        
        Args:
            prompt: 입력 프롬프트
            system_prompt: 시스템 프롬프트 (선택사항)
            **kwargs: 추가 매개변수
            
        Returns:
            LLMResponse: 표준화된 응답
        """
        pass
    
    async def generate_with_retry(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        재시도 로직이 포함된 텍스트 생성
        
        Args:
            prompt: 입력 프롬프트
            system_prompt: 시스템 프롬프트
            **kwargs: 추가 매개변수
            
        Returns:
            LLMResponse: 표준화된 응답
        """
        import asyncio
        
        last_error = None
        
        for attempt in range(self.config.max_retries):
            try:
                response = await self.generate(prompt, system_prompt, **kwargs)
                self._request_count += 1
                return response
                
            except Exception as e:
                self._error_count += 1
                last_error = e
                
                if attempt < self.config.max_retries - 1:
                    # 지수 백오프
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)
        
        # 모든 재시도 실패
        return LLMResponse(
            content="",
            model=self.config.model,
            backend_name=self.name,
            success=False,
            latency_ms=0,
            error_message=f"모든 재시도 실패: {str(last_error)}"
        )
    
    def update_status(self, healthy: bool):
        """백엔드 상태 업데이트"""
        self._last_health_check = datetime.now()
        self._status = BackendStatus.HEALTHY if healthy else BackendStatus.UNHEALTHY
    
    def get_metrics(self) -> Dict[str, Any]:
        """백엔드 메트릭 반환"""
        return {
            "name": self.name,
            "status": self._status.value,
            "health_score": self.health_score,
            "request_count": self._request_count,
            "error_count": self._error_count,
            "last_health_check": self._last_health_check.isoformat() if self._last_health_check else None,
        }
