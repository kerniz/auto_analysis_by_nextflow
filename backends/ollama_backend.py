"""
Ollama Backend
로컬 Ollama 서버 연결 백엔드 (DeepSeek 포함)
"""

import asyncio
import logging
import re
import time

from .base import LLMBackend, LLMConfig, LLMResponse

logger = logging.getLogger(__name__)

try:
    import httpx
    ASYNC_CLIENT = True
except ImportError:
    import requests
    ASYNC_CLIENT = False

_THINK_TAG_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)
_THINK_OPEN_RE = re.compile(r"<think>.*", re.DOTALL)
# qwen3 등에서 <think> 태그 없이 텍스트로 출력하는 사고 과정 패턴
# "Hmm, ...\n\n실제답변" 또는 "Okay, ...\n\n실제답변" 형태
_THINK_TEXT_RE = re.compile(
    r"^(?:Hmm|Okay|Let me|So,|Well,|First,|I need|The user|Wait|Alright)"
    r".*?(?:\n\n|\n(?=[A-Z\u3131-\u318E\uac00-\ud7a3]))",
    re.DOTALL,
)


def _strip_think(text: str) -> str:
    """Remove thinking content from model output.

    Handles:
    1. <think>...</think> 완전한 태그
    2. <think>... 닫히지 않은 태그 (토큰 제한으로 잘린 경우)
    3. 태그 없이 텍스트로 나오는 사고 과정 (qwen3)
    """
    # 1) 완전한 <think>...</think> 블록 제거
    text = _THINK_TAG_RE.sub("", text)
    # 2) 닫히지 않은 <think>... 제거
    text = _THINK_OPEN_RE.sub("", text)
    # 3) 텍스트 사고 패턴 제거 (반복 적용)
    for _ in range(5):
        m = _THINK_TEXT_RE.match(text)
        if not m:
            break
        text = text[m.end():]
    return text.strip()


