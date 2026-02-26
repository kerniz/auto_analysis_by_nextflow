#!/usr/bin/env python3
"""
DeepSeek-Coder LLM Analyzer
외부 DeepSeek-Coder 모델로 논문 vs 데이터 일관성 분석
"""

import requests
import json
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime

class DeepSeekAnalyzer:
    def __init__(self, server_url="http://10.0.1.54:11434", model="deepseek-coder:33b"):
        """DeepSeek-Coder 분석기 초기화"""
        self.server_url = server_url
        self.model = model
        self.timeout = 60
        self.max_retries = 3
        
    def test_connection(self) -> bool:
        """LLM 서버 접속 테스트"""
        try:
            response = requests.get(f"{self.server_url}/api/tags", timeout=10)
            if response.status_code == 200:
                models = response.json().get('models', [])
                model_names = [m['name'] for m in models]
                return self.model in model_names
            return False
        except Exception:
            return False
    
    def analyze_paper_data_consistency(self, pubmed_metadata: Dict, 
                                      sequencing_result: Dict, 
                                      pipeline_result: Dict) -> Dict:
        """논문 vs 데이터 일관성 분석"""
        print("DeepSeek-Coder 일관성 분석 시작...")
        
        pmid = pubmed_metadata.get("pmid", "unknown")
        seq_type = sequencing_result.get("predicted_type", "unknown")
        pipeline_status = pipeline_result.get("status", "unknown")
        
        analysis_result = {
            "pmid": pmid,
            "model": self.model,
            "analysis_timestamp": datetime.now().isoformat(),
            "sequencing_type": seq_type,
            "pipeline_status": pipeline_status,
            "consistency_score": 0.0,
            "consistency_rating": "UNKNOWN",
            "technical_assessment": "",
            "code_quality_notes": "",
            "data_quality_assessment": "",
            "recommendations": [],
            "error_message": ""
        }
        
        try:
            # 분석 프롬프트 생성
            prompt = self._generate_analysis_prompt(pubmed_metadata, sequencing_result, pipeline_result)
            
            # LLM 분석 요청
            llm_response = self._call_llm(prompt)
            
            if llm_response:
                # 응답 파싱
                parsed_result = self._parse_llm_response(llm_response)
                analysis_result.update(parsed_result)
                
                print(f"✅ DeepSeek-Coder 분석 완료: {analysis_result['consistency_rating']}")
            else:
                analysis_result["error_message"] = "LLM 응답 없음"
                print("❌ LLM 분석 실패: 응답 없음")
            
            return analysis_result
            
        except Exception as e:
            analysis_result["error_message"] = str(e)
            print(f"❌ DeepSeek-Coder 분석 예외: {e}")
            return analysis_result
    
    def _generate_analysis_prompt(self, pubmed_metadata: Dict, 
                                sequencing_result: Dict, 
                                pipeline_result: Dict) -> str:
        """분석 프롬프트 생성"""
        pmid = pubmed_metadata.get("pmid", "")
        title = pubmed_metadata.get("title", "")
        abstract = pubmed_metadata.get("abstract", "")
        seq_type = sequencing_result.get("predicted_type", "")
        confidence = sequencing_result.get("confidence", 0)
        pipeline_status = pipeline_result.get("status", "")
        execution_time = pipeline_result.get("execution_time_seconds", 0)
        
        prompt = f"""당신은 바이오인포매틱스 전문가입니다. 다음 논문과 데이터 분석 결과의 일관성을 평가해주세요.

## 논문 정보
PMID: {pmid}
제목: {title}
초록: {abstract[:1000]}...

## 시퀀싱 타입 분석 결과
예측 타입: {seq_type}
신뢰도: {confidence}

## 파이프라인 실행 결과
상태: {pipeline_status}
실행 시간: {execution_time/60:.1f}분

## 분석 요청
1. 논문의 주장과 시퀀싱 타입의 일관성을 평가하세요
2. 파이프라인 실행 결과의 기술적 타당성을 분석하세요
3. 데이터 품질과 분석 방법론의 적합성을 평가하세요
4. PASS/WARN/FAIL 중 하나로 최종 평가하고, 그 이유를 상세히 설명하세요

## 출력 형식
다음 JSON 형식으로 응답하세요:

{{
    "consistency_score": 0.0-1.0,
    "consistency_rating": "PASS|WARN|FAIL",
    "technical_assessment": "기술적 평가 상세 설명",
    "code_quality_notes": "코드 및 파이프라인 품질 평가",
    "data_quality_assessment": "데이터 품질 평가",
    "recommendations": ["추천사항1", "추천사항2"]
}}

분석 결과:"""
        
        return prompt
    
    def _call_llm(self, prompt: str) -> Optional[str]:
        """LLM API 호출"""
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    f"{self.server_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.1,
                            "top_p": 0.9,
                            "max_tokens": 2000
                        }
                    },
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return result.get('response', '')
                else:
                    print(f"LLM API 실패 (시도 {attempt + 1}): {response.status_code}")
                    
            except requests.exceptions.Timeout:
                print(f"LLM API 타임아웃 (시도 {attempt + 1})")
            except Exception as e:
                print(f"LLM API 예외 (시도 {attempt + 1}): {e}")
            
            if attempt < self.max_retries - 1:
                time.sleep(2 ** attempt)  # 지수 백오프
        
        return None
    
    def _parse_llm_response(self, response: str) -> Dict:
        """LLM 응답 파싱"""
        parsed = {
            "consistency_score": 0.0,
            "consistency_rating": "UNKNOWN",
            "technical_assessment": "",
            "code_quality_notes": "",
            "data_quality_assessment": "",
            "recommendations": []
        }
        
        try:
            # JSON 추출 시도
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start != -1 and json_end > json_start:
                json_str = response[json_start:json_end]
                json_data = json.loads(json_str)
                
                parsed.update(json_data)
                
                # 점수 정규화
                if isinstance(parsed.get("consistency_score"), (int, float)):
                    parsed["consistency_score"] = max(0, min(1, parsed["consistency_score"]))
                
                # 평가 등급 검증
                valid_ratings = ["PASS", "WARN", "FAIL"]
                if parsed.get("consistency_rating") not in valid_ratings:
                    # 점수 기반 등급 결정
                    score = parsed.get("consistency_score", 0)
                    if score >= 0.8:
                        parsed["consistency_rating"] = "PASS"
                    elif score >= 0.5:
                        parsed["consistency_rating"] = "WARN"
                    else:
                        parsed["consistency_rating"] = "FAIL"
                
            else:
                # JSON 파싱 실패 시 텍스트 기반 분석
                parsed = self._parse_text_response(response)
            
        except Exception as e:
            print(f"LLM 응답 파싱 실패: {e}")
            # 기본값으로 백업 평가
            parsed["technical_assessment"] = f"LLM 응답 파싱 실패: {str(e)}"
            parsed["consistency_rating"] = "WARN"
        
        return parsed
    
    def _parse_text_response(self, response: str) -> Dict:
        """텍스트 응답 파싱 (백업)"""
        parsed = {
            "consistency_score": 0.5,
            "consistency_rating": "WARN",
            "technical_assessment": response[:500],
            "code_quality_notes": "",
            "data_quality_assessment": "",
            "recommendations": []
        }
        
        # 텍스트에서 키워드 기반 평가
        response_lower = response.lower()
        
        if "pass" in response_lower or "일치" in response_lower or "적절" in response_lower:
            parsed["consistency_rating"] = "PASS"
            parsed["consistency_score"] = 0.8
        elif "fail" in response_lower or "불일치" in response_lower or "부적절" in response_lower:
            parsed["consistency_rating"] = "FAIL"
            parsed["consistency_score"] = 0.3
        
        parsed["technical_assessment"] = response[:1000]
        
        return parsed
    
    def save_analysis_result(self, result: Dict) -> str:
        """분석 결과 저장"""
        pmid = result.get("pmid", "unknown")
        filename = f"/workspace/results/deepseek_analysis_{pmid}.json"
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"DeepSeek 분석 결과 저장: {filename}")
            return filename
            
        except Exception as e:
            print(f"분석 결과 저장 실패: {e}")
            return ""
    
    def load_analysis_result(self, pmid: str) -> Optional[Dict]:
        """저장된 분석 결과 로드"""
        filename = f"/workspace/results/deepseek_analysis_{pmid}.json"
        
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    
    def generate_backup_analysis(self, pubmed_metadata: Dict, 
                               sequencing_result: Dict, 
                               pipeline_result: Dict) -> Dict:
        """백업 분석 생성 (LLM 실패 시)"""
        pmid = pubmed_metadata.get("pmid", "")
        seq_type = sequencing_result.get("predicted_type", "")
        confidence = sequencing_result.get("confidence", 0)
        pipeline_status = pipeline_result.get("status", "")
        
        backup_result = {
            "pmid": pmid,
            "model": "backup_algorithm",
            "analysis_timestamp": datetime.now().isoformat(),
            "sequencing_type": seq_type,
            "pipeline_status": pipeline_status,
            "consistency_score": 0.0,
            "consistency_rating": "WARN",
            "technical_assessment": "LLM 서버 접속 실패로 인한 백업 분석",
            "code_quality_notes": "",
            "data_quality_assessment": "",
            "recommendations": ["LLM 서버 상태 확인", "수동 분석 수행"],
            "error_message": "LLM 서버 접속 실패"
        }
        
        # 간단한 규칙 기반 평가
        if pipeline_status == "completed" and confidence > 0.7:
            backup_result["consistency_score"] = 0.6
            backup_result["consistency_rating"] = "WARN"
            backup_result["technical_assessment"] = f"파이프라인 성공적으로 완료됨 ({seq_type}), 신뢰도 {confidence}"
        elif pipeline_status == "failed":
            backup_result["consistency_score"] = 0.3
            backup_result["consistency_rating"] = "FAIL"
            backup_result["technical_assessment"] = "파이프라인 실행 실패로 데이터 분석 불가"
        
        return backup_result

