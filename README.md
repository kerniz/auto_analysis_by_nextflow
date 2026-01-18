## README.md 구성

```markdown
# 📄 Paper-to-Analysis: 자동 RNA-seq 재분석 파이프라인

논문 PMID 하나만으로 SRA 데이터 다운로드부터 분석, LLM 비교 요약까지 자동화

## ✨ 주요 기능

- **논문 → 데이터**: PMID/PRJNA/GSE에서 SRA ID 자동 추출
- **자동 다운로드**: recount3 → nf-core/fetchngs → prefetch 순차 시도
- **파이프라인 감지**: RNA-seq/ChIP-seq/ATAC-seq 등 자동 감지
- **논문 평가**: PubPeer, Altmetric, Scite, Semantic Scholar 자동 체크
- **LLM 비교**: 재분석 결과와 원본 논문 비교 분석

---

## 🚀 빠른 시작

### 설치

```bash
# 1. Conda 환경
conda create -n paper2analysis python=3.10 nextflow sra-tools
conda activate paper2analysis

# 2. Python 패키지
pip install pandas biopython requests

# 3. nf-core 파이프라인
nextflow pull nf-core/fetchngs
nextflow pull nf-core/rnaseq

# 4. Ollama (LLM)
# https://ollama.com 설치 후
ollama pull gemma3:27b

# 5. Apptainer (선택)
sudo apt install apptainer
```

### 기본 사용법

```bash
# PMID로 전체 파이프라인 실행
python paper_to_analysis.py 33234698

# BioProject로 실행
python paper_to_analysis.py PRJNA656047

# 샘플 수 제한
python paper_to_analysis.py 33234698 --max-samples 5

# 기존 결과만 요약
python paper_to_analysis.py --summarize-only --pmid 33234698
```

---

## 📊 출력 파일

```
fastq_data/
├── fastq/              # FASTQ 파일
└── samplesheet/        # 메타데이터

results/
├── star_salmon/
│   ├── salmon.merged.gene_counts.tsv  # Count matrix
│   └── recount3_*.tsv                  # (recount3 사용 시)
├── multiqc/
│   └── multiqc_report.html             # QC 리포트
└── pipeline_info/

samplesheet.csv         # nf-core 입력
```

---

## 🔧 고급 옵션

### 1. 논문 평가만

```python
from paper_to_analysis import check_paper_reputation

reputation = check_paper_reputation("33234698")
print(reputation['altmetric']['score'])
```

### 2. SRA ID 직접 지정

```python
from paper_to_analysis import download_data, create_samplesheet, run_rnaseq

sra_ids = ["SRR12345678", "SRR12345679"]
download_data(sra_ids, profile="apptainer")
create_samplesheet()
run_rnaseq()
```

### 3. 다른 파이프라인

```bash
# 코드에서 run_rnaseq() 대신
nextflow run nf-core/chipseq -profile apptainer --input samplesheet.csv
```

---

## 🎯 워크플로우

```
1. PMID 입력
   ↓
2. PubMed → SRA 링크 추출
   ↓
3. 다운로드 시도
   - recount3 (가장 빠름)
   - fetchngs (표준)
   - prefetch (fallback)
   ↓
4. Samplesheet 자동 생성
   - Layout (SE/PE) 감지
   - Strandedness 자동 판단
   ↓
5. nf-core/rnaseq 실행
   ↓
6. 논문 평가 + 전문 가져오기
   ↓
7. LLM으로 비교 분석
```

---

## 📝 주요 함수

| 함수 | 설명 |
|------|------|
| `paper_to_sra()` | PMID → SRR ID |
| `check_paper_reputation()` | 논문 평판 체크 |
| `download_counts_via_recount3()` | recount3 다운로드 |
| `run_fetchngs()` | nf-core/fetchngs |
| `detect_pipeline()` | 파이프라인 자동 감지 |
| `detect_strandedness_from_api()` | Strandedness 판단 |
| `create_samplesheet()` | Samplesheet 생성 |
| `run_rnaseq()` | nf-core/rnaseq 실행 |
| `analyze_results_with_llm()` | LLM 비교 분석 |

---

## ⚙️ 설정

### Entrez Email

```python
# 스크립트 상단
ENTREZ_EMAIL = "your@email.com"  # 필수 변경!
```

### Nextflow 프로필

```bash
# Docker
python paper_to_analysis.py 33234698 -profile docker

# Singularity/Apptainer
python paper_to_analysis.py 33234698 -profile apptainer

# 로컬 (비권장)
python paper_to_analysis.py 33234698 -profile standard
```

### LLM 모델 변경

```python
# analyze_results_with_llm() 함수 내
"model": "gemma3:27b"  # → "llama3:70b" 등으로 변경
```

---

## 🐛 문제 해결

### Q1: "nextflow not found"
```bash
conda install -c bioconda nextflow
```

### Q2: "prefetch not found"
```bash
conda install -c bioconda sra-tools
```

### Q3: fetchngs timeout
```bash
# fallback이 자동 실행됨
# 또는 수동으로:
prefetch SRR12345678
fasterq-dump SRR12345678 -O fastq_data/fastq
```

### Q4: LLM 연결 실패
```bash
# Ollama 실행 확인
ollama list
ollama serve  # 백그라운드 실행
```

### Q5: recount3 에러
```bash
# R 패키지 설치
R -e 'BiocManager::install("recount3")'
```

---

## 📚 참고 문서

- [nf-core/fetchngs](https://nf-co.re/fetchngs)
- [nf-core/rnaseq](https://nf-co.re/rnaseq)
- [recount3](https://rna.recount.bio/)
- [SRA Toolkit](https://github.com/ncbi/sra-tools)
- [Ollama](https://ollama.com/)

---

## 🔬 예시 분석

### COVID-19 RNA-seq 재분석

```bash
# Nature 논문 (PMID: 33234698)
python paper_to_analysis.py 33234698

# 출력:
[OK] Found 24 SRA IDs
[OK] Downloaded via recount3: 58,037 genes x 24 samples
[AI 비교 분석]
1. 재분석 결과 품질: 평균 매핑률 85.3%, 양호
2. 논문 주장 검증: 인터페론 반응 지연 확인 가능
3. 추가 분석 필요: DESeq2로 DEG, GSEA로 pathway
...
```

---

## 📄 라이선스

MIT License

## 🤝 기여

Issues/PR 환영합니다!