class OllamaBackend(LLMBackend):
    """
    Ollama API 백엔드

    로컬 또는 원격 Ollama 서버에 연결하여 텍스트 생성을 수행합니다.
    model="auto"이면 서버에서 사용 가능한 모델 중 가장 큰 모델을 자동 선택합니다.
    """

    # 텍스트 생성에 적합하지 않은 모델 패턴 (임베딩, 번역 전용 등)
    _EXCLUDE_PATTERNS = (
        "embed", "snowflake", "translate", "rerank",
    )
    # 가용 메모리 대비 모델 크기 비율 상한
    _MEM_RATIO = 0.7

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        config: LLMConfig | None = None,
        failover_url: str | None = None,
    ):
        if config is None:
            config = LLMConfig(model="auto")

        super().__init__(config)
        self.base_url = base_url.rstrip("/")
        self._failover_url = failover_url.rstrip("/") if failover_url else None
        self._using_failover = False
        self._client = None
        self._auto_model = config.model in ("auto", "")
        self._model_resolved = False

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

    async def _fetch_models(self) -> list[dict]:
        """서버에서 모델 목록 가져오기."""
        if not ASYNC_CLIENT:
            return []
        client = await self._get_client()
        resp = await client.get(f"{self.base_url}/api/tags")
        if resp.status_code == 200:
            return resp.json().get("models", [])
        return []

    def _is_generation_model(self, model_info: dict) -> bool:
        """텍스트 생성용 모델인지 판별."""
        name = model_info.get("name", "").lower()
        return not any(p in name for p in self._EXCLUDE_PATTERNS)

    async def _estimate_max_model_gb(self) -> float:
        """서버 환경에 맞는 최대 모델 크기(GB) 추정.

        1) Ollama /api/ps에서 현재 VRAM 사용량 확인
        2) nvidia-smi 정보가 있으면 GPU VRAM 총량 사용
        3) 없으면 시스템 메모리 기반 (Mac 통합 메모리 고려)
        """
        client = await self._get_client()

        # 1) GPU VRAM: Ollama가 보고하는 로드 모델에서 추정
        try:
            ps_resp = await client.get(
                f"{self.base_url}/api/ps", timeout=min(self.config.timeout, 10)
            )
            if ps_resp.status_code == 200:
                ps_data = ps_resp.json()
                loaded = ps_data.get("models", [])
                if loaded:
                    # 로드된 모델의 size_vram 합계로 가용 VRAM 추정
                    total_vram = sum(
                        m.get("size_vram", 0) for m in loaded
                    )
                    if total_vram > 0:
                        vram_gb = total_vram / (1024 ** 3)
                        logger.debug(
                            "현재 VRAM 사용: %.1f GB", vram_gb
                        )
        except Exception:
            pass

        # 2) 시스템 메모리 기반 추정
        #    Mac: 통합 메모리의 ~70%를 GPU에 할당 가능
        #    Linux: GPU VRAM 별도이므로 시스템 메모리의 ~70%
        import platform
        try:
            import psutil
            total_mem_gb = psutil.virtual_memory().total / (1024 ** 3)
            avail_mem_gb = psutil.virtual_memory().available / (1024 ** 3)
        except ImportError:
            # psutil 없으면 /proc/meminfo 또는 기본값
            total_mem_gb = 64.0
            avail_mem_gb = 48.0
            try:
                with open("/proc/meminfo") as f:
                    for line in f:
                        if line.startswith("MemTotal:"):
                            total_mem_gb = (
                                int(line.split()[1]) / (1024 ** 2)
                            )
                        elif line.startswith("MemAvailable:"):
                            avail_mem_gb = (
                                int(line.split()[1]) / (1024 ** 2)
                            )
            except OSError:
                pass

        is_mac = platform.system() == "Darwin"
        if is_mac:
            # Mac 통합 메모리: 전체의 ~70% GPU 사용 가능
            max_gb = total_mem_gb * self._MEM_RATIO
        else:
            # Linux/Windows: 가용 메모리의 70%
            max_gb = avail_mem_gb * self._MEM_RATIO

        logger.debug(
            "모델 크기 상한: %.1f GB (총 %.1f GB, 가용 %.1f GB, %s)",
            max_gb, total_mem_gb, avail_mem_gb,
            "Mac" if is_mac else "Linux",
        )
        return max_gb

    async def _quick_test(self, model_name: str) -> bool:
        """모델이 실제 응답 가능한지 빠르게 테스트."""
        try:
            client = await self._get_client()
            resp = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model_name,
                    "prompt": "Hi",
                    "stream": False,
                    "think": False,
                    "options": {"num_predict": 5},
                },
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data.get("response", "") or data.get("thinking", "")
                return bool(content.strip())
        except Exception:
            pass
        return False

    async def _resolve_auto_model(self) -> str | None:
        """서버 모델 중 로드 가능한 가장 큰 모델 선택.

        1) /api/ps에서 이미 로드된 generation 모델을 우선 사용 (즉시 응답 가능).
        2) 로드된 모델이 없으면 크기순으로 시도하되 최대 3개만 테스트.
        """
        # 1) 이미 로드된 모델 확인
        try:
            client = await self._get_client()
            ps_resp = await client.get(
                f"{self.base_url}/api/ps", timeout=10,
            )
            if ps_resp.status_code == 200:
                loaded = ps_resp.json().get("models", [])
                for m in loaded:
                    name = m.get("name", "")
                    if name and self._is_generation_model({"name": name}):
                        logger.info("자동 모델: 이미 로드된 모델 사용 — %s", name)
                        return name
        except Exception:
            pass

        # 2) 전체 모델 목록에서 크기순 탐색 (최대 3개 시도)
        models = await self._fetch_models()

        candidates = []
        for m in models:
            if not self._is_generation_model(m):
                continue
            size_gb = m.get("size", 0) / (1024 ** 3)
            candidates.append((size_gb, m["name"]))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0], reverse=True)

        for size_gb, name in candidates[:3]:  # 최대 3개만 시도
            logger.info("자동 모델 후보 테스트: %s (%.1f GB)", name, size_gb)
            if await self._quick_test(name):
                logger.info(
                    "자동 모델 선택: %s (%.1f GB)", name, size_gb,
                )
                return name
            logger.debug("모델 %s 응답 불가, 다음 후보 시도", name)

        return None

    def _switch_to_failover(self) -> bool:
        """failover URL로 전환. 이미 failover 중이면 False."""
        if not self._failover_url or self._using_failover:
            return False
        logger.warning(
            "Ollama failover: %s → %s", self.base_url, self._failover_url,
        )
        self._primary_url = self.base_url
        self.base_url = self._failover_url
        self._using_failover = True
        # 클라이언트 리셋 (새 URL로 재연결)
        if self._client and not getattr(self._client, "is_closed", True):
            asyncio.get_event_loop().create_task(self._client.aclose())
        self._client = None
        return True

    async def health_check(self) -> bool:
        """Ollama 서버 상태 확인 + auto 모델 결정. 실패 시 failover URL 시도."""
        if not ASYNC_CLIENT:
            self.update_status(False)
            return False

        result = await self._health_check_single()
        if result:
            return True

        # primary 실패 → failover 시도
        if self._switch_to_failover():
            self._model_resolved = False  # failover 서버에서 모델 재탐색
            result = await self._health_check_single()
            if result:
                return True

        self.update_status(False)
        return False

    async def _health_check_single(self) -> bool:
        """현재 base_url에 대한 health check."""
        max_attempts = 2
        last_err = None

        for attempt in range(1, max_attempts + 1):
            try:
                models = await self._fetch_models()
                if not models:
                    last_err = "모델 목록이 비어 있음"
                    if attempt < max_attempts:
                        await asyncio.sleep(1)
                    continue

                # auto 모드: 모델 자동 선택
                if self._auto_model and not self._model_resolved:
                    chosen = await self._resolve_auto_model()
                    if chosen:
                        self.config.model = chosen
                        self._model_resolved = True
                        logger.info("Ollama 모델 결정: %s (%s)", chosen, self.base_url)
                    else:
                        last_err = "auto 모델 선택 실패"
                        if attempt < max_attempts:
                            await asyncio.sleep(1)
                        continue

                model_names = [m.get("name", "") for m in models]
                model_available = any(
                    self.config.model in n
                    or n.startswith(self.config.model.split(":")[0])
                    for n in model_names
                )

                self.update_status(model_available)
                return model_available

            except Exception as e:
                last_err = str(e)
                logger.warning(
                    "Ollama health check 시도 %d/%d 실패 (%s): %s",
                    attempt, max_attempts, self.base_url, e,
                )
                if attempt < max_attempts:
                    await asyncio.sleep(1)

        logger.warning("Ollama health check 실패 (%s): %s", self.base_url, last_err)
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
                "repeat_penalty": kwargs.get("repeat_penalty", 1.3),
                "repeat_last_n": 128,
            },
            # thinking 모델(qwen3 등)에서 사고를 별도 필드로 분리
            "think": False,
        }

        # JSON 형식 강제 (format 파라미터가 전달된 경우)
        if kwargs.get("format"):
            body["format"] = kwargs["format"]

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
                    content = data.get("response", "")

                    # thinking 모드 fallback: response가 비어도 thinking에 내용이 있으면 사용
                    if (not content or not content.strip()) and data.get("thinking"):
                        content = data["thinking"]
                        logger.debug("Ollama thinking 모드 응답 사용 (model=%s)", self.config.model)

                    # 빈 응답 감지: success=False로 처리하여 재시도 유도
                    if not content or not content.strip():
                        logger.warning(
                            "Ollama 빈 응답 (model=%s, prompt_tokens=%d)",
                            self.config.model,
                            data.get("prompt_eval_count", 0),
                        )
                        return LLMResponse(
                            content="",
                            model=self.config.model,
                            backend_name=self.name,
                            success=False,
                            latency_ms=latency_ms,
                            error_message="Empty response from model",
                        )

                    return LLMResponse(
                        content=_strip_think(content),
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
                    content = data.get("response", "")

                    # thinking 모드 fallback
                    if (not content or not content.strip()) and data.get("thinking"):
                        content = data["thinking"]

                    if not content or not content.strip():
                        logger.warning(
                            "Ollama 빈 응답 (sync, model=%s)",
                            self.config.model,
                        )
                        return LLMResponse(
                            content="",
                            model=self.config.model,
                            backend_name=self.name,
                            success=False,
                            latency_ms=latency_ms,
                            error_message="Empty response from model",
                        )

                    return LLMResponse(
                        content=_strip_think(content),
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

        except (ConnectionError, OSError) as e:
            # 연결 실패 시 failover 시도
            if self._switch_to_failover():
                logger.info("generate 연결 실패, failover로 재시도: %s", self.base_url)
                return await self.generate(prompt, system_prompt, **kwargs)
            latency_ms = (time.time() - start_time) * 1000
            return LLMResponse(
                content="",
                model=self.config.model,
                backend_name=self.name,
                success=False,
                latency_ms=latency_ms,
                error_message=str(e)
            )

        except Exception as e:
            # httpx.ConnectError 등도 failover 시도
            err_name = type(e).__name__
            if "Connect" in err_name and self._switch_to_failover():
                logger.info("generate %s, failover로 재시도: %s", err_name, self.base_url)
                return await self.generate(prompt, system_prompt, **kwargs)
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
                    timeout=max(self.config.timeout, 600)
                )
                return response.status_code == 200

            response = requests.post(
                f"{self.base_url}/api/pull",
                json={"name": model, "stream": False},
                timeout=max(self.config.timeout, 600),
            )
            return response.status_code == 200

        except Exception as e:
            print(f"모델 다운로드 실패: {e}")
            return False

    async def close(self):
        """클라이언트 정리"""
        if ASYNC_CLIENT and self._client and not self._client.is_closed:
            await self._client.aclose()
