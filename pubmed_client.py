#!/usr/bin/env python3
"""
PubMed Client for Metadata Retrieval
PubMed ID로 논문 메타데이터 수집
"""

import requests
import json
import sys
import time
from typing import Dict, Optional, List
from datetime import datetime
from Bio import Entrez
from Bio.Entrez import efetch, esummary, elink

class PubMedClient:
    def __init__(self, email="your.email@example.com"):
        """PubMed 클라이언트 초기화"""
        Entrez.email = email
        Entrez.api_key = None  # 필요 시 설정
        self.base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        
    def fetch_paper_metadata(self, pmid: str) -> Optional[Dict]:
        """PMID로 논문 메타데이터 수집"""
        print(f"PubMed 메타데이터 수집: PMID {pmid}")
        
        try:
            # 기본 정보 수집
            summary = self._fetch_summary(pmid)
            if not summary:
                return None
            
            # 상세 정보 수집
            abstract = self._fetch_abstract(pmid)
            
            # SRA/GEO 관련 링크 탐색
            sra_links = self._find_sra_links(pmid)
            geo_links = self._find_geo_links(pmid)
            
            # 메타데이터 구성
            metadata = {
                "pmid": pmid,
                "title": summary.get("Title", ""),
                "authors": summary.get("Authors", []),
                "journal": summary.get("Source", ""),
                "pub_date": summary.get("PubDate", ""),
                "abstract": abstract,
                "keywords": self._extract_keywords(summary, abstract),
                "sra_links": sra_links,
                "geo_links": geo_links,
                "doi": summary.get("DOI", ""),
                "article_ids": summary.get("ArticleIds", {}),
                "retrieved_at": datetime.now().isoformat()
            }
            
            print(f"✅ 메타데이터 수집 완료: {metadata['title'][:50]}...")
            return metadata
            
        except Exception as e:
            print(f"❌ 메타데이터 수집 실패: {e}")
            return None
    
    def _fetch_summary(self, pmid: str) -> Optional[Dict]:
        """논문 요약 정보 수집"""
        try:
            handle = Entrez.esummary(db="pubmed", id=pmid, retmode="json")
            record = Entrez.read(handle)
            handle.close()
            
            if pmid in record:
                return record[pmid]
            else:
                return None
                
        except Exception as e:
            print(f"요약 정보 수집 실패: {e}")
            return None
    
    def _fetch_abstract(self, pmid: str) -> str:
        """초록 정보 수집"""
        try:
            handle = Entrez.efetch(db="pubmed", id=pmid, retmode="xml")
            record = Entrez.read(handle)
            handle.close()
            
            # XML에서 초록 추출
            articles = record.get("PubmedArticle", [])
            if articles:
                article = articles[0]
                abstract_text = article.get("MedlineCitation", {}).get("Article", {}).get("Abstract", {}).get("AbstractText", [])
                
                if isinstance(abstract_text, list):
                    return " ".join(str(text) for text in abstract_text)
                else:
                    return str(abstract_text)
            
            return ""
            
        except Exception as e:
            print(f"초록 수집 실패: {e}")
            return ""
    
    def _find_sra_links(self, pmid: str) -> List[str]:
        """SRA 관련 링크 탐색"""
        try:
            # PubMed에서 SRA 데이터베이스로 링크 탐색
            handle = Entrez.elink(dbfrom="pubmed", db="sra", id=pmid, linkname="pubmed_sra")
            record = Entrez.read(handle)
            handle.close()
            
            sra_ids = []
            if record and "LinkSetDb" in record[0]:
                for linkset in record[0]["LinkSetDb"]:
                    for link in linkset["Link"]:
                        sra_ids.append(link["Id"])
            
            return sra_ids
            
        except Exception as e:
            print(f"SRA 링크 탐색 실패: {e}")
            return []
    
    def _find_geo_links(self, pmid: str) -> List[str]:
        """GEO 관련 링크 탐색"""
        try:
            # PubMed에서 GEO 데이터베이스로 링크 탐색
            handle = Entrez.elink(dbfrom="pubmed", db="gds", id=pmid, linkname="pubmed_gds")
            record = Entrez.read(handle)
            handle.close()
            
            geo_ids = []
            if record and "LinkSetDb" in record[0]:
                for linkset in record[0]["LinkSetDb"]:
                    for link in linkset["Link"]:
                        geo_ids.append(link["Id"])
            
            return geo_ids
            
        except Exception as e:
            print(f"GEO 링크 탐색 실패: {e}")
            return []
    
    def _extract_keywords(self, summary: Dict, abstract: str) -> List[str]:
        """키워드 추출"""
        keywords = []
        
        # 저널 키워드
        if "KeywordList" in summary:
            for keyword_list in summary["KeywordList"]:
                keywords.extend(keyword_list)
        
        # 초록에서 시퀀싱 관련 키워드 추출
        abstract_lower = abstract.lower()
        sequencing_keywords = [
            "rna-seq", "single-cell", "scrna-seq", "bulk rna-seq",
            "transcriptome", "gene expression", "sequencing",
            "next-generation sequencing", "ngs", "high-throughput"
        ]
        
        for keyword in sequencing_keywords:
            if keyword in abstract_lower:
                keywords.append(keyword)
        
        return list(set(keywords))  # 중복 제거
    
    def search_by_topic(self, query: str, max_results: int = 20) -> List[Dict]:
        """
        키워드로 PubMed 논문 검색
        Search PubMed by keyword using Entrez.esearch.

        Args:
            query: 검색 쿼리 (예: "spatial transcriptomics cancer")
            max_results: 최대 결과 수

        Returns:
            논문 메타데이터 목록
        """
        print(f"PubMed 주제 검색: '{query}' (최대 {max_results}건)")
        try:
            handle = Entrez.esearch(
                db="pubmed", term=query, retmax=max_results,
                sort="relevance", retmode="xml",
            )
            record = Entrez.read(handle)
            handle.close()

            pmid_list = record.get("IdList", [])
            if not pmid_list:
                print("검색 결과 없음")
                return []

            print(f"  {len(pmid_list)}건 발견, 메타데이터 수집 중...")
            results = []
            for pmid in pmid_list:
                meta = self.fetch_paper_metadata(pmid)
                if meta:
                    results.append(meta)
                time.sleep(0.34)  # NCBI rate limit (3 req/s)

            print(f"  {len(results)}건 메타데이터 수집 완료")
            return results

        except Exception as e:
            print(f"PubMed 주제 검색 실패: {e}")
            return []

    def save_metadata(self, metadata: Dict, filename: str = None) -> str:
        """메타데이터 저장"""
        if not filename:
            pmid = metadata["pmid"]
            filename = f"/workspace/results/pubmed_{pmid}.json"
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            print(f"메타데이터 저장: {filename}")
            return filename
            
        except Exception as e:
            print(f"메타데이터 저장 실패: {e}")
            return ""
    
    def load_metadata(self, pmid: str) -> Optional[Dict]:
        """저장된 메타데이터 로드"""
        filename = f"/workspace/results/pubmed_{pmid}.json"
        
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

def main():
    """테스트 실행"""
    print("=== PubMed 클라이언트 테스트 ===")
    
    client = PubMedClient()
    
    # 테스트 PMID
    test_pmids = ["40315330", "32416070"]
    
    for pmid in test_pmids:
        print(f"\n--- PMID {pmid} 처리 ---")
        
        # 메타데이터 수집
        metadata = client.fetch_paper_metadata(pmid)
        
        if metadata:
            # 저장
            client.save_metadata(metadata)
            
            # 요약 출력
            print(f"제목: {metadata['title']}")
            print(f"저널: {metadata['journal']}")
            print(f"초록 길이: {len(metadata['abstract'])}")
            print(f"SRA 링크: {len(metadata['sra_links'])}")
            print(f"GEO 링크: {len(metadata['geo_links'])}")
            print(f"키워드: {metadata['keywords']}")
        else:
            print(f"PMID {pmid} 메타데이터 수집 실패")

if __name__ == "__main__":
    main()