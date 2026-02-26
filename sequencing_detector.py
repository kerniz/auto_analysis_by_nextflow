#!/usr/bin/env python3
"""
Sequencing Type Detector
시퀀싱 타입 자동 판별 (scRNA-seq vs bulk RNA-seq)
"""

import re
import json
from typing import Dict, List, Tuple, Optional

class SequencingDetector:
    def __init__(self):
        """시퀀싱 타입 판별기 초기화"""
        
        # scRNA-seq 키워드
        self.scrna_keywords = [
            "single-cell", "single cell", "singlecell",
            "scrna-seq", "single-cell rna sequencing",
            "10x genomics", "drop-seq", "smart-seq",
            "cell ranger", "cellranger",
            "droplet", "microfluidic", "cell barcoding",
            "umis", "unique molecular identifiers",
            "cell capture", "cell isolation",
            "single nucleus", "snrna-seq",
            "c1", "fluidigm", "in-drop"
        ]
        
        # bulk RNA-seq 키워드
        self.bulk_keywords = [
            "bulk rna-seq", "bulk rna sequencing",
            "rna-seq", "rna sequencing",
            "transcriptome", "gene expression",
            "polya", "poly-a selection",
            "ribosomal depletion", "rrna depletion",
            "total rna", "whole transcriptome",
            "strand-specific", "directional"
        ]
        
        # 제외 키워드 (다른 시퀀싱 타입)
        self.exclude_keywords = [
            "dna-seq", "whole genome sequencing", "wgs",
            "chip-seq", "atac-seq", "hi-c", "methylation",
            "proteomics", "metabolomics", "genomics"
        ]
    
    def detect_sequencing_type(self, pubmed_metadata: Dict, sra_metadata: Dict) -> Dict:
        """시퀀싱 타입 판별"""
        print("시퀀싱 타입 판별 시작...")
        
        pmid = pubmed_metadata.get("pmid", "unknown")
        title = pubmed_metadata.get("title", "")
        abstract = pubmed_metadata.get("abstract", "")
        keywords = pubmed_metadata.get("keywords", [])
        
        # 텍스트 결합
        combined_text = f"{title} {abstract} {' '.join(keywords)}".lower()
        
        # 점수 계산
        scrna_score = self._calculate_scrna_score(combined_text)
        bulk_score = self._calculate_bulk_score(combined_text)
        
        # SRA 메타데이터 기반 추가 점수
        sra_scrna_score, sra_bulk_score = self._analyze_sra_metadata(sra_metadata)
        scrna_score += sra_scrna_score
        bulk_score += sra_bulk_score
        
        # 최종 판별
        if scrna_score > bulk_score and scrna_score > 0.3:
            predicted_type = "scRNA-seq"
            confidence = min(scrna_score, 1.0)
        elif bulk_score > scrna_score and bulk_score > 0.3:
            predicted_type = "bulk RNA-seq"
            confidence = min(bulk_score, 1.0)
        else:
            predicted_type = "unknown"
            confidence = 0.0
        
        # 결과 구성
        result = {
            "pmid": pmid,
            "predicted_type": predicted_type,
            "confidence": confidence,
            "scrna_score": round(scrna_score, 3),
            "bulk_score": round(bulk_score, 3),
            "sra_scrna_score": round(sra_scrna_score, 3),
            "sra_bulk_score": round(sra_bulk_score, 3),
            "evidence": self._collect_evidence(combined_text, sra_metadata),
            "recommended_pipeline": self._get_recommended_pipeline(predicted_type)
        }
        
        print(f"✅ 시퀀싱 타입 판별: {predicted_type} (신뢰도: {confidence:.2f})")
        return result
    
    def _calculate_scrna_score(self, text: str) -> float:
        """scRNA-seq 점수 계산"""
        score = 0.0
        
        # 키워드 매칭
        for keyword in self.scrna_keywords:
            if keyword in text:
                # 가중치 부여
                if "single-cell" in keyword or "single cell" in keyword:
                    score += 0.3
                elif "10x" in keyword or "cell ranger" in keyword:
                    score += 0.25
                elif "umis" in keyword or "droplet" in keyword:
                    score += 0.2
                else:
                    score += 0.15
        
        # 문맥 기반 추가 점수
        if re.search(r'cell.*count|cell.*type|cell.*population', text):
            score += 0.2
        
        if re.search(r'droplet.*based|microfluidic.*based', text):
            score += 0.15
        
        return min(score, 1.0)
    
    def _calculate_bulk_score(self, text: str) -> float:
        """bulk RNA-seq 점수 계산"""
        score = 0.0
        
        # 키워드 매칭
        for keyword in self.bulk_keywords:
            if keyword in text:
                # 가중치 부여
                if "bulk rna-seq" in keyword or "bulk rna sequencing" in keyword:
                    score += 0.3
                elif "transcriptome" in keyword or "gene expression" in keyword:
                    score += 0.2
                elif "polya" in keyword or "ribosomal depletion" in keyword:
                    score += 0.15
                else:
                    score += 0.1
        
        # scRNA-seq 키워드가 없으면 bulk 점수 증가
        if not any(keyword in text for keyword in self.scrna_keywords):
            if "rna-seq" in text or "rna sequencing" in text:
                score += 0.2
        
        return min(score, 1.0)
    
    def _analyze_sra_metadata(self, sra_metadata: Dict) -> Tuple[float, float]:
        """SRA 메타데이터 분석"""
        scrna_score = 0.0
        bulk_score = 0.0
        
        for sra_id, meta in sra_metadata.items():
            # 라이브러리 전략 분석
            library_strategy = meta.get("LibStrategy", "").lower()
            library_source = meta.get("LibSource", "").lower()
            library_selection = meta.get("LibSelection", "").lower()
            
            # scRNA-seq 관련
            if "single cell" in library_strategy or "single-cell" in library_strategy:
                scrna_score += 0.3
            elif "10x" in library_strategy or "cellranger" in library_strategy:
                scrna_score += 0.25
            
            # bulk RNA-seq 관련
            if "rna-seq" in library_strategy or "transcriptome" in library_strategy:
                bulk_score += 0.2
            elif "polya" in library_selection or "mrna" in library_source:
                bulk_score += 0.15
        
        return min(scrna_score, 0.5), min(bulk_score, 0.5)
    
    def _collect_evidence(self, text: str, sra_metadata: Dict) -> List[str]:
        """증거 수집"""
        evidence = []
        
        # 텍스트 기반 증거
        for keyword in self.scrna_keywords:
            if keyword in text:
                evidence.append(f"scRNA-seq 키워드: '{keyword}'")
        
        for keyword in self.bulk_keywords:
            if keyword in text:
                evidence.append(f"bulk RNA-seq 키워드: '{keyword}'")
        
        # SRA 메타데이터 기반 증거
        for sra_id, meta in sra_metadata.items():
            strategy = meta.get("LibStrategy", "")
            if strategy:
                evidence.append(f"SRA {sra_id} 라이브러리 전략: {strategy}")
        
        return evidence[:10]  # 최대 10개 증거
    
    def _get_recommended_pipeline(self, seq_type: str) -> str:
        """추천 파이프라인 반환"""
        pipeline_map = {
            "scRNA-seq": "nf-core/scrnaseq",
            "bulk RNA-seq": "nf-core/rnaseq",
            "unknown": "manual_review_required"
        }
        return pipeline_map.get(seq_type, "unknown")
    
    def save_detection_result(self, result: Dict) -> str:
        """판별 결과 저장"""
        pmid = result.get("pmid", "unknown")
        filename = f"/workspace/results/sequencing_detection_{pmid}.json"
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"시퀀싱 타입 판별 결과 저장: {filename}")
            return filename
            
        except Exception as e:
            print(f"판별 결과 저장 실패: {e}")
            return ""
    
    def load_detection_result(self, pmid: str) -> Optional[Dict]:
        """저장된 판별 결과 로드"""
        filename = f"/workspace/results/sequencing_detection_{pmid}.json"
        
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

