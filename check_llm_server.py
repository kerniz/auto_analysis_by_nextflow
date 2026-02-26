#!/usr/bin/env python3
"""
LLM Server Connection Checker
DeepSeek-Coder 모델 서버 접속 확인 및 테스트
"""

import requests
import json
import sys
import time
from datetime import datetime

class LLMChecker:
    def __init__(self, server_url="http://localhost:11434", model="deepseek-coder:33b"):
        self.server_url = server_url
        self.model = model
        self.timeout = 60
        self.max_retries = 3
        
    def test_connection(self):
        """LLM 서버 접속 테스트"""
        print(f"LLM 서버 접속 테스트: {self.server_url}")
        
        for attempt in range(self.max_retries):
            try:
                # 서버 상태 확인
                response = requests.get(f"{self.server_url}/api/tags", timeout=30)
                
                if response.status_code == 200:
                    models = response.json().get('models', [])
                    model_names = [m['name'] for m in models]
                    
                    print(f"서버 접속 성공")
                    print(f"사용 가능 모델: {model_names}")
                    
                    # DeepSeek-Coder 모델 확인
                    if self.model in model_names:
                        print(f"DeepSeek-Coder 모델 확인: {self.model}")
                        return self.test_model_inference()
                    else:
                        print(f"경고: DeepSeek-Coder 모델을 찾을 수 없음")
                        print(f"사용 가능한 모델: {model_names}")
                        return False
                else:
                    print(f"서버 응답 오류: {response.status_code}")
                    
            except requests.exceptions.RequestException as e:
                print(f"접속 시도 {attempt + 1} 실패: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)  # 지수 백오프
                    
        print("LLM 서버 접속 최종 실패")
        return False
    
    def test_model_inference(self):
        """모델 추론 테스트"""
        print("DeepSeek-Coder 추론 테스트...")
        
        test_prompt = "간단한 테스트 응답해주세요."
        
        try:
            response = requests.post(
                f"{self.server_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": test_prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "top_p": 0.9,
                        "num_predict": 50  # 응답 길이 제한
                    }
                },
                timeout=30  # 짧은 타임아웃
            )
            
            if response.status_code == 200:
                result = response.json()
                analysis = result.get('response', '')
                print("추론 테스트 성공")
                print(f"모델 응답: {analysis}")
                return True
            else:
                print(f"추론 요청 실패: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"추론 테스트 실패: {e}")
            return False
    
    def get_model_info(self):
        """모델 정보 조회"""
        try:
            response = requests.get(f"{self.server_url}/api/show", 
                                  json={"name": self.model}, 
                                  timeout=10)
            
            if response.status_code == 200:
                return response.json()
            else:
                return None
                
        except Exception as e:
            print(f"모델 정보 조회 실패: {e}")
            return None

def main():
    """메인 실행 함수"""
    print("=== LLM 서버 확인 시작 ===")
    print(f"시작 시간: {datetime.now()}")
    
    checker = LLMChecker()
    
    # 서버 접속 테스트
    if checker.test_connection():
        print("✅ LLM 서버 정상")
        
        # 모델 정보 조회
        model_info = checker.get_model_info()
        if model_info:
            print(f"모델 정보: {json.dumps(model_info, indent=2, ensure_ascii=False)}")
        
        print("=== LLM 서버 확인 완료 ===")
        sys.exit(0)
    else:
        print("❌ LLM 서버 확인 실패")
        print("=== LLM 서버 확인 종료 ===")
        sys.exit(1)

if __name__ == "__main__":
    main()