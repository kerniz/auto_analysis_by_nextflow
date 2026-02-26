"""
Data Source Clients Module
데이터 소스 클라이언트 모듈

외부 API(Semantic Scholar, Europe PMC, 어노테이션 서비스, TCGA/GDC)에
접근하기 위한 비동기 클라이언트 패키지입니다.
Async client package for accessing external APIs including Semantic Scholar,
Europe PMC, annotation services (QuickGO, KEGG, Ensembl), and TCGA/GDC.
"""

from .base import BaseClient, ClientConfig, ClientResponse
from .semantic_scholar_client import SemanticScholarClient
from .europe_pmc_client import EuropePMCClient
from .annotation_client import AnnotationClient
from .tcga_client import TCGAClient
from .data_aggregator import DataAggregator, AggregatedResult

__all__ = [
    "BaseClient",
    "ClientConfig",
    "ClientResponse",
    "SemanticScholarClient",
    "EuropePMCClient",
    "AnnotationClient",
    "TCGAClient",
    "DataAggregator",
    "AggregatedResult",
]