def main():
    """테스트 실행"""
    print("=== 시퀀싱 타입 판별기 테스트 ===")
    
    detector = SequencingDetector()
    
    # 테스트 데이터 (scRNA-seq)
    scrna_metadata = {
        "pmid": "40315330",
        "title": "Single-cell RNA sequencing reveals cellular heterogeneity in tumor microenvironment",
        "abstract": "We performed single-cell RNA sequencing using 10x Genomics platform to analyze cellular composition. Our analysis identified distinct cell populations using UMI-based counting.",
        "keywords": ["single-cell", "RNA-seq", "10x Genomics", "tumor"],
        "sra_links": ["SRR123456"]
    }
    
    scrna_sra_metadata = {
        "SRR123456": {
            "LibStrategy": "SINGLE_CELL",
            "LibSource": "TRANSCRIPTOMIC",
            "LibSelection": "cDNA"
        }
    }
    
    # 테스트 데이터 (bulk RNA-seq)
    bulk_metadata = {
        "pmid": "32416070",
        "title": "Bulk RNA-seq analysis of gene expression changes in response to treatment",
        "abstract": "We performed bulk RNA sequencing with polyA selection to analyze gene expression changes. Total RNA was extracted and sequenced using Illumina platform.",
        "keywords": ["RNA-seq", "gene expression", "polyA", "treatment"],
        "sra_links": ["SRR789012"]
    }
    
    bulk_sra_metadata = {
        "SRR789012": {
            "LibStrategy": "RNA-SEQ",
            "LibSource": "TRANSCRIPTOMIC",
            "LibSelection": "POLY_A"
        }
    }
    
    # scRNA-seq 테스트
    print("\n--- scRNA-seq 테스트 ---")
    scrna_result = detector.detect_sequencing_type(scrna_metadata, scrna_sra_metadata)
    detector.save_detection_result(scrna_result)
    print(f"결과: {scrna_result['predicted_type']} (신뢰도: {scrna_result['confidence']})")
    
    # bulk RNA-seq 테스트
    print("\n--- bulk RNA-seq 테스트 ---")
    bulk_result = detector.detect_sequencing_type(bulk_metadata, bulk_sra_metadata)
    detector.save_detection_result(bulk_result)
    print(f"결과: {bulk_result['predicted_type']} (신뢰도: {bulk_result['confidence']})")

if __name__ == "__main__":
    main()