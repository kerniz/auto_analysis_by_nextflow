"""
Terminal visual effects for bioauto.
DNA 헬릭스, 분자 시각화, 화려한 대기 애니메이션.
모든 대기 작업(검색, 분석, 파이프라인)에 공통으로 사용.
"""

import asyncio
import math
import random
import shutil
import sys
import unicodedata


def _display_width(text: str) -> int:
    """터미널에서 실제 차지하는 폭 계산 (한글=2, ASCII=1)."""
    w = 0
    for ch in text:
        eaw = unicodedata.east_asian_width(ch)
        w += 2 if eaw in ("W", "F") else 1
    return w


# ── ANSI Color Helpers ──────────────────────────────────────────────

def _rgb(r: int, g: int, b: int) -> str:
    return f"\033[38;2;{r};{g};{b}m"


def _bg_rgb(r: int, g: int, b: int) -> str:
    return f"\033[48;2;{r};{g};{b}m"


RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"
CLEAR_LINE = "\033[2K"
MOVE_UP = "\033[A"
SAVE_CURSOR = "\033[s"
RESTORE_CURSOR = "\033[u"


# ── Color Palettes ──────────────────────────────────────────────────

# Bio gradient: deep blue → cyan → green → lime
BIO_GRADIENT = [
    (20, 60, 180), (15, 90, 200), (10, 130, 210), (5, 170, 200),
    (0, 200, 180), (0, 210, 140), (20, 220, 100), (60, 230, 80),
    (100, 240, 60), (140, 250, 50),
]

# DNA colors
DNA_PALETTE = {
    "A": (255, 80, 80),    # Adenine — red
    "T": (80, 180, 255),   # Thymine — blue
    "G": (80, 255, 120),   # Guanine — green
    "C": (255, 200, 60),   # Cytosine — yellow
}

# Neon pulse colors
NEON_CYCLE = [
    (0, 255, 200), (0, 200, 255), (100, 100, 255),
    (200, 50, 255), (255, 50, 200), (255, 100, 100),
    (255, 200, 50), (200, 255, 50), (50, 255, 100),
]


# ── Category-specific Fun Facts ─────────────────────────────────────
# 카테고리별 문구: AnimatedWait(category="search") 등으로 자동 선택

