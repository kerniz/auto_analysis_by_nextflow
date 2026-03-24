#!/usr/bin/env python3
"""
PubMed Client for Metadata Retrieval
PubMed ID로 논문 메타데이터 수집 + NCBI Elink 연관 데이터 탐색
"""

import json
import logging
import ssl
import time
from datetime import datetime
from urllib.error import URLError
from urllib.request import urlopen

from Bio import Entrez

logger = logging.getLogger(__name__)

# macOS SSL 인증서 문제 자동 해결
try:
    _default_ctx = ssl.create_default_context()
except ssl.SSLError:
    _default_ctx = ssl._create_unverified_context()

try:
    import certifi
    _default_ctx.load_verify_locations(certifi.where())
except ImportError:
    # certifi 없으면 시스템 인증서 사용, 실패 시 unverified
    try:
        _default_ctx.load_default_certs()
    except Exception:
        _default_ctx = ssl._create_unverified_context()


def _ssl_urlopen(url, timeout=30):
    """SSL 컨텍스트를 적용한 urlopen wrapper."""
    return urlopen(url, timeout=timeout, context=_default_ctx)


# Bio.Entrez의 내부 urlopen을 SSL-safe로 패치
try:
    _orig_urlopen = Entrez._urlopen if hasattr(Entrez, '_urlopen') else None
except Exception:
    _orig_urlopen = None


def _patch_entrez_ssl():
    """Entrez의 urllib 호출에 SSL 컨텍스트를 주입."""
    import urllib.request
    _orig = urllib.request.urlopen

    def _patched(url, data=None, timeout=30, **kwargs):
        if isinstance(url, str) and url.startswith("https"):
            return _orig(url, data=data, timeout=timeout, context=_default_ctx)
        if hasattr(url, 'full_url') and url.full_url.startswith("https"):
            return _orig(url, data=data, timeout=timeout, context=_default_ctx)
        return _orig(url, data=data, timeout=timeout, **kwargs)

    urllib.request.urlopen = _patched


_patch_entrez_ssl()

# NCBI Elink에서 탐색할 연관 데이터베이스
NCBI_LINK_DATABASES = {
    "pubmed_sra": {"db": "sra", "label": "SRA"},
    "pubmed_gds": {"db": "gds", "label": "GEO"},
    "pubmed_bioproject": {"db": "bioproject", "label": "BioProject"},
    "pubmed_nuccore": {"db": "nuccore", "label": "Nucleotide"},
    "pubmed_protein": {"db": "protein", "label": "Protein"},
    "pubmed_gene": {"db": "gene", "label": "Gene"},
    "pubmed_assembly": {"db": "assembly", "label": "Assembly"},
}

# Evaluability 판단 기준
EVALUABILITY_THRESHOLDS = {
    "minimum_fields": 2,   # 최소 title+abstract
    "full_evaluation": 4,  # title+abstract+methods+data
}


def _retry(func, max_retries=1, delay=0.5):
    """재시도 래퍼 (exponential backoff)."""
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except (URLError, ssl.SSLError, OSError, TimeoutError) as e:
            last_err = e
            logger.warning(
                "NCBI API 호출 실패 (시도 %d/%d): %s",
                attempt, max_retries, e,
            )
            if attempt < max_retries:
                time.sleep(delay * attempt)
        except Exception as e:
            last_err = e
            logger.warning(
                "NCBI API 예외 (시도 %d/%d): %s",
                attempt, max_retries, e,
            )
            if attempt < max_retries:
                time.sleep(delay * attempt)
    raise last_err


