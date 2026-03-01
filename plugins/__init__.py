"""
Sequencing Type Plugins
시퀀싱 타입 감지 플러그인 시스템
"""

from .atac_plugin import AtacSeqPlugin
from .base import DetectionResult, PipelineDefinition, SequencingTypePlugin
from .bulk_rna_plugin import BulkRnaSeqPlugin
from .chipseq_plugin import ChIPSeqPlugin
from .registry import PluginRegistry, register_default_plugins
from .scrna_plugin import ScRnaSeqPlugin

__all__ = [
    "SequencingTypePlugin",
    "DetectionResult",
    "PipelineDefinition",
    "PluginRegistry",
    "register_default_plugins",
    "ScRnaSeqPlugin",
    "BulkRnaSeqPlugin",
    "AtacSeqPlugin",
    "ChIPSeqPlugin",
]
