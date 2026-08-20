"""
LLM Backend Abstract Base Class
모든 LLM 백엔드의 추상 기본 클래스
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class BackendStatus(Enum):
    """백엔드 상태"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ErrorClass(Enum):
    """오류 재시도 분류 (LLM-003)"""
    RETRYABLE = "retryable"      # 잠시 후 재시도하면 달라질 수 있음
    RATE_LIMITED = "rate_limited"  # 시간이 지나야 풀림 — Retry-After 준수
    FATAL = "fatal"              # 재시도해도 같음 — 즉시 실패


# Melchizedek gateway 오류 계약 (llms.txt §4).
# "재시도해도 되는 것은 provider_busy·queue_full·timeout뿐이다."
_RETRYABLE_CODES = frozenset({"provider_busy", "queue_full", "timeout"})
_RATE_LIMITED_CODES = frozenset({"rate_limited"})
_FATAL_CODES = frozenset({
    "invalid_request", "unsupported_field", "invalid_routing_combination",
    "auth_failed", "model_not_allowed", "run_not_found", "input_too_large",
    "invalid_host", "provider_not_authenticated", "failover_exhausted",
    "routing_unavailable", "not_configured",
})

# gateway가 아닌 provider를 위한 HTTP status 기반 분류
_FATAL_STATUS = frozenset({400, 401, 403, 404, 413, 421, 422})
_RETRYABLE_STATUS = frozenset({408, 409, 425, 500, 502, 503, 504})


def _extract(error: Any, *names: str) -> Any:
    """error 또는 error.response에서 첫 번째로 발견되는 속성을 반환."""
    for target in (error, getattr(error, "response", None)):
        if target is None:
            continue
        for name in names:
            value = getattr(target, name, None)
            if value is not None:
                return value
    return None


def classify_error(error: Any) -> tuple[ErrorClass, float | None]:
    """오류를 재시도 분류와 대기 시간(초)으로 변환한다 (LLM-003).

    gateway는 `{"request_id","code","message"}` JSON을 주므로 **code를 우선**
    본다(llms.txt §4: message는 사람용이라 바뀔 수 있다). code가 없으면
    HTTP status로 판정하고, 그것도 없으면 네트워크 오류로 보아 재시도한다.

    Returns:
        (분류, retry_after 초 또는 None)
    """
    code = _extract(error, "code")
    if not isinstance(code, str):
        body = _extract(error, "body", "json")
        if isinstance(body, dict):
            code = body.get("code")

    status = _extract(error, "status_code", "status")

    retry_after: float | None = None
    headers = _extract(error, "headers")
    if headers is not None:
        raw = None
        try:
            raw = headers.get("retry-after") or headers.get("Retry-After")
        except AttributeError:
            raw = None
        if raw is not None:
            try:
                retry_after = float(raw)
            except (TypeError, ValueError):
                retry_after = None

    if isinstance(code, str):
        if code in _RATE_LIMITED_CODES:
            return ErrorClass.RATE_LIMITED, retry_after
        if code in _RETRYABLE_CODES:
            return ErrorClass.RETRYABLE, retry_after
        if code in _FATAL_CODES:
            return ErrorClass.FATAL, None

    if isinstance(status, int):
        if status == 429:
            return ErrorClass.RATE_LIMITED, retry_after
        if status in _FATAL_STATUS:
            return ErrorClass.FATAL, None
        if status in _RETRYABLE_STATUS:
            return ErrorClass.RETRYABLE, retry_after

    # 분류 불가(연결 끊김 등)는 일시적 장애로 본다
    return ErrorClass.RETRYABLE, retry_after


@dataclass
class LLMConfig:
    """LLM 백엔드 설정"""
    model: str
    temperature: float = 0.1
    top_p: float = 0.9
    max_tokens: int = 2000
    timeout: int = 60
    max_retries: int = 3
    extra_params: dict[str, Any] = field(default_factory=dict)


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
    raw_response: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "model": self.model,
            "backend_name": self.backend_name,
            "success": self.success,
            "latency_ms": self.latency_ms,
            "tokens_used": self.tokens_used,
            "error_message": self.error_message,
            "raw_response": self.raw_response,
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
        self._last_health_check: datetime | None = None
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
        system_prompt: str | None = None,
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
        system_prompt: str | None = None,
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
        last_response = None

        for attempt in range(self.config.max_retries):
            try:
                response = await self.generate(prompt, system_prompt, **kwargs)
                self._request_count += 1

                if response.success:
                    return response

                # 실패 응답: 재시도 (빈 응답, 서버 오류 등)
                last_response = response
                last_error = response.error_message

            except Exception as e:
                self._error_count += 1
                last_error = e

                # LLM-003: 재시도해도 같은 오류(인증·잘못된 요청 등)는 즉시 실패.
                # 그대로 재시도하면 설정 오류가 "모든 재시도 실패"로 가려진다.
                error_class, retry_after = classify_error(e)
                if error_class is ErrorClass.FATAL:
                    return LLMResponse(
                        content="",
                        model=self.config.model,
                        backend_name=self.name,
                        success=False,
                        latency_ms=0,
                        error_message=f"재시도 불가 오류: {e}",
                        raw_response={"error_class": error_class.value},
                    )
            else:
                retry_after = None

            if attempt < self.config.max_retries - 1:
                # rate_limited는 Retry-After를 준수한다 (llms.txt §4:
                # 즉시 재시도하면 같은 한도에 계속 걸린다).
                wait_time = retry_after if retry_after else 2 ** attempt
                await asyncio.sleep(wait_time)

        # 성공한 응답이 있으면 반환 (success=False라도)
        if last_response is not None:
            return last_response

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

    def get_metrics(self) -> dict[str, Any]:
        """백엔드 메트릭 반환"""
        return {
            "name": self.name,
            "status": self._status.value,
            "health_score": self.health_score,
            "request_count": self._request_count,
            "error_count": self._error_count,
            "last_health_check": self._last_health_check.isoformat() if self._last_health_check else None,
        }
