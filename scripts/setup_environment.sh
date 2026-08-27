#!/usr/bin/env bash
# Bioinformatics Pipeline Environment Setup Script
# 지원 OS: Ubuntu/Debian (Linux), macOS (Homebrew)
# 설치 순서: Java → Python → Apptainer/Singularity → Nextflow → SRA-tools

set -euo pipefail

echo "=== Bioinformatics Pipeline Environment Setup ==="
echo "시작 시간: $(date)"

# --- OS 감지 ---
case "$(uname -s)" in
    Linux*)  OS="linux" ;;
    Darwin*) OS="macos" ;;
    *)       echo "지원하지 않는 OS: $(uname -s)"; exit 1 ;;
esac
echo "OS: ${OS} ($(uname -m))"

# macOS: Homebrew 확인
if [[ "$OS" == "macos" ]]; then
    if ! command -v brew &>/dev/null; then
        echo "Homebrew가 필요합니다: https://brew.sh"
        exit 1
    fi
    WORKSPACE="${WORKSPACE:-$HOME/workspace}"
else
    WORKSPACE="${WORKSPACE:-/workspace}"
fi

# --- 1. Java (Nextflow 의존성) ---
echo ""
echo "1. Java 설치 확인..."
if java -version &>/dev/null 2>&1; then
    echo "Java 이미 설치됨: $(java -version 2>&1 | head -1)"
else
    echo "Java 설치 중..."
    if [[ "$OS" == "macos" ]]; then
        brew install --cask temurin
    else
        apt-get update -qq
        apt-get install -y default-jdk
    fi
    echo "Java 설치 완료: $(java -version 2>&1 | head -1)"
fi

# --- 2. Python ---
echo ""
echo "2. Python 설치 확인..."
if command -v python3 &>/dev/null; then
    echo "Python3 이미 설치됨: $(python3 --version)"
else
    echo "Python3 설치 중..."
    if [[ "$OS" == "macos" ]]; then
        brew install python3
    else
        apt-get update -qq
        apt-get install -y python3 python3-pip python3-venv
    fi
    echo "Python3 설치 완료"
fi

# --- 3. Python 라이브러리 ---
echo ""
echo "3. Python 라이브러리 설치..."
if python3 -c "import requests, Bio, pandas, matplotlib" 2>/dev/null; then
    echo "모든 필수 라이브러리 이미 설치됨"
else
    python3 -m pip install --upgrade pip --break-system-packages 2>/dev/null || \
    python3 -m pip install --upgrade pip
    python3 -m pip install requests biopython pandas matplotlib plotly \
        --break-system-packages 2>/dev/null || \
    python3 -m pip install requests biopython pandas matplotlib plotly
fi

# --- 4. Apptainer / Singularity ---
echo ""
echo "4. Apptainer 설치 확인..."
if command -v apptainer &>/dev/null; then
    echo "Apptainer 이미 설치됨: $(apptainer --version)"
elif [[ "$OS" == "macos" ]]; then
    echo "macOS: Apptainer는 네이티브 미지원 — Docker로 대체합니다"
    if ! command -v docker &>/dev/null; then
        echo "  Docker Desktop 미설치 — 설치: brew install --cask docker"
        echo "  Nextflow는 Docker 없이도 로컬 실행 가능합니다 (컨테이너 없이)"
    else
        echo "  Docker 사용 가능: $(docker --version)"
    fi
else
    echo "Apptainer 설치 중..."
    apt-get update -qq
    apt-get install -y apptainer 2>/dev/null || \
        echo "  apt에 apptainer 없음 — Singularity fallback 사용"
fi

echo ""
echo "5. Singularity 설치 확인..."
if command -v singularity &>/dev/null; then
    echo "Singularity 이미 설치됨: $(singularity --version)"
elif [[ "$OS" == "macos" ]]; then
    echo "macOS: Singularity 네이티브 미지원 (Docker 대체)"
else
    echo "Singularity 설치 중..."
    apt-get update -qq
    apt-get install -y build-essential libssl-dev uuid-dev libgpgme11-dev squashfs-tools
    cd /tmp
    wget -q https://github.com/sylabs/singularity/releases/download/v4.1.1/singularity-4.1.1.tar.gz
    tar -xzf singularity-4.1.1.tar.gz
    cd singularity-4.1.1
    ./mconfig --prefix=/usr/local
    make -C builddir
    make -C builddir install
    cd -
    rm -rf /tmp/singularity-*
    echo "Singularity 설치 완료"
fi

# --- 6. Nextflow ---
echo ""
echo "6. Nextflow 설치 확인..."
if command -v nextflow &>/dev/null; then
    echo "Nextflow 이미 설치됨: $(nextflow -version 2>/dev/null | grep version | head -1)"
else
    echo "Nextflow 설치 중..."
    if [[ "$OS" == "macos" ]]; then
        # brew install nextflow는 macOS 12에서 gobject-introspection 빌드 실패
        # Java(temurin)가 있으면 공식 스크립트로 직접 설치
        curl -s https://get.nextflow.io | bash
        chmod +x nextflow
        mv nextflow "$HOME/.local/bin/nextflow" 2>/dev/null || \
        mv nextflow /usr/local/bin/nextflow
    else
        wget -qO- https://get.nextflow.io | bash
        chmod +x nextflow
        mv nextflow /usr/local/bin/
    fi
    echo "Nextflow 설치 완료: $(nextflow -version 2>/dev/null | grep version | head -1)"
fi

# --- 7. SRA-tools ---
echo ""
echo "7. SRA-tools 설치 확인..."
if command -v prefetch &>/dev/null || command -v fasterq-dump &>/dev/null; then
    echo "SRA-tools 이미 설치됨"
else
    echo "SRA-tools 설치 중..."
    if [[ "$OS" == "macos" ]]; then
        brew install sratoolkit 2>/dev/null && echo "SRA-tools 설치 완료" || \
            echo "  SRA-tools brew 설치 실패 — https://github.com/ncbi/sra-tools 수동 설치"
    else
        echo "SRA-tools는 NCBI에서 별도 설치 필요 (https://github.com/ncbi/sra-tools)"
    fi
fi

# --- 8. 작업 디렉토리 ---
echo ""
echo "8. 작업 디렉토리 생성..."
mkdir -p "${WORKSPACE}"/{raw_data,processed_data,nextflow_work,containers,results,logs,charts}
chmod 755 "${WORKSPACE}"/{raw_data,processed_data,nextflow_work,containers,results,logs,charts}
echo "작업 디렉토리: ${WORKSPACE}"

# --- 9. 환경 변수 (shell rc) ---
echo ""
echo "9. 환경 변수 설정..."
NXF_EXPORT="export NXF_WORK=\"${WORKSPACE}/nextflow_work\""
NXF_CACHE_EXPORT="export NXF_CACHE=\"${WORKSPACE}/containers\""

for rc in "$HOME/.zshrc" "$HOME/.bashrc"; do
    if [[ -f "$rc" ]] && ! grep -qF "NXF_WORK" "$rc" 2>/dev/null; then
        echo "" >> "$rc"
        echo "# nextflow" >> "$rc"
        echo "$NXF_EXPORT" >> "$rc"
        echo "$NXF_CACHE_EXPORT" >> "$rc"
        echo "  환경 변수 추가: $rc"
    fi
done

export NXF_WORK="${WORKSPACE}/nextflow_work"
export NXF_CACHE="${WORKSPACE}/containers"

# --- 10. 최종 확인 ---
echo ""
echo "10. 최종 설치 확인..."
echo "  Python3:    $(python3 --version 2>/dev/null || echo '없음')"
echo "  Java:       $(java -version 2>&1 | head -1 || echo '없음')"
echo "  Nextflow:   $(nextflow -version 2>/dev/null | grep version | head -1 || echo '없음')"
echo "  Apptainer:  $(apptainer --version 2>/dev/null || echo '없음 (macOS: Docker 대체)')"
echo "  Singularity:$(singularity --version 2>/dev/null || echo '없음')"
echo "  Docker:     $(docker --version 2>/dev/null || echo '없음')"
echo "  prefetch:   $(prefetch --version 2>/dev/null | head -1 || echo '없음')"
echo ""

# --- 11. 기능 테스트 ---
echo "11. 기능 테스트..."
python3 -c "import requests, Bio, pandas, matplotlib; print('  Python 라이브러리 정상')" 2>/dev/null || \
    echo "  Python 라이브러리 일부 누락"
nextflow -version &>/dev/null && echo "  Nextflow 정상" || echo "  Nextflow 실패"

echo ""
echo "=== 환경 설정 완료 ==="
echo "완료 시간: $(date)"
[[ "$OS" == "linux" ]] && echo "디스크 공간: $(df -h "${WORKSPACE}" | tail -1)"