def main():
    """테스트 실행"""
    print("=== DeepSeek-Coder 분석기 테스트 ===")
    
    analyzer = DeepSeekAnalyzer()
    
    # 서버 접속 테스트
    if not analyzer.test_connection():
        print("LLM 서버 접속 실패 - 백업 분석 테스트")
        # 백업 분석 테스트
        test_metadata = {"pmid": "40315330", "title": "Test", "abstract": "Test abstract"}
        test_seq = {"predicted_type": "scRNA-seq", "confidence": 0.8}
        test_pipeline = {"status": "completed", "execution_time_seconds": 3600}
        
        backup_result = analyzer.generate_backup_analysis(test_metadata, test_seq, test_pipeline)
        print(f"백업 분석 결과: {backup_result['consistency_rating']}")
        return
    
    # 테스트 데이터
    test_metadata = {
        "pmid": "40315330",
        "title": "Single-cell RNA sequencing reveals cellular heterogeneity",
        "abstract": "We performed single-cell RNA sequencing using 10x Genomics platform to analyze tumor microenvironment. Our analysis identified distinct cell populations and their gene expression patterns."
    }
    
    test_seq = {
        "predicted_type": "scRNA-seq",
        "confidence": 0.85
    }
    
    test_pipeline = {
        "status": "completed",
        "execution_time_seconds": 7200
    }
    
    # 분석 실행
    result = analyzer.analyze_paper_data_consistency(test_metadata, test_seq, test_pipeline)
    
    # 결과 출력
    print(f"분석 결과: {result['consistency_rating']}")
    print(f"일관성 점수: {result['consistency_score']}")
    print(f"기술적 평가: {result['technical_assessment'][:100]}...")
    
    # 결과 저장
    analyzer.save_analysis_result(result)

if __name__ == "__main__":
    main()