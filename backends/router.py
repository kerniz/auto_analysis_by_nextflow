"""
LLM Router
다중 LLM 백엔드 라우팅 및 폴백 관리
"""

import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field

from .base import LLMBackend, LLMResponse, LLMConfig, BackendStatus


@dataclass
class RouterConfig:
    """라우터 설정"""
    strategy: str = "priority"  # priority, round_robin, health_based, random
    health_check_interval: int = 60  # 초
    enable_auto_failover: bool = True
    max_concurrent_requests: int = 10


@dataclass
class RouterMetrics:
    """라우터 메트릭"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    backend_usage: Dict[str, int] = field(default_factory=dict)
    fallback_count: int = 0
    last_request_time: Optional[datetime] = None


class LLMRouter:
    """
    LLM 백엔드 라우터
    
    여러 LLM 백엔드를 관리하고, 우선순위/상태 기반 라우팅을 제공합니다.
    백엔드 장애 시 자동으로 다음 백엔드로 폴백합니다.
    """
    
    def __init__(
        self,
        backends: List[LLMBackend],
        config: Optional[RouterConfig] = None
    ):
        """
        라우터 초기화
        
        Args:
            backends: LLM 백엔드 리스트 (우선순위 순)
            config: 라우터 설정
        """
        self.backends = {backend.name: backend for backend in backends}
        self.backend_order = [backend.name for backend in backends]
        self.config = config or RouterConfig()
        self.metrics = RouterMetrics()
        self._current_index = 0
        self._health_check_task: Optional[asyncio.Task] = None
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent_requests)
    
    @property
    def available_backends(self) -> List[str]:
        """사용 가능한 백엔드 목록"""
        return [
            name for name, backend in self.backends.items()
            if backend.status == BackendStatus.HEALTHY
        ]
    
    async def start(self):
        """라우터 시작 (백그라운드 헬스체크)"""
        # 초기 헬스체크
        await self.health_check_all()
        
        # 주기적 헬스체크 시작
        if self.config.health_check_interval > 0:
            self._health_check_task = asyncio.create_task(
                self._periodic_health_check()
            )
    
    async def stop(self):
        """라우터 정지"""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        # 모든 백엔드 정리
        for backend in self.backends.values():
            if hasattr(backend, 'close'):
                await backend.close()
    
    async def _periodic_health_check(self):
        """주기적 헬스체크"""
        while True:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                await self.health_check_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"헬스체크 오류: {e}")
    
    async def health_check_all(self) -> Dict[str, bool]:
        """모든 백엔드 헬스체크"""
        results = {}
        
        tasks = [
            backend.health_check()
            for backend in self.backends.values()
        ]
        
        check_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for name, result in zip(self.backends.keys(), check_results):
            if isinstance(result, Exception):
                results[name] = False
                print(f"백엔드 {name} 헬스체크 실패: {result}")
            else:
                results[name] = result
        
        return results
    
    def _select_backend(self) -> Optional[str]:
        """전략에 따른 백엔드 선택"""
        if self.config.strategy == "priority":
            # 우선순위 기반: 첫 번째 사용 가능한 백엔드
            for name in self.backend_order:
                if self.backends[name].status == BackendStatus.HEALTHY:
                    return name
        
        elif self.config.strategy == "round_robin":
            # 라운드 로빈
            available = self.available_backends
            if available:
                self._current_index = (self._current_index + 1) % len(available)
                return available[self._current_index]
        
        elif self.config.strategy == "health_based":
            # 건강 점수 기반
            best_backend = None
            best_score = -1
            
            for name in self.backend_order:
                backend = self.backends[name]
                if backend.status == BackendStatus.HEALTHY:
                    score = backend.health_score
                    if score > best_score:
                        best_score = score
                        best_backend = name
            
            return best_backend
        
        elif self.config.strategy == "random":
            # 랜덤 선택
            import random
            available = self.available_backends
            if available:
                return random.choice(available)
        
        return None
    
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        preferred_backend: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        텍스트 생성 (자동 폴백)
        
        Args:
            prompt: 입력 프롬프트
            system_prompt: 시스템 프롬프트
            preferred_backend: 선호 백엔드 (선택사항)
            **kwargs: 추가 옵션
            
        Returns:
            LLMResponse: 표준화된 응답
        """
        async with self._semaphore:
            self.metrics.total_requests += 1
            self.metrics.last_request_time = datetime.now()
            
            # 백엔드 선택
            if preferred_backend and preferred_backend in self.backends:
                backend_names = [preferred_backend] + [
                    name for name in self.backend_order
                    if name != preferred_backend
                ]
            else:
                backend_names = self.backend_order.copy()
            
            last_error = None
            
            for backend_name in backend_names:
                backend = self.backends.get(backend_name)
                
                if not backend:
                    continue
                
                # 비정상 백엔드 스킵 (폴백이 활성화된 경우)
                if (self.config.enable_auto_failover and 
                    backend.status == BackendStatus.UNHEALTHY):
                    continue
                
                try:
                    response = await backend.generate_with_retry(
                        prompt, system_prompt, **kwargs
                    )
                    
                    if response.success:
                        self.metrics.successful_requests += 1
                        self.metrics.backend_usage[backend_name] = \
                            self.metrics.backend_usage.get(backend_name, 0) + 1
                        return response
                    
                    last_error = response.error_message
                    
                except Exception as e:
                    last_error = str(e)
                    print(f"백엔드 {backend_name} 실패: {e}")
                    
                    # 백엔드 상태 업데이트
                    backend.update_status(False)
                    
                    if self.config.enable_auto_failover:
                        self.metrics.fallback_count += 1
                        continue
            
            # 모든 백엔드 실패
            self.metrics.failed_requests += 1
            
            return LLMResponse(
                content="",
                model="unknown",
                backend_name="router",
                success=False,
                latency_ms=0,
                error_message=f"모든 백엔드 실패: {last_error}"
            )
    
    def add_backend(self, backend: LLMBackend, priority: Optional[int] = None):
        """백엔드 추가"""
        self.backends[backend.name] = backend
        
        if priority is not None:
            self.backend_order.insert(priority, backend.name)
        else:
            self.backend_order.append(backend.name)
    
    def remove_backend(self, name: str):
        """백엔드 제거"""
        if name in self.backends:
            del self.backends[name]
            self.backend_order.remove(name)
    
    def get_metrics(self) -> Dict[str, Any]:
        """라우터 메트릭 반환"""
        return {
            "total_requests": self.metrics.total_requests,
            "successful_requests": self.metrics.successful_requests,
            "failed_requests": self.metrics.failed_requests,
            "success_rate": (
                self.metrics.successful_requests / self.metrics.total_requests * 100
                if self.metrics.total_requests > 0 else 0
            ),
            "fallback_count": self.metrics.fallback_count,
            "backend_usage": self.metrics.backend_usage,
            "available_backends": self.available_backends,
            "backend_metrics": {
                name: backend.get_metrics()
                for name, backend in self.backends.items()
            },
        }
    
    def __repr__(self) -> str:
        return (
            f"LLMRouter(backends={list(self.backends.keys())}, "
            f"strategy={self.config.strategy})"
        )