FACTS_BY_CATEGORY: dict[str, list[str]] = {
    # 일반 / 기본
    "general": [
        "인간 유전체는 약 32억 개의 염기쌍으로 구성되어 있습니다",
        "DNA를 모두 풀면 태양까지 왕복할 수 있는 길이입니다",
        "인체에는 약 37조 개의 세포가 있습니다",
        "미토콘드리아 DNA는 모계로만 유전됩니다",
        "인간과 바나나의 DNA는 약 60% 유사합니다",
        "하나의 세포 안에 약 2미터의 DNA가 접혀 있습니다",
        "인간 유전자는 약 20,000~25,000개입니다",
        "장내 미생물 유전체는 인간 유전자의 150배입니다",
        "CRISPR는 세균의 면역 시스템에서 발견되었습니다",
        "RNA 스플라이싱으로 하나의 유전자가 여러 단백질을 만듭니다",
        "텔로미어는 세포 분열마다 짧아집니다",
        "후성유전학: DNA 서열 변화 없이 유전자 발현이 바뀝니다",
        "단일세포 RNA-seq로 개별 세포의 유전자 발현을 분석합니다",
        "Spatial transcriptomics로 조직 내 공간 정보를 보존합니다",
        "Oxford Nanopore로 100kb 이상의 긴 리드를 읽을 수 있습니다",
    ],
    # 논문 검색 중
    "search": [
        "PubMed에는 3,600만 건 이상의 생의학 논문이 색인되어 있습니다",
        "Semantic Scholar는 AI로 2억 건 이상의 논문을 분석합니다",
        "Europe PMC는 유럽 전역의 생명과학 문헌을 통합합니다",
        "h-index는 1946년 물리학자 Jorge Hirsch가 제안했습니다",
        "매년 약 300만 건의 새로운 생의학 논문이 발표됩니다",
        "최초의 DNA 구조 논문은 1953년 Nature에 1페이지로 실렸습니다",
        "DOI(Digital Object Identifier)는 2000년부터 사용되기 시작했습니다",
        "preprint 서버 bioRxiv는 2013년에 시작되었습니다",
        "평균적으로 과학 논문 하나에 5명의 저자가 참여합니다",
        "인용 반감기: 대부분의 논문은 발표 후 7~8년이 인용 피크입니다",
        "Open Access 논문은 구독 논문보다 평균 18% 더 많이 인용됩니다",
        "MeSH 용어는 29,000개 이상의 의학 주제어로 구성됩니다",
    ],
    # LLM 분석 / 상담 중
    "llm": [
        "LLM은 수천 개의 논문을 동시에 비교 분석할 수 있습니다",
        "멀티 에이전트 토론은 단일 모델보다 편향을 줄여줍니다",
        "PhD, 학부생, 일반인 세 관점에서 연구를 검토합니다",
        "합의 기반 분석은 여러 LLM의 답변 교집합을 찾습니다",
        "Chain-of-Thought 프롬프팅으로 추론 정확도가 향상됩니다",
        "Hallucination 방지를 위해 원문 기반 근거를 요구합니다",
        "토론 라운드가 진행될수록 의견이 수렴하는 경향이 있습니다",
        "에이전트 가중치로 전문가 의견에 더 높은 비중을 줍니다",
        "Temperature 값이 낮을수록 더 결정적인 응답을 생성합니다",
        "컨텍스트 윈도우가 클수록 더 많은 논문을 한번에 분석합니다",
        "RAG를 활용하면 최신 논문 정보를 실시간으로 반영합니다",
        "Few-shot 예시가 분석 품질을 크게 향상시킵니다",
    ],
    # 파이프라인 실행 중 (Nextflow, 분석)
    "pipeline": [
        "Nextflow는 10,000개 이상의 연구실에서 사용됩니다",
        "nf-core는 100개 이상의 표준화된 파이프라인을 제공합니다",
        "RNA-seq 분석의 핵심: alignment → quantification → DE analysis",
        "STAR aligner는 분당 수백만 개의 리드를 정렬할 수 있습니다",
        "DESeq2는 음이항 분포로 차등 발현 유전자를 탐지합니다",
        "scRNA-seq 하나의 실험에서 수만 개의 세포를 분석합니다",
        "UMAP 차원 축소로 세포 클러스터를 2D로 시각화합니다",
        "Salmon은 alignment-free 방식으로 빠른 정량화를 수행합니다",
        "MultiQC로 품질 지표를 한눈에 확인할 수 있습니다",
        "Singularity 컨테이너로 HPC에서 재현 가능한 분석을 합니다",
        "Slurm 스케줄러가 최적의 노드에 작업을 분배합니다",
        "nf-core/rnaseq v3.0+는 pseudo-alignment도 지원합니다",
        "FASTQ 파일 하나에 수억 개의 시퀀싱 리드가 들어 있습니다",
        "GRCh38은 현재 가장 널리 쓰이는 인간 참조 유전체입니다",
    ],
    # 데이터 수집 / PubMed / SRA
    "fetch": [
        "NCBI SRA에는 50 페타바이트 이상의 시퀀싱 데이터가 있습니다",
        "PubMed Central은 전문(full-text) 논문 800만 건을 무료 제공합니다",
        "SRA에서 FASTQ 변환은 fasterq-dump로 병렬 처리됩니다",
        "Entrez API는 초당 10건의 요청을 허용합니다 (API key 사용시)",
        "GEO(Gene Expression Omnibus)에는 500만 개 이상의 샘플이 있습니다",
        "BioProject 하나에 수백 개의 SRA 실험이 연결될 수 있습니다",
        "10x Genomics 데이터는 셀 바코드로 개별 세포를 구분합니다",
        "Illumina HiSeq는 한 번에 60억 개 리드를 생성할 수 있습니다",
        "SRA accession은 SRR/ERR/DRR로 시작하는 고유 ID입니다",
        "prefetch + fasterq-dump 조합이 가장 빠른 다운로드 방법입니다",
        "EBI의 ENA는 유럽 최대의 시퀀싱 데이터 아카이브입니다",
        "TCGA 프로젝트는 33개 암종, 20,000명 이상의 데이터를 보유합니다",
    ],
    # 농축 분석 / GSEA
    "enrichment": [
        "Gene Ontology는 44,000개 이상의 생물학적 용어를 정의합니다",
        "KEGG 경로 데이터베이스는 500개 이상의 대사/신호 경로를 포함합니다",
        "GSEA는 유전자 세트 수준의 변화를 탐지하는 강력한 방법입니다",
        "Enrichr는 200개 이상의 유전자 세트 라이브러리를 제공합니다",
        "FDR 보정으로 다중 검정 문제를 해결합니다",
        "Pathway 분석은 개별 유전자보다 생물학적 맥락을 제공합니다",
        "Reactome에는 2,600개 이상의 인간 생물학적 경로가 있습니다",
        "ORA(Over-Representation Analysis)는 가장 기본적인 농축 분석입니다",
        "Leading edge 분석으로 핵심 유전자를 식별할 수 있습니다",
        "MSigDB는 33,000개 이상의 유전자 세트 컬렉션을 보유합니다",
        "Hallmark 유전자 세트 50개로 주요 생물학적 상태를 요약합니다",
        "STRING DB는 단백질 상호작용 네트워크를 시각화합니다",
    ],
    # 보고서 생성
    "report": [
        "잘 정리된 보고서는 연구의 재현성을 높여줍니다",
        "HTML 보고서에 인터랙티브 차트를 포함할 수 있습니다",
        "종합보고서는 여러 PMID의 교차 분석 결과를 담습니다",
        "Volcano plot은 유의미한 차등 발현 유전자를 한눈에 보여줍니다",
        "Heatmap은 유전자 발현 패턴의 군집화를 시각화합니다",
        "PCA plot은 샘플 간 전체적인 변이를 2D로 요약합니다",
        "MA plot은 발현량과 변화량의 관계를 보여줍니다",
        "자동 생성 보고서로 수작업 시간을 90% 이상 절약합니다",
        "RAG 인덱싱으로 과거 분석 결과를 즉시 검색할 수 있습니다",
        "JSON 보고서는 프로그래밍 방식의 후속 분석에 활용됩니다",
    ],
}

# 하위 호환: 기존 SCIENCE_FACTS 유지
SCIENCE_FACTS = FACTS_BY_CATEGORY["general"]


def _get_facts(category: str | None = None) -> list[str]:
    """카테고리별 문구를 반환. None이면 전체에서 랜덤."""
    if category and category in FACTS_BY_CATEGORY:
        return FACTS_BY_CATEGORY[category]
    # 전체 카테고리에서 합쳐서 반환
    all_facts = []
    for facts in FACTS_BY_CATEGORY.values():
        all_facts.extend(facts)
    return all_facts