class PubMedClient:
    def __init__(self, email="bioauto@pipeline.local"):
        """PubMed 클라이언트 초기화"""
        Entrez.email = email
        Entrez.api_key = None  # 필요 시 설정
        self.base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        self.max_retries = 1

    def fetch_paper_metadata(self, pmid: str) -> dict | None:
        """PMID로 논문 메타데이터 수집 (httpx 우선 + NCBI Elink 포함)"""
        logger.info("PubMed 메타데이터 수집: PMID %s", pmid)

        try:
            # httpx 우선 시도 (SSL 문제 회피), 실패 시 Entrez 폴백
            summary = self._fetch_summary_httpx(pmid)
            if not summary:
                summary = self._fetch_summary(pmid)
            if not summary:
                return None

            # 상세 정보 수집
            abstract = self._fetch_abstract_httpx(pmid)
            if not abstract:
                abstract = self._fetch_abstract(pmid)

            # NCBI Elink로 연관 데이터 탐색 (SRA, GEO, BioProject 등)
            ncbi_links = self._fetch_all_ncbi_links(pmid)
            sra_links = ncbi_links.get("sra", [])
            geo_links = ncbi_links.get("gds", [])

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
                "ncbi_links": ncbi_links,
                "doi": summary.get("DOI", ""),
                "article_ids": summary.get("ArticleIds", {}),
                "retrieved_at": datetime.now().isoformat(),
            }

            # Evaluability 평가
            metadata["evaluability"] = self._assess_evaluability(metadata)

            logger.info(
                "메타데이터 수집 완료: %s (evaluability: %s)",
                metadata['title'][:50],
                metadata['evaluability']['level'],
            )
            return metadata

        except Exception as e:
            logger.error("메타데이터 수집 실패 (PMID %s): %s", pmid, e)
            return None

    def _fetch_summary(self, pmid: str) -> dict | None:
        """논문 요약 정보 수집 (재시도 포함)"""
        def _do():
            handle = Entrez.esummary(db="pubmed", id=pmid, retmode="json")
            record = json.load(handle)
            handle.close()
            return record

        try:
            record = _retry(_do, max_retries=self.max_retries)
            result = record.get("result", {})
            if pmid in result:
                raw = result[pmid]
                return {
                    "Title": raw.get("title", ""),
                    "Authors": [
                        a.get("name", "") for a in raw.get("authors", [])
                    ],
                    "Source": raw.get("source", ""),
                    "PubDate": raw.get("pubdate", ""),
                    "DOI": raw.get("elocationid", ""),
                    "ArticleIds": {
                        aid.get("idtype", ""): aid.get("value", "")
                        for aid in raw.get("articleids", [])
                    },
                }
            return None
        except Exception as e:
            logger.warning("요약 정보 수집 실패 (PMID %s): %s", pmid, e)
            return None

    def _fetch_summary_httpx(self, pmid: str) -> dict | None:
        """Entrez 실패 시 httpx로 직접 API 호출 (SSL 폴백)."""
        try:
            import httpx
        except ImportError:
            return None

        url = (
            f"{self.base_url}/esummary.fcgi"
            f"?db=pubmed&id={pmid}&retmode=json"
        )
        try:
            resp = httpx.get(url, timeout=30, verify=False)
            if resp.status_code == 200:
                data = resp.json()
                result = data.get("result", {})
                if pmid in result:
                    raw = result[pmid]
                    return {
                        "Title": raw.get("title", ""),
                        "Authors": [
                            a.get("name", "")
                            for a in raw.get("authors", [])
                        ],
                        "Source": raw.get("source", ""),
                        "PubDate": raw.get("pubdate", ""),
                        "DOI": raw.get("elocationid", ""),
                        "ArticleIds": {
                            aid.get("idtype", ""): aid.get("value", "")
                            for aid in raw.get("articleids", [])
                        },
                    }
        except Exception as e:
            logger.warning("httpx 폴백 실패 (PMID %s): %s", pmid, e)
        return None

    def _fetch_abstract(self, pmid: str) -> str:
        """초록 정보 수집 (재시도 + httpx 폴백)"""
        def _do():
            handle = Entrez.efetch(db="pubmed", id=pmid, retmode="xml")
            record = Entrez.read(handle)
            handle.close()
            return record

        try:
            record = _retry(_do, max_retries=self.max_retries)
            return self._extract_abstract_from_xml(record)
        except Exception as e:
            logger.warning("초록 Entrez 실패 (PMID %s): %s, httpx 폴백", pmid, e)
            return self._fetch_abstract_httpx(pmid)

    def _extract_abstract_from_xml(self, record) -> str:
        """Entrez XML 응답에서 초록 추출."""
        articles = record.get("PubmedArticle", [])
        if articles:
            article = articles[0]
            abstract_text = (
                article.get("MedlineCitation", {})
                .get("Article", {})
                .get("Abstract", {})
                .get("AbstractText", [])
            )
            if isinstance(abstract_text, list):
                return " ".join(str(text) for text in abstract_text)
            return str(abstract_text)
        return ""

    def _fetch_abstract_httpx(self, pmid: str) -> str:
        """httpx로 efetch 호출하여 초록 추출."""
        try:
            from xml.etree import ElementTree

            import httpx
        except ImportError:
            return ""
        url = (
            f"{self.base_url}/efetch.fcgi"
            f"?db=pubmed&id={pmid}&retmode=xml"
        )
        try:
            resp = httpx.get(url, timeout=30, verify=False)
            if resp.status_code != 200:
                return ""
            root = ElementTree.fromstring(resp.text)
            # PubmedArticle/MedlineCitation/Article/Abstract/AbstractText
            texts = []
            for at in root.iter("AbstractText"):
                if at.text:
                    texts.append(at.text)
                # 혼합 콘텐츠 (하위 태그 포함)
                for child in at:
                    if child.text:
                        texts.append(child.text)
                    if child.tail:
                        texts.append(child.tail)
            return " ".join(texts).strip()
        except Exception as e:
            logger.warning("httpx abstract 폴백 실패 (PMID %s): %s", pmid, e)
            return ""

    def _fetch_all_ncbi_links(self, pmid: str) -> dict[str, list[str]]:
        """NCBI Elink로 모든 연관 데이터베이스 링크 탐색."""
        links: dict[str, list[str]] = {}

        for linkname, info in NCBI_LINK_DATABASES.items():
            db = info["db"]
            ids = self._fetch_elink(pmid, db, linkname)
            if ids:
                links[db] = ids
                logger.info(
                    "PMID %s → %s: %d건", pmid, info["label"], len(ids),
                )

            time.sleep(0.34)  # NCBI rate limit

        return links

    def _fetch_elink(
        self, pmid: str, db: str, linkname: str,
    ) -> list[str]:
        """단일 Elink 호출 (httpx 우선, Entrez 폴백)."""
        # httpx 우선 (SSL 문제 회피)
        ids = self._fetch_elink_httpx(pmid, db, linkname)
        if ids:
            return ids

        # Entrez 폴백
        def _do():
            handle = Entrez.elink(
                dbfrom="pubmed", db=db, id=pmid, linkname=linkname,
            )
            record = Entrez.read(handle)
            handle.close()
            return record

        try:
            record = _retry(_do, max_retries=self.max_retries)
            ids = []
            if record and record[0].get("LinkSetDb"):
                for linkset in record[0]["LinkSetDb"]:
                    for link in linkset.get("Link", []):
                        ids.append(link["Id"])
            return ids
        except Exception as e:
            logger.debug("Elink %s 실패 (PMID %s): %s", linkname, pmid, e)
            return []

    def _fetch_elink_httpx(
        self, pmid: str, db: str, linkname: str,
    ) -> list[str]:
        """httpx로 elink 호출."""
        try:
            from xml.etree import ElementTree

            import httpx
        except ImportError:
            return []
        url = (
            f"{self.base_url}/elink.fcgi"
            f"?dbfrom=pubmed&db={db}&id={pmid}&linkname={linkname}"
        )
        for attempt in range(2):  # 최대 2회 시도
            try:
                resp = httpx.get(url, timeout=30, verify=False)
                if resp.status_code != 200:
                    time.sleep(0.5)
                    continue
                root = ElementTree.fromstring(resp.text)
                ids = []
                for link_id in root.iter("Id"):
                    # Skip the input Id (same as pmid)
                    if link_id.text and link_id.text != pmid:
                        ids.append(link_id.text)
                if ids or attempt == 1:
                    return ids
                time.sleep(0.5)  # 빈 결과면 1회 재시도
            except Exception as e:
                logger.debug("httpx elink 폴백 실패 (%s, PMID %s, attempt %d): %s", linkname, pmid, attempt, e)
                time.sleep(0.5)
        return []

    # 하위 호환용 (기존 코드에서 직접 호출하는 경우)
    def _find_sra_links(self, pmid: str) -> list[str]:
        """SRA 관련 링크 탐색"""
        return self._fetch_elink(pmid, "sra", "pubmed_sra")

    def _find_geo_links(self, pmid: str) -> list[str]:
        """GEO 관련 링크 탐색"""
        return self._fetch_elink(pmid, "gds", "pubmed_gds")

    def _extract_keywords(self, summary: dict, abstract: str) -> list[str]:
        """키워드 추출"""
        keywords = []

        if "KeywordList" in summary:
            for keyword_list in summary["KeywordList"]:
                keywords.extend(keyword_list)

        abstract_lower = abstract.lower()
        sequencing_keywords = [
            "rna-seq", "single-cell", "scrna-seq", "bulk rna-seq",
            "transcriptome", "gene expression", "sequencing",
            "next-generation sequencing", "ngs", "high-throughput",
            "metagenomics", "metagenomic", "whole-genome",
            "chip-seq", "atac-seq", "bisulfite", "nanopore",
            "illumina", "oxford nanopore", "pacbio",
        ]

        for keyword in sequencing_keywords:
            if keyword in abstract_lower:
                keywords.append(keyword)

        return list(set(keywords))

    @staticmethod
    def _assess_evaluability(metadata: dict) -> dict:
        """입력 데이터 충분성 평가 (Evaluability Gate).

        Missing-as-Negative 방지: 데이터가 부족하면 "평가 불가"로 분류.
        """
        fields = {
            "title": bool(metadata.get("title", "").strip()),
            "abstract": bool(metadata.get("abstract", "").strip()),
            "authors": bool(metadata.get("authors")),
            "journal": bool(metadata.get("journal", "").strip()),
            "keywords": bool(metadata.get("keywords")),
            "sra_data": bool(metadata.get("sra_links")),
            "geo_data": bool(metadata.get("geo_links")),
            "ncbi_linked_dbs": sum(
                1 for v in metadata.get("ncbi_links", {}).values() if v
            ),
        }

        available_count = sum(1 for v in fields.values() if v)
        has_text = fields["title"] and fields["abstract"]
        has_data = fields["sra_data"] or fields["geo_data"]
        linked_db_count = fields["ncbi_linked_dbs"]

        # 평가 수준 결정
        if has_text and has_data and linked_db_count >= 2:
            level = "FULL"
            confidence = 1.0
        elif has_text and (has_data or linked_db_count >= 1):
            level = "SUFFICIENT"
            confidence = 0.8
        elif has_text:
            level = "TEXT_ONLY"
            confidence = 0.5
        elif fields["title"]:
            level = "MINIMAL"
            confidence = 0.2
        else:
            level = "INSUFFICIENT"
            confidence = 0.0

        return {
            "level": level,
            "confidence": confidence,
            "fields": fields,
            "available_count": available_count,
            "recommendation": (
                "EVALUATE" if level in ("FULL", "SUFFICIENT")
                else "EVALUATE_WITH_CAVEAT" if level in ("TEXT_ONLY", "MINIMAL")
                else "NO_DATA"  # INSUFFICIENT만 스킵
            ),
        }

    def search_by_topic(self, query: str, max_results: int = 20) -> list[dict]:
        """키워드로 PubMed 논문 검색"""
        logger.info("PubMed 주제 검색: '%s' (최대 %d건)", query, max_results)
        try:
            def _do():
                handle = Entrez.esearch(
                    db="pubmed", term=query, retmax=max_results,
                    sort="relevance", retmode="xml",
                )
                record = Entrez.read(handle)
                handle.close()
                return record

            record = _retry(_do, max_retries=self.max_retries)
            pmid_list = record.get("IdList", [])
            if not pmid_list:
                return []

            results = []
            for pmid in pmid_list:
                meta = self.fetch_paper_metadata(pmid)
                if meta:
                    results.append(meta)
                time.sleep(0.34)

            return results

        except Exception as e:
            logger.error("PubMed 주제 검색 실패: %s", e)
            return []

    def save_metadata(self, metadata: dict, filename: str = None) -> str:
        """메타데이터 저장"""
        if not filename:
            pmid = metadata["pmid"]
            filename = f"./results/pubmed_{pmid}.json"

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            return filename
        except Exception as e:
            logger.error("메타데이터 저장 실패: %s", e)
            return ""

    def load_metadata(self, pmid: str) -> dict | None:
        """저장된 메타데이터 로드"""
        filename = f"./results/pubmed_{pmid}.json"
        try:
            with open(filename, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None


def main():
    """테스트 실행"""
    logging.basicConfig(level=logging.INFO)
    print("=== PubMed 클라이언트 테스트 ===")

    client = PubMedClient()
    test_pmids = ["32015508", "40315330"]

    for pmid in test_pmids:
        print(f"\n--- PMID {pmid} 처리 ---")
        metadata = client.fetch_paper_metadata(pmid)

        if metadata:
            client.save_metadata(metadata)
            print(f"제목: {metadata['title']}")
            print(f"저널: {metadata['journal']}")
            print(f"초록 길이: {len(metadata['abstract'])}")
            print(f"SRA 링크: {len(metadata['sra_links'])}")
            print(f"GEO 링크: {len(metadata['geo_links'])}")
            ncbi = metadata.get('ncbi_links', {})
            for db, ids in ncbi.items():
                if ids:
                    print(f"NCBI {db}: {len(ids)}건")
            ev = metadata['evaluability']
            print(f"평가 가능성: {ev['level']} (confidence: {ev['confidence']})")
            print(f"권장: {ev['recommendation']}")
        else:
            print(f"PMID {pmid} 메타데이터 수집 실패")


if __name__ == "__main__":
    main()
