"""
Sequencing Type Plugins
시퀀싱 타입 감지 플러그인 시스템
"""

from .base import SequencingTypePlugin, DetectionResult, PipelineDefinition
from .registry import PluginRegistry, register_default_plugins
from .scrna_plugin import ScRnaSeqPlugin
from .bulk_rna_plugin import BulkRnaSeqPlugin
from .atac_plugin import AtacSeqPlugin
from .chipseq_plugin import ChIPSeqPlugin

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