# ── DNA Helix Animation ────────────────────────────────────────────

class DNAHelixSpinner:
    """Animated double-helix spinner with nucleotide coloring."""

    BASES = "ATGC"
    HELIX_CHARS = "╭╮╰╯│─"

    def __init__(self, width: int = 40, height: int = 6):
        self.width = min(width, shutil.get_terminal_size().columns - 4)
        self.height = height
        self.frame = 0
        self.fact_index = random.randint(0, len(SCIENCE_FACTS) - 1)
        self.fact_timer = 0

    def render_frame(self) -> list[str]:
        lines = []
        t = self.frame * 0.3

        for y in range(self.height):
            row = []
            for x in range(self.width):
                phase = (x * 0.25) + t + (y * 0.5)
                sin_val = math.sin(phase)
                cos_val = math.cos(phase)

                # Two strands of DNA
                pos1 = int((sin_val + 1) * 2.5)  # 0-5
                pos2 = int((cos_val + 1) * 2.5)

                if y == pos1 and y == pos2:
                    # Base pair connection
                    base = self.BASES[x % 4]
                    r, g, b = DNA_PALETTE[base]
                    row.append(f"{_rgb(r, g, b)}{BOLD}═{RESET}")
                elif y == pos1:
                    base = self.BASES[(x + self.frame) % 4]
                    r, g, b = DNA_PALETTE[base]
                    brightness = 0.6 + 0.4 * abs(sin_val)
                    r, g, b = int(r * brightness), int(g * brightness), int(b * brightness)
                    row.append(f"{_rgb(r, g, b)}{base}{RESET}")
                elif y == pos2:
                    base = self.BASES[(x + self.frame + 2) % 4]
                    r, g, b = DNA_PALETTE[base]
                    brightness = 0.4 + 0.3 * abs(cos_val)
                    r, g, b = int(r * brightness), int(g * brightness), int(b * brightness)
                    row.append(f"{_rgb(r, g, b)}{base}{RESET}")
                else:
                    # Faint background particles
                    if random.random() < 0.02:
                        c = random.choice(NEON_CYCLE)
                        row.append(f"{_rgb(*c)}{DIM}·{RESET}")
                    else:
                        row.append(" ")

            lines.append("  " + "".join(row))

        return lines


# ── Wave Equalizer ──────────────────────────────────────────────────

class WaveEqualizer:
    """Audio-visualizer-style wave bars with bio gradient."""

    BLOCKS = " ▁▂▃▄▅▆▇█"

    def __init__(self, width: int = 50):
        self.width = min(width, shutil.get_terminal_size().columns - 4)
        self.frame = 0
        self.phases = [random.uniform(0, math.pi * 2) for _ in range(self.width)]
        self.speeds = [random.uniform(0.08, 0.2) for _ in range(self.width)]

    def render_frame(self) -> str:
        chars = []
        for i in range(self.width):
            phase = self.phases[i] + self.frame * self.speeds[i]
            val = (math.sin(phase) + math.sin(phase * 1.7 + 0.3) + 2) / 4
            level = int(val * (len(self.BLOCKS) - 1))

            # Color from gradient
            grad_idx = int(val * (len(BIO_GRADIENT) - 1))
            r, g, b = BIO_GRADIENT[grad_idx]

            # Pulse brightness
            pulse = 0.7 + 0.3 * math.sin(self.frame * 0.1 + i * 0.15)
            r, g, b = int(r * pulse), int(g * pulse), int(b * pulse)

            chars.append(f"{_rgb(r, g, b)}{self.BLOCKS[level]}{RESET}")

        self.frame += 1
        return "  " + "".join(chars)


# ── Molecule Orbit ──────────────────────────────────────────────────

class MoleculeOrbit:
    """Orbiting atoms / molecules animation."""

    ATOMS = ["●", "◉", "○", "◎", "⊙"]

    def __init__(self, width: int = 50):
        self.width = min(width, shutil.get_terminal_size().columns - 8)
        self.frame = 0
        self.orbits = [
            {"r": 8, "speed": 0.12, "char": "●", "color": (0, 255, 200)},
            {"r": 12, "speed": -0.08, "char": "◉", "color": (255, 100, 200)},
            {"r": 6, "speed": 0.18, "char": "○", "color": (100, 200, 255)},
            {"r": 15, "speed": -0.05, "char": "◎", "color": (255, 230, 50)},
            {"r": 10, "speed": 0.10, "char": "⊙", "color": (150, 100, 255)},
        ]

    def render_frame(self) -> str:
        canvas = [" "] * self.width
        center = self.width // 2

        # Center nucleus
        if center < self.width:
            pulse = 0.7 + 0.3 * math.sin(self.frame * 0.15)
            r, g, b = int(255 * pulse), int(255 * pulse), int(255 * pulse)
            canvas[center] = f"{_rgb(r, g, b)}{BOLD}⬡{RESET}"

        for orb in self.orbits:
            t = self.frame * orb["speed"]
            x = int(center + orb["r"] * math.cos(t))
            if 0 <= x < self.width:
                # Depth-based brightness
                depth = math.sin(t)
                cr, cg, cb = orb["color"]
                brightness = 0.4 + 0.6 * ((depth + 1) / 2)
                cr = int(cr * brightness)
                cg = int(cg * brightness)
                cb = int(cb * brightness)
                ch = orb["char"] if depth > 0 else "·"
                canvas[x] = f"{_rgb(cr, cg, cb)}{ch}{RESET}"

            # Orbit trail
            for trail in range(1, 4):
                tx = int(center + orb["r"] * math.cos(t - trail * orb["speed"] * 2))
                if 0 <= tx < self.width and canvas[tx] == " ":
                    fade = max(0.1, 0.4 - trail * 0.1)
                    cr, cg, cb = orb["color"]
                    cr, cg, cb = int(cr * fade), int(cg * fade), int(cb * fade)
                    canvas[tx] = f"{_rgb(cr, cg, cb)}·{RESET}"

        self.frame += 1
        return "  " + "".join(c if c != " " else " " for c in canvas)


