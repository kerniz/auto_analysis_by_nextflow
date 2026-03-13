"""
Plugin Registry
시퀀싱 타입 플러그인 등록 및 관리
"""

from dataclasses import dataclass
from typing import Any

from .base import DetectionResult, SequencingTypePlugin


@dataclass
class RegistryStats:
    total_plugins: int
    plugin_names: list[str]
    detection_count: int


class PluginRegistry:

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._plugins: dict[str, SequencingTypePlugin] = {}
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

    def get(self, name: str) -> SequencingTypePlugin | None:
        return self._plugins.get(name)

    def list_plugins(self) -> list[str]:
        return list(self._plugins.keys())

    def detect(
        self,
        pubmed_metadata: dict[str, Any],
        sra_metadata: dict[str, Any]
    ) -> tuple[DetectionResult, str]:
        self._detection_count += 1

        results: list[tuple[str, DetectionResult]] = []

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
        pubmed_metadata: dict[str, Any],
        sra_metadata: dict[str, Any]
    ) -> dict[str, DetectionResult]:
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
    from .atac_plugin import AtacSeqPlugin
    from .bulk_rna_plugin import BulkRnaSeqPlugin
    from .chipseq_plugin import ChIPSeqPlugin
    from .cutandrun_plugin import CutAndRunPlugin
    from .methylseq_plugin import MethylSeqPlugin
    from .rnafusion_plugin import RnaFusionPlugin
    from .sarek_plugin import SarekPlugin
    from .scrna_plugin import ScRnaSeqPlugin

    registry = PluginRegistry.get_instance()

    if not registry.list_plugins():
        registry.register(ScRnaSeqPlugin())
        registry.register(BulkRnaSeqPlugin())
        registry.register(AtacSeqPlugin())
        registry.register(ChIPSeqPlugin())
        registry.register(SarekPlugin())
        registry.register(MethylSeqPlugin())
        registry.register(CutAndRunPlugin())
        registry.register(RnaFusionPlugin())

    return registry
