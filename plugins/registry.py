"""
Plugin Registry
시퀀싱 타입 플러그인 등록 및 관리
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

from .base import SequencingTypePlugin, DetectionResult


@dataclass
class RegistryStats:
    total_plugins: int
    plugin_names: List[str]
    detection_count: int


class PluginRegistry:
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._plugins: Dict[str, SequencingTypePlugin] = {}
            cls._instance._detection_count = 0
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> "PluginRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def register(self, plugin: SequencingTypePlugin) -> None:
        self._plugins[plugin.name] = plugin
    
    def unregister(self, name: str) -> bool:
        if name in self._plugins:
            del self._plugins[name]
            return True
        return False
    
    def get(self, name: str) -> Optional[SequencingTypePlugin]:
        return self._plugins.get(name)
    
    def list_plugins(self) -> List[str]:
        return list(self._plugins.keys())
    
    def detect(
        self,
        pubmed_metadata: Dict[str, Any],
        sra_metadata: Dict[str, Any]
    ) -> Tuple[DetectionResult, str]:
        self._detection_count += 1
        
        results: List[Tuple[str, DetectionResult]] = []
        
        for name, plugin in self._plugins.items():
            result = plugin.detect(pubmed_metadata, sra_metadata)
            results.append((name, result))
        
        results.sort(key=lambda x: x[1].score, reverse=True)
        
        if results and results[0][1].score > 0.3:
            best_name, best_result = results[0]
            return best_result, best_name
        
        unknown_result = DetectionResult(
            sequencing_type="unknown",
            confidence=0.0,
            score=0.0,
            evidence=["No sequencing type matched with sufficient confidence"]
        )
        return unknown_result, "unknown"
    
    def detect_all(
        self,
        pubmed_metadata: Dict[str, Any],
        sra_metadata: Dict[str, Any]
    ) -> Dict[str, DetectionResult]:
        results = {}
        for name, plugin in self._plugins.items():
            results[name] = plugin.detect(pubmed_metadata, sra_metadata)
        return results
    
    def get_pipeline_for_type(self, sequencing_type: str):
        plugin = self._plugins.get(sequencing_type)
        if plugin:
            return plugin.pipeline
        return None
    
    def get_stats(self) -> RegistryStats:
        return RegistryStats(
            total_plugins=len(self._plugins),
            plugin_names=list(self._plugins.keys()),
            detection_count=self._detection_count
        )
    
    def clear(self) -> None:
        self._plugins.clear()
        self._detection_count = 0


def register_default_plugins() -> PluginRegistry:
    from .scrna_plugin import ScRnaSeqPlugin
    from .bulk_rna_plugin import BulkRnaSeqPlugin
    from .atac_plugin import AtacSeqPlugin
    from .chipseq_plugin import ChIPSeqPlugin
    
    registry = PluginRegistry.get_instance()
    
    if not registry.list_plugins():
        registry.register(ScRnaSeqPlugin())
        registry.register(BulkRnaSeqPlugin())
        registry.register(AtacSeqPlugin())
        registry.register(ChIPSeqPlugin())
    
    return registry