# ── Typing Effect ───────────────────────────────────────────────────

async def typewriter(text: str, color: tuple = (0, 220, 200), speed: float = 0.02):
    """Print text with typewriter effect and color."""
    r, g, b = color
    sys.stdout.write(_rgb(r, g, b))
    for ch in text:
        sys.stdout.write(ch)
        sys.stdout.flush()
        if ch in ".,!?:;":
            await asyncio.sleep(speed * 4)
        elif ch == "\n":
            await asyncio.sleep(speed * 2)
        else:
            await asyncio.sleep(speed)
    sys.stdout.write(RESET)
    sys.stdout.flush()


# ── Fancy Banner ────────────────────────────────────────────────────

def print_consult_banner():
    """Print gorgeous startup banner for consult mode."""
    term_width = shutil.get_terminal_size().columns

    banner_lines = [
        "╔══════════════════════════════════════════════╗",
        "║                                              ║",
        "║    🧬  B I O A U T O   C O N S U L T  🔬    ║",
        "║                                              ║",
        "║    바이오인포매틱스 연구 상담 시스템              ║",
        "║                                              ║",
        "╚══════════════════════════════════════════════╝",
    ]

    print()
    for i, line in enumerate(banner_lines):
        # Gradient color per line
        t = i / max(len(banner_lines) - 1, 1)
        r = int(20 + 80 * t)
        g = int(200 - 60 * t)
        b = int(255 - 100 * t)
        padding = " " * max(0, (term_width - 48) // 2)
        print(f"{padding}{_rgb(r, g, b)}{BOLD}{line}{RESET}")

    # Subtitle with sparkle
    sub = "LLM 연구 탐색 → 논문 검색 → 자동 분석"
    sub_width = _display_width(sub)
    padding = " " * max(0, (term_width - sub_width) // 2)
    print(f"\n{padding}{_rgb(100, 200, 255)}{DIM}{sub}{RESET}\n")


# ── Status Line ─────────────────────────────────────────────────────

def print_status_bar(text: str, style: str = "info"):
    """Print a colored status bar."""
    term_width = shutil.get_terminal_size().columns
    colors = {
        "info": (50, 180, 255),
        "success": (50, 255, 120),
        "warn": (255, 200, 50),
        "error": (255, 80, 80),
        "magic": (200, 100, 255),
    }
    r, g, b = colors.get(style, colors["info"])

    bar_char = "━"
    # 실제 출력 폭: 들여쓰기(2) + 좌바 + 공백(1) + 텍스트 + 공백(1) + 우바
    # 터미널 폭의 75%로 제한하여 줄넘김 방지
    usable = min(term_width - 2, int(term_width * 0.75))
    side_len = max(1, (usable - _display_width(text) - 2) // 2)
    left = bar_char * side_len
    right = bar_char * side_len

    print(f"  {_rgb(r, g, b)}{DIM}{left}{RESET}"
          f" {_rgb(r, g, b)}{BOLD}{text}{RESET} "
          f"{_rgb(r, g, b)}{DIM}{right}{RESET}")


# ── Animated Waiting Context Manager ────────────────────────────────

class AnimatedWait:
    """
    Async context manager that shows a fancy animation while awaiting.

    Usage:
        async with AnimatedWait("분석 중"):
            result = await router.generate(...)

        async with AnimatedWait("논문 검색 중", category="search", style="molecule"):
            results = await searcher.search(query)

    Categories: general, search, llm, pipeline, fetch, enrichment, report
    Styles: dna, wave, molecule (auto-selected if omitted)
    """

    SPINNER_STYLES = ["dna", "wave", "molecule"]

    def __init__(
        self,
        message: str = "처리 중",
        style: str | None = None,
        category: str | None = None,
    ):
        self.message = message
        self.style = style or random.choice(self.SPINNER_STYLES)
        self.category = category
        self._task: asyncio.Task | None = None
        self._stop = False
        self._lines_drawn = 0

    async def __aenter__(self):
        self._stop = False
        self._task = asyncio.create_task(self._animate())
        return self

    async def __aexit__(self, *args):
        self._stop = True
        if self._task:
            await self._task
        # Clear the spinner line and show cursor
        sys.stdout.write(f"\r{CLEAR_LINE}{SHOW_CURSOR}")
        sys.stdout.flush()

    def _clear_lines(self):
        for _ in range(self._lines_drawn):
            sys.stdout.write(f"{MOVE_UP}{CLEAR_LINE}")
        sys.stdout.flush()
        self._lines_drawn = 0

    async def _animate(self):
        sys.stdout.write(HIDE_CURSOR)
        sys.stdout.flush()

        frame = 0
        dots_cycle = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

        while not self._stop:
            # 단일 라인: 스피너 + 메시지 + 경과시간 (제자리 업데이트)
            dot = dots_cycle[frame % len(dots_cycle)]
            elapsed = frame * 0.1
            neon_idx = frame % len(NEON_CYCLE)
            nr, ng, nb = NEON_CYCLE[neon_idx]
            line = (
                f"\r  {_rgb(nr, ng, nb)}{BOLD}{dot}{RESET} "
                f"{_rgb(180, 220, 255)}{self.message}{RESET}"
                f"{_rgb(100, 100, 120)}{DIM} ({elapsed:.1f}s){RESET}"
                f"{CLEAR_LINE}"
            )
            sys.stdout.write(line)
            sys.stdout.flush()
            self._lines_drawn = 0  # \r 사용하므로 줄 수 추적 불필요

            frame += 1
            await asyncio.sleep(0.1)


# ── Response Reveal ─────────────────────────────────────────────────

async def reveal_response(prefix: str, text: str, color: tuple = (0, 220, 200)):
    """Reveal assistant response with gradient typing effect."""
    r, g, b = color

    # Prefix (e.g., [상담사])
    sys.stdout.write(f"\n  {_rgb(100, 200, 255)}{BOLD}{prefix}{RESET} ")
    sys.stdout.flush()

    # Text with per-character gradient
    for i, ch in enumerate(text):
        # Subtle color shift
        shift = math.sin(i * 0.05) * 30
        cr = max(0, min(255, r + int(shift)))
        cg = max(0, min(255, g - int(shift * 0.5)))
        cb = max(0, min(255, b + int(shift * 0.3)))

        sys.stdout.write(f"{_rgb(cr, cg, cb)}{ch}")
        sys.stdout.flush()

        if ch in ".,!?:;":
            await asyncio.sleep(0.03)
        elif ch == "\n":
            await asyncio.sleep(0.015)
            sys.stdout.write("    ")  # indent continuation
        elif ch == " ":
            await asyncio.sleep(0.008)
        else:
            await asyncio.sleep(0.012)

    sys.stdout.write(f"{RESET}\n\n")
    sys.stdout.flush()


# ── Search Results Table ────────────────────────────────────────────

def _print_results_page(results: list, start: int, end: int, total: int):
    """결과 테이블의 한 페이지를 출력합니다."""
    header = f"  {'#':>3}  {'PMID':>10}  {'Year':>5}  {'Cited':>6}  Title"
    print(f"  {_rgb(150, 180, 220)}{BOLD}{header.strip()}{RESET}")
    sep = f"  {'─' * 3}  {'─' * 10}  {'─' * 5}  {'─' * 6}  {'─' * 40}"
    print(f"  {_rgb(80, 100, 130)}{sep.strip()}{RESET}")

    page_size = end - start
    for idx, r in enumerate(results[start:end]):
        i = start + idx + 1
        pmid_str = r.pmid or "N/A"
        year_str = str(r.year) if r.year else "?"
        title_str = r.title[:55] + "..." if len(r.title) > 55 else r.title

        t = (idx + 1) / max(page_size, 1)
        rr = int(50 + 150 * t)
        gg = int(220 - 80 * t)
        bb = int(255 - 50 * t)
        cite_color = (50, 255, 100) if r.citation_count > 50 else (200, 200, 200)

        row = (
            f"  {_rgb(rr, gg, bb)}{i:3d}{RESET}"
            f"  {_rgb(100, 200, 255)}{pmid_str:>10}{RESET}"
            f"  {_rgb(180, 180, 200)}{year_str:>5}{RESET}"
            f"  {_rgb(*cite_color)}{r.citation_count:6d}{RESET}"
            f"  {_rgb(rr, gg, bb)}{title_str}{RESET}"
        )
        print(row)


def print_results_table(results: list, page_size: int = 20):
    """검색 결과를 페이지 단위로 표시합니다. Enter로 다음 페이지."""
    if not results:
        return

    total = len(results)
    print()
    print_status_bar("검색 결과", "success")
    print()

    # 첫 페이지 출력
    end = min(page_size, total)
    _print_results_page(results, 0, end, total)

    # 남은 결과가 있으면 페이지네이션
    while end < total:
        remaining = total - end
        print(
            f"\n  {_rgb(120, 160, 200)}{DIM}"
            f"({end}/{total}건 표시) "
            f"Enter=다음 {min(page_size, remaining)}건 / "
            f"a=전체 / q=그만{RESET}"
        )
        try:
            choice = input("  ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break

        if choice == "q":
            break
        elif choice == "a":
            # 나머지 전부 표시
            _print_results_page(results, end, total, total)
            end = total
        else:
            # 다음 페이지
            next_end = min(end + page_size, total)
            _print_results_page(results, end, next_end, total)
            end = next_end

    print(f"\n  {_rgb(120, 160, 200)}{DIM}총 {total}건{RESET}\n")


# ── Prompt Decorator ────────────────────────────────────────────────

def fancy_prompt(turn: int = 0) -> str:
    """Return a colorful input prompt string.

    ANSI escape sequences are wrapped in \\x01…\\x02 so that
    readline correctly computes visible prompt width — this prevents
    cursor corruption when the user backspaces or types long lines.
    """
    colors = [
        (0, 255, 200), (100, 200, 255), (200, 150, 255),
        (255, 150, 200), (255, 200, 100),
    ]
    r, g, b = colors[turn % len(colors)]
    # \x01 / \x02 = readline RL_PROMPT_START_IGNORE / END_IGNORE
    color = f"\x01{_rgb(r, g, b)}{BOLD}\x02"
    reset = f"\x01{RESET}\x02"
    return f"{color}  You ▶{reset} "


def print_goodbye():
    """Print farewell message."""
    msg = "상담을 종료합니다. 좋은 연구 되세요! 🧬"
    print(f"\n  {_rgb(100, 200, 255)}{BOLD}{msg}{RESET}\n")


# ── Banners for other commands ──────────────────────────────────────

def print_search_banner(query: str):
    """Print banner for search command."""
    term_width = shutil.get_terminal_size().columns

    lines = [
        "╔══════════════════════════════════════════════╗",
        "║                                              ║",
        "║     🔍  B I O A U T O   S E A R C H  📚     ║",
        "║                                              ║",
        "╚══════════════════════════════════════════════╝",
    ]

    print()
    for i, line in enumerate(lines):
        t = i / max(len(lines) - 1, 1)
        r = int(50 + 100 * t)
        g = int(180 + 40 * (1 - t))
        b = int(255 - 50 * t)
        padding = " " * max(0, (term_width - 48) // 2)
        print(f"{padding}{_rgb(r, g, b)}{BOLD}{line}{RESET}")

    # Query display
    q_display = query if len(query) <= 50 else query[:47] + "..."
    padding = " " * max(0, (term_width - len(q_display) - 10) // 2)
    print(f"\n{padding}{_rgb(255, 200, 50)}{BOLD}  Query: {q_display}{RESET}\n")


def print_run_banner(pmids: list[str], project: str | None = None):
    """Print banner for run command."""
    term_width = shutil.get_terminal_size().columns

    lines = [
        "╔══════════════════════════════════════════════╗",
        "║                                              ║",
        "║    🧬  B I O A U T O   P I P E L I N E  🚀  ║",
        "║                                              ║",
        "║        전체 분석 파이프라인 실행                  ║",
        "║                                              ║",
        "╚══════════════════════════════════════════════╝",
    ]

    print()
    for i, line in enumerate(lines):
        t = i / max(len(lines) - 1, 1)
        r = int(80 + 120 * t)
        g = int(60 + 100 * (1 - t))
        b = int(220 - 80 * t)
        padding = " " * max(0, (term_width - 48) // 2)
        print(f"{padding}{_rgb(r, g, b)}{BOLD}{line}{RESET}")

    # PMIDs
    pmid_str = ", ".join(pmids[:5])
    if len(pmids) > 5:
        pmid_str += f" +{len(pmids) - 5} more"
    print(f"\n  {_rgb(0, 255, 200)}{BOLD}  PMIDs:{RESET} {_rgb(180, 220, 255)}{pmid_str}{RESET}")
    if project:
        print(f"  {_rgb(0, 255, 200)}{BOLD}  Project:{RESET} {_rgb(255, 200, 100)}{project}{RESET}")
    print()


def print_pipeline_stage(stage: str, pmid: str, index: int = 0, total: int = 1):
    """Print a pipeline stage transition line."""
    # Stage icons
    stage_icons = {
        "pubmed": "📄",
        "sra": "🗄️",
        "sequencing": "🧪",
        "fetchngs": "📥",
        "nf-core": "⚡",
        "analysis": "📊",
        "data_integration": "🔗",
        "enrichment": "🧬",
        "llm_analysis": "🤖",
        "debate": "💬",
        "report": "📋",
    }
    icon = stage_icons.get(stage, "▸")

    # Progress bar
    if total > 0:
        progress = index / total
        bar_width = 20
        filled = int(bar_width * progress)
        bar = (
            f"{_rgb(0, 255, 200)}{'█' * filled}"
            f"{_rgb(60, 60, 80)}{'░' * (bar_width - filled)}{RESET}"
        )
        pct = f"{progress * 100:.0f}%"
    else:
        bar = ""
        pct = ""

    print(
        f"  {icon} {_rgb(100, 200, 255)}{BOLD}{stage}{RESET}"
        f" {_rgb(150, 150, 180)}{DIM}[{pmid}]{RESET}"
        f"  {bar} {_rgb(180, 180, 200)}{pct}{RESET}"
    )


def print_completion_summary(
    total: int, completed: int, failed: int, duration: float
):
    """Print final completion summary with stats."""
    print()
    print_status_bar("실행 완료", "success")
    print()

    # Stats in colored boxes
    stats = [
        ("전체", total, (100, 200, 255)),
        ("완료", completed, (50, 255, 120)),
        ("실패", failed, (255, 80, 80) if failed > 0 else (100, 100, 120)),
    ]
    parts = []
    for label, count, color in stats:
        parts.append(
            f"{_rgb(*color)}{BOLD}{label}: {count}{RESET}"
        )
    print(f"  {' │ '.join(parts)}")

    # Duration
    if duration >= 60:
        dur_str = f"{duration / 60:.1f}분"
    else:
        dur_str = f"{duration:.1f}초"
    print(f"  {_rgb(180, 180, 200)}{DIM}소요 시간: {dur_str}{RESET}")
    print()


# ── Pipeline Progress Table (PMID × Stage 매트릭스) ──────────────

# 파이프라인 스테이지 정의 (순서대로)
_STAGES = [
    ("pubmed", "PubMed"),
    ("sra", "SRA"),
    ("sequencing", "시퀀싱감지"),
    ("data_aggregation", "데이터통합"),
    ("enrichment", "경로분석"),
    ("llm_consensus", "LLM분석"),
    ("debate", "토론"),
    ("rag_indexing", "RAG"),
    ("report", "보고서"),
]

# 스테이지별 컬럼 약어 (테이블 헤더용)
_STAGE_SHORT = ["PM", "SRA", "SEQ", "DATA", "GSEA", "LLM", "토론", "RAG", "RPT"]

# 스테이지별 색상
_STAGE_COLORS = [
    (80, 200, 255),   # pubmed — 하늘
    (100, 220, 200),  # sra — 민트
    (180, 150, 255),  # sequencing — 보라
    (255, 200, 100),  # data — 노랑
    (100, 255, 180),  # enrichment — 초록
    (255, 150, 200),  # llm — 핑크
    (200, 180, 255),  # debate — 라벤더
    (120, 230, 255),  # rag — 시안
    (255, 220, 120),  # report — 골드
]

# 셀 상태
_CELL_PENDING = 0
_CELL_RUNNING = 1
_CELL_DONE = 2
_CELL_FAIL = 3
_CELL_SKIP = 4


class StickyHeader:
    """터미널 최상단에 고정되는 PMID × Stage 매트릭스 테이블.

    각 행이 PMID, 각 열이 파이프라인 단계.
    셀은 ○(대기), ⠋(진행), ✓(완료), ✗(실패), -(스킵) 으로 표시.
    ANSI 스크롤 영역으로 상단을 고정하고 하단에서만 로그 스크롤.

    Usage:
        header = StickyHeader(model="auto", total_pmids=5, pmids=[...])
        header.start()
        header.update(pmid="12345", stage="pubmed")
        header.mark_done(pmid="12345", stage="pubmed")
        header.mark_fail(pmid="12345", stage="sra")
        header.stop()
    """

    _SPINNERS = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    _COL_W = 6  # 각 셀 폭

    def __init__(
        self,
        model: str = "",
        total_pmids: int = 0,
        pmids: list[str] | None = None,
    ):
        self.model = model
        self.total_pmids = total_pmids
        self.pmids = list(pmids or [])
        self._active = False
        self._rows = 0
        self._cols = 0
        self._frame = 0
        self._ticker_thread = None
        self._header_lines = 0  # 테이블이 차지하는 총 행 수

        # 셀 상태 매트릭스: {pmid: [stage0_status, stage1_status, ...]}
        self._matrix: dict[str, list[int]] = {}
        for p in self.pmids:
            self._matrix[p] = [_CELL_PENDING] * len(_STAGES)

        # 현재 진행 중인 PMID/stage (스피너 표시용)
        self._current_pmid = ""
        self._current_stage = ""

    def start(self):
        """테이블 활성화 — 스크롤 영역 설정 + 스피너 스레드 시작."""
        import threading

        size = shutil.get_terminal_size()
        self._rows = size.lines
        self._cols = size.columns
        self._active = True

        # 테이블 높이: 헤더(1) + 구분선(1) + PMID행(N) + 하단 구분선(1) = N+3
        # PMID가 너무 많으면 최대 높이 제한
        max_display = min(len(self.pmids), self._rows // 3)
        self._header_lines = max_display + 3
        scroll_start = self._header_lines + 1

        # 공간 확보
        sys.stdout.write("\n" * self._header_lines)
        sys.stdout.write(f"\033[{scroll_start};{self._rows}r")
        sys.stdout.write(f"\033[{scroll_start};1H")
        sys.stdout.flush()
        self._render()

        if sys.stdout.isatty():
            def _ticker():
                import time as _time
                while self._active:
                    _time.sleep(0.15)
                    self._frame += 1
                    if self._active:
                        try:
                            self._render()
                        except Exception:
                            break

            self._ticker_thread = threading.Thread(
                target=_ticker, daemon=True,
            )
            self._ticker_thread.start()

    def stop(self):
        """테이블 비활성화 — 스피너 스레드 종료 + 스크롤 영역 복원."""
        if not self._active:
            return
        self._active = False
        if self._ticker_thread:
            self._ticker_thread.join(timeout=0.5)
            self._ticker_thread = None
        sys.stdout.write(f"\033[1;{self._rows}r")
        sys.stdout.write(f"\033[{self._rows};1H")
        sys.stdout.flush()

    def update(
        self,
        pmid: str = "",
        stage: str = "",
        pmid_index: int = 0,
        message: str = "",
    ):
        """해당 PMID-Stage 셀을 '진행 중'으로 표시."""
        if pmid and pmid not in self._matrix:
            self._matrix[pmid] = [_CELL_PENDING] * len(_STAGES)
            if pmid not in self.pmids:
                self.pmids.append(pmid)
        if pmid:
            self._current_pmid = pmid
        if stage:
            self._current_stage = stage
            si = self._stage_idx(stage)
            if si >= 0 and pmid:
                # 이전 스테이지들 중 아직 pending인 것은 done으로
                for prev in range(si):
                    if self._matrix[pmid][prev] == _CELL_PENDING:
                        self._matrix[pmid][prev] = _CELL_DONE
                # 현재를 running으로
                self._matrix[pmid][si] = _CELL_RUNNING
        self._render()

    def mark_done(self, pmid: str, stage: str):
        """해당 셀을 '완료'로 표시."""
        si = self._stage_idx(stage)
        if si >= 0 and pmid in self._matrix:
            self._matrix[pmid][si] = _CELL_DONE
            self._render()

    def mark_fail(self, pmid: str, stage: str):
        """해당 셀을 '실패'로 표시."""
        si = self._stage_idx(stage)
        if si >= 0 and pmid in self._matrix:
            self._matrix[pmid][si] = _CELL_FAIL
            self._render()

    def mark_skip(self, pmid: str):
        """해당 PMID의 남은 모든 셀을 '스킵'으로 표시."""
        if pmid in self._matrix:
            for i in range(len(_STAGES)):
                if self._matrix[pmid][i] == _CELL_PENDING:
                    self._matrix[pmid][i] = _CELL_SKIP
            self._render()

    def set_model(self, model: str):
        """모델명 업데이트."""
        self.model = model
        self._render()

    def _stage_idx(self, stage: str) -> int:
        for i, (skey, _) in enumerate(_STAGES):
            if skey == stage:
                return i
        return -1

    def _render(self):
        """상단 테이블 전체 렌더링."""
        if not self._active:
            return

        cw = self._COL_W
        spin = self._SPINNERS[self._frame % len(self._SPINNERS)]

        # PMID 컬럼 폭: "PMID" + 8자리 + 여유
        pmid_w = 12

        sys.stdout.write(SAVE_CURSOR)

        row = 1  # 현재 출력 행

        # ── 헤더 행: 모델 + 스테이지 컬럼명 ──
        sys.stdout.write(f"\033[{row};1H{CLEAR_LINE}")
        header = f" {_bg_rgb(25, 30, 55)}{_rgb(120, 220, 255)}{BOLD}"
        header += f" 🧬 {self.model or 'auto':<{pmid_w - 4}s}"
        for i, short in enumerate(_STAGE_SHORT):
            cr, cg, cb = _STAGE_COLORS[i]
            header += f"{RESET}{_bg_rgb(25, 30, 55)}{_rgb(cr, cg, cb)}{BOLD}"
            header += f"{short:^{cw}s}"
        header += f"  {RESET}"
        sys.stdout.write(header)
        row += 1

        # ── 구분선 ──
        sys.stdout.write(f"\033[{row};1H{CLEAR_LINE}")
        sep = f" {_bg_rgb(20, 25, 45)}{_rgb(60, 70, 100)}"
        sep += "─" * pmid_w
        for _ in _STAGE_SHORT:
            sep += "─" * cw
        sep += f"──{RESET}"
        sys.stdout.write(sep)
        row += 1

        # ── PMID 행들 ──
        max_display = min(len(self.pmids), (self._rows // 3))
        for pi, pmid in enumerate(self.pmids[:max_display]):
            sys.stdout.write(f"\033[{row};1H{CLEAR_LINE}")
            cells = self._matrix.get(pmid, [_CELL_PENDING] * len(_STAGES))

            # PMID 완료 여부에 따라 행 배경색
            all_done = all(c in (_CELL_DONE, _CELL_SKIP) for c in cells)
            any_fail = any(c == _CELL_FAIL for c in cells)
            any_running = any(c == _CELL_RUNNING for c in cells)

            if any_fail:
                bg = _bg_rgb(40, 20, 20)
                pmid_color = _rgb(255, 100, 100)
            elif all_done:
                bg = _bg_rgb(20, 35, 25)
                pmid_color = _rgb(80, 220, 120)
            elif any_running:
                bg = _bg_rgb(25, 30, 45)
                pmid_color = _rgb(255, 255, 255)
            else:
                bg = _bg_rgb(20, 22, 35)
                pmid_color = _rgb(140, 150, 180)

            line = f" {bg}{pmid_color}"
            # PMID 짧게 표시
            pmid_short = pmid if len(pmid) <= 10 else pmid[:10]
            line += f" {pmid_short:<{pmid_w - 1}s}"

            for si, status in enumerate(cells):
                cr, cg, cb = _STAGE_COLORS[si]
                if status == _CELL_DONE:
                    cell = f"{_rgb(80, 220, 120)}  ✓ "
                elif status == _CELL_FAIL:
                    cell = f"{_rgb(255, 80, 80)}{BOLD}  ✗ "
                elif status == _CELL_RUNNING:
                    cell = f"{_rgb(cr, cg, cb)}{BOLD}  {spin} "
                elif status == _CELL_SKIP:
                    cell = f"{_rgb(70, 70, 90)}  ─ "
                else:
                    cell = f"{_rgb(50, 55, 75)}  ○ "
                line += f"{RESET}{bg}{cell}"

            # 진행률 (해당 PMID)
            done_count = sum(1 for c in cells if c in (_CELL_DONE, _CELL_SKIP))
            pct = int(done_count / len(_STAGES) * 100) if _STAGES else 0
            pct_color = (
                _rgb(80, 220, 120) if pct == 100
                else _rgb(255, 80, 80) if any_fail
                else _rgb(180, 180, 200)
            )
            line += f"{RESET}{bg}{pct_color}{pct:>4d}%{RESET}"

            sys.stdout.write(line)
            row += 1

        # ── 하단 구분선 + 요약 ──
        sys.stdout.write(f"\033[{row};1H{CLEAR_LINE}")
        total = len(self.pmids)
        done_pmids = sum(
            1 for p in self.pmids
            if all(c in (_CELL_DONE, _CELL_SKIP)
                   for c in self._matrix.get(p, []))
        )
        fail_pmids = sum(
            1 for p in self.pmids
            if any(c == _CELL_FAIL for c in self._matrix.get(p, []))
        )
        summary = (
            f" {_bg_rgb(20, 25, 40)}{_rgb(100, 120, 160)}"
            f" 전체 {total} │ "
            f"{_rgb(80, 220, 120)}완료 {done_pmids}{_rgb(100, 120, 160)} │ "
        )
        if fail_pmids:
            summary += f"{_rgb(255, 80, 80)}실패 {fail_pmids}{_rgb(100, 120, 160)} │ "
        summary += f"진행 {total - done_pmids - fail_pmids}"
        summary += f"  {RESET}"
        sys.stdout.write(summary)

        sys.stdout.write(RESTORE_CURSOR)
        sys.stdout.flush()
