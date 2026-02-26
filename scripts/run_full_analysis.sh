#!/bin/bash

# Bioinformatics Pipeline One-Click Execution Script
# 전체 바이오인포매틱스 파이프라인 원클릭 실행

set -e

echo "=========================================="
echo "  바이오인포매틱스 파이프라인 자동 실행"
echo "=========================================="
echo "시작 시간: $(date)"
echo "작업 디렉토리: $(pwd)"
echo ""

# 함수 정의
print_status() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

print_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ❌ ERROR: $1"
}

print_success() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ SUCCESS: $1"
}

# 1. 사전 검사
print_status "사전 환경 검사 시작..."

# Python 확인
if ! command -v python3 &> /dev/null; then
    print_error "Python3 설치되지 않음"
    exit 1
fi

# 디스크 공간 확인
available_space=$(df /workspace | tail -1 | awk '{print $4}')
if [ "$available_space" -lt 1000000 ]; then  # 1TB 이하
    print_error "디스크 공간 부족: ${available_space}KB"
    exit 1
fi

print_success "사전 환경 검사 완료"

# 2. 환경 설정 (필요 시)
print_status "환경 설정 확인..."

if [ ! -f "/usr/local/bin/nextflow" ] || [ ! -d "/usr/local/bin/apptainer" ]; then
    print_status "환경 설정 스크립트 실행..."
    /workspace/setup_environment.sh
    if [ $? -eq 0 ]; then
        print_success "환경 설정 완료"
    else
        print_error "환경 설정 실패"
        exit 1
    fi
else
    print_success "환경 설정 이미 완료됨"
fi

# 3. LLM 서버 접속 확인
print_status "LLM 서버 접속 확인..."

if python3 /workspace/check_llm_server.py; then
    print_success "LLM 서버 접속 확인 완료"
else
    print_error "LLM 서버 접속 실패"
    exit 1
fi

# 4. 메인 파이프라인 실행
echo "[2026-01-11 $(date '+%H:%M:%S')] ✅ 메인 파이프라인 실행 시작..."
echo "[2026-01-11 $(date '+%H:%M:%S')] 대상 PMID: 40315330, 32416070"
echo "[2026-01-11 $(date '+%H:%M:%S')] 예상 실행 시간: 6-12시간"
echo "[2026-01-11 $(date '+%H:%M:%S')] Resume 기능: 활성화됨"
echo ""

# 파이프라인 실행
if python3 /workspace/main_pipeline.py; then
    print_success "메인 파이프라인 실행 완료"
else
    print_error "메인 파이프라인 실행 실패"
    exit 1
fi

# 5. 결과 확인
print_status "최종 결과 확인..."

if [ -f "/workspace/results/final_report_40315330.json" ] && [ -f "/workspace/results/final_report_32416070.json" ]; then
    print_success "모든 최종 리포트 생성 완료"
    
    # 요약 정보 출력
    print_status "실행 결과 요약:"
    
    for pmid in 40315330 32416070; do
        if [ -f "/workspace/results/final_report_${pmid}.json" ]; then
            echo "--- PMID ${pmid} ---"
            python3 -c "
import json
with open('/workspace/results/final_report_${pmid}.json', 'r') as f:
    data = json.load(f)
print(f'시퀀싱 타입: {data[\"sequencing_analysis\"][\"type\"]}')
print(f'파이프라인 상태: {data[\"pipeline_execution\"][\"status\"]}')
print(f'일관성 평가: {data[\"llm_analysis\"][\"consistency_rating\"]}')
print(f'전체 상태: {data[\"summary\"][\"overall_status\"]}')
"
        fi
    done
    
    # 실행 요약
    if [ -f "/workspace/results/execution_summary.json" ]; then
        echo ""
        echo "--- 전체 실행 요약 ---"
        python3 -c "
import json
with open('/workspace/results/execution_summary.json', 'r') as f:
    data = json.load(f)
summary = data['execution_summary']
print(f'총 처리: {summary[\"total_pmids\"]}개 PMID')
print(f'성공: {summary[\"successful_analyses\"]}개')
print(f'부분 성공: {summary[\"partial_successes\"]}개')
print(f'실패: {summary[\"failures\"]}개')
print(f'총 실행 시간: {data[\"total_execution_time_minutes\"]:.1f}분')
print(f'총 다운로드: {data[\"total_data_downloaded_gb\"]:.1f}GB')
"
    fi
    
else
    print_error "일부 최종 리포트 누락"
fi

# 6. 시각화 확인
print_status "시각화 차트 확인..."

chart_count=$(find /workspace/charts -name "*.png" 2>/dev/null | wc -l)
if [ "$chart_count" -gt 0 ]; then
    print_success "시각화 차트 ${chart_count}개 생성 완료"
    echo "생성된 차트:"
    find /workspace/charts -name "*.png" -exec basename {} \;
else
    print_status "시각화 차트 없음 (선택적 기능)"
fi

# 7. 로그 파일 확인
print_status "로그 파일 확인..."

log_files=(
    "/workspace/logs/nextflow_scrnaseq_40315330.log"
    "/workspace/logs/nextflow_rnaseq_32416070.log"
    "/workspace/progress.json"
)

for log_file in "${log_files[@]}"; do
    if [ -f "$log_file" ]; then
        size=$(du -h "$log_file" | cut -f1)
        print_status "로그 파일: $(basename $log_file) (${size})"
    fi
done

# 8. 최종 완료
print_status "디스크 사용량 확인:"
df -h /workspace | tail -1

echo ""
echo "=========================================="
echo "  바이오인포매틱스 파이프라인 완료"
echo "=========================================="
echo "완료 시간: $(date)"
echo "결과 디렉토리: /workspace/results"
echo "차트 디렉토리: /workspace/charts"
echo "로그 디렉토리: /workspace/logs"
echo ""

# 중요 파일 목록
echo "주요 결과 파일:"
find /workspace/results -name "*.json" -exec basename {} \; | sort

echo ""
echo "실행이 완료되었습니다. 결과를 확인하세요."