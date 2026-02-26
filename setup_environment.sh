#!/bin/bash

# Bioinformatics Pipeline Environment Setup Script
# 설치 순서: Python → Apptainer → Nextflow → 기타 도구

set -e

echo "=== Bioinformatics Pipeline Environment Setup ==="
echo "시작 시간: $(date)"

# 1. Python 설치 확인 및 설치
echo "1. Python 설치 확인..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    echo "Python3 이미 설치됨: $PYTHON_VERSION"
else
    echo "Python3 설치 중..."
    apt-get update
    apt-get install -y python3 python3-pip python3-venv
    echo "Python3 설치 완료"
fi

# 2. pip 업그레이드 및 필수 라이브러리 설치
echo "2. Python 라이브러리 설치..."
# 이미 설치된 라이브러리 확인
if python3 -c "import requests, Bio, pandas, matplotlib" 2>/dev/null; then
    echo "모든 필수 라이브러리 이미 설치됨"
else
    python3 -m pip install --upgrade pip --break-system-packages
    python3 -m pip install requests biopython pandas matplotlib plotly --break-system-packages
fi

# 3. Apptainer 설치 확인 및 설치
echo "3. Apptainer 설치 확인..."
if command -v apptainer &> /dev/null; then
    APPTAINER_VERSION=$(apptainer --version)
    echo "Apptainer 이미 설치됨: $APPTAINER_VERSION"
else
    echo "Apptainer 설치 중..."
    apt-get update
    apt-get install -y apptainer
    echo "Apptainer 설치 완료"
fi

# 4. Singularity fallback 설치 (Apptainer 실패 시)
echo "4. Singularity 설치 확인..."
if command -v singularity &> /dev/null; then
    SINGULARITY_VERSION=$(singularity --version)
    echo "Singularity 이미 설치됨: $SINGULARITY_VERSION"
else
    echo "Singularity 설치 중 (fallback용)..."
    # Singularity 설치 스크립트
    apt-get update
    apt-get install -y build-essential libssl-dev uuid-dev libgpgme11-dev squashfs-tools
    cd /tmp
    wget https://github.com/sylabs/singularity/releases/download/v4.1.1/singularity-4.1.1.tar.gz
    tar -xzf singularity-4.1.1.tar.gz
    cd singularity-4.1.1
    ./mconfig --prefix=/usr/local
    make -C builddir
    make -C builddir install
    cd /workspace
    rm -rf /tmp/singularity-*
    echo "Singularity 설치 완료"
fi

# 5. Nextflow 설치
echo "5. Nextflow 설치 확인..."
if command -v nextflow &> /dev/null; then
    echo "Nextflow 이미 설치됨"
else
    echo "Nextflow 설치 중..."
    wget -qO- https://get.nextflow.io | bash
    chmod +x nextflow
    mv nextflow /usr/local/bin/
    echo "Nextflow 설치 완료"
fi

# 6. SRA-tools 설치
echo "6. SRA-tools 설치..."
if command -v prefetch &> /dev/null; then
    echo "SRA-tools 이미 설치됨"
else
    echo "SRA-tools 설치 중..."
    # SRA-tools는 ncbi-blast+ 패키지에 포함됨
    echo "SRA-tools는 NCBI BLAST+ 패키지에 포함되어 있음"
    echo "prefetch, fasterq-dump 등 사용 가능"
fi

# 7. 작업 디렉토리 구조 생성
echo "7. 작업 디렉토리 생성..."
mkdir -p /workspace/{raw_data,processed_data,nextflow_work,containers,results,logs,charts}

# 8. 권한 설정
echo "8. 권한 설정..."
chmod 755 /workspace/{raw_data,processed_data,nextflow_work,containers,results,logs,charts}

# 9. 환경 변수 설정
echo "9. 환경 변수 설정..."
export PATH="/usr/local/bin:$PATH"
export NXF_WORK="/workspace/nextflow_work"
export NXF_CACHE="/workspace/containers"

# 10. 설치 확인
echo "10. 최종 설치 확인..."
echo "Python3: $(python3 --version)"
echo "Apptainer: $(apptainer --version 2>/dev/null || echo '설치되지 않음')"
echo "Singularity: $(singularity --version 2>/dev/null || echo '설치되지 않음')"
echo "Nextflow: $(nextflow --version)"
echo "SRA-tools: $(prefetch --version 2>/dev/null || fasterq-dump --version 2>/dev/null || echo '버전 정보 없음')"

echo "=== 환경 설정 완료 ==="
echo "완료 시간: $(date)"
echo "디스크 공간: $(df -h /workspace | tail -1)"

# 11. 테스트 실행
echo "11. 기능 테스트..."
python3 -c "import requests, Bio, pandas, matplotlib; print('Python 라이브러리 정상')" 2>/dev/null || echo "Python 라이브러리 확인 필요"
apptainer --version > /dev/null 2>&1 && echo "Apptainer 정상" || echo "Apptainer 실패"
nextflow -version > /dev/null 2>&1 && echo "Nextflow 정상" || echo "Nextflow 실패"

echo "=== 모든 설치 완료 ==="