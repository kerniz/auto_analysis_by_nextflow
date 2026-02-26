"""
Analysis Orchestrator
nf-core 파이프라인 출력 → 다운스트림 R/Python 분석 라우팅
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from pathlib import Path

from .script_runner import RScriptRunner, PythonScriptRunner

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Result from downstream analysis."""

    analysis_type: str
    success: bool
    output_dir: Optional[Path] = None
    summary: Dict[str, Any] = field(default_factory=dict)
    key_files: Dict[str, str] = field(default_factory=dict)
    execution_time_seconds: float = 0.0
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "analysis_type": self.analysis_type,
            "success": self.success,
            "output_dir": str(self.output_dir) if self.output_dir else None,
            "summary": self.summary,
            "key_files": self.key_files,
            "execution_time_seconds": self.execution_time_seconds,
            "error": self.error,
        }


# Analysis type -> (script filename, runner_type, required_R_packages)
ANALYSIS_ROUTES = {
    "deseq2": {
        "script": "r_scripts/deseq2_analysis.R",
        "runner": "r",
        "r_packages": ["DESeq2", "tximport", "ggplot2", "optparse", "jsonlite"],
    },
    "seurat": {
        "script": "r_scripts/seurat_analysis.R",
        "runner": "r",
        "r_packages": ["Seurat", "ggplot2", "dplyr", "optparse", "jsonlite"],
    },
    "scanpy": {
        "script": "python_scripts/scanpy_analysis.py",
        "runner": "python",
        "python_packages": ["scanpy", "anndata", "matplotlib"],
    },
    "peak_diff": {
        "script": "r_scripts/peak_analysis.R",
        "runner": "r",
        "r_packages": ["DESeq2", "ggplot2", "optparse", "jsonlite"],
    },
}

# Maps nf-core output categories -> R/Python script arguments
OUTPUT_TO_ARGS_MAP = {
    "deseq2": {
        "counts_matrix": "counts_matrix",
        "tx2gene": "tx2gene",
    },
    "seurat": {
        "cellranger_filtered": "input_dir",
        "star_filtered": "input_dir",
        "rds_files": "input_rds",
    },
    "scanpy": {
        "h5ad_files": "input_h5ad",
        "cellranger_filtered": "input_dir",
    },
    "peak_diff": {
        "consensus_counts": "counts_matrix",
        "consensus_peaks": "peaks_bed",
    },
}


class AnalysisOrchestrator:
    """Routes nf-core pipeline outputs to appropriate downstream analysis."""

    def __init__(
        self,
        r_executable: str = "Rscript",
        scripts_dir: Optional[Path] = None,
        scanpy_enabled: bool = False,
        analysis_params: Optional[Dict[str, Dict[str, str]]] = None,
    ):
        self.r_runner = RScriptRunner(r_executable)
        self.py_runner = PythonScriptRunner()
        self.scanpy_enabled = scanpy_enabled
        self.analysis_params = analysis_params or {}

        # Default to scripts bundled with this package
        if scripts_dir is None:
            self.scripts_dir = Path(__file__).parent
        else:
            self.scripts_dir = scripts_dir

    async def check_prerequisites(
        self, analysis_type: str
    ) -> Dict[str, bool]:
        """Check if required tools/packages are installed for a given analysis type."""
        route = ANALYSIS_ROUTES.get(analysis_type)
        if not route:
            return {"supported": False}

        results = {"supported": True}

        if route["runner"] == "r":
            results["r_installed"] = await self.r_runner.check_installation()
            if results["r_installed"]:
                pkg_results = await self.r_runner.check_packages(
                    route.get("r_packages", [])
                )
                results["r_packages"] = pkg_results
                results["all_packages_ok"] = all(pkg_results.values())
            else:
                results["all_packages_ok"] = False
        else:
            results["python_installed"] = True
            pkg_results = await self.py_runner.check_packages(
                route.get("python_packages", [])
            )
            results["python_packages"] = pkg_results
            results["all_packages_ok"] = all(pkg_results.values())

        return results

    async def run_analysis(
        self,
        analysis_type: str,
        pipeline_outputs: Dict[str, List[str]],
        output_dir: Path,
        params: Optional[Dict[str, str]] = None,
    ) -> AnalysisResult:
        """
        Run downstream analysis based on type.

        Args:
            analysis_type: Type of analysis (deseq2, seurat, scanpy, peak_diff)
            pipeline_outputs: Dict from OutputParser.find_outputs()
            output_dir: Where to write analysis results
            params: Additional parameters for the analysis script

        Returns:
            AnalysisResult with summary and key file paths
        """
        # If seurat requested but R not available, try scanpy
        if analysis_type == "seurat" and self.scanpy_enabled:
            r_ok = await self.r_runner.check_installation()
            if not r_ok:
                logger.info("R not available, falling back to scanpy")
                analysis_type = "scanpy"

        route = ANALYSIS_ROUTES.get(analysis_type)
        if not route:
            return AnalysisResult(
                analysis_type=analysis_type,
                success=False,
                error=f"Unknown analysis type: {analysis_type}",
            )

        output_dir.mkdir(parents=True, exist_ok=True)
        script_path = self.scripts_dir / route["script"]

        if not script_path.exists():
            return AnalysisResult(
                analysis_type=analysis_type,
                success=False,
                error=f"Analysis script not found: {script_path}",
            )

        # Map pipeline outputs to script arguments
        script_args = self._map_outputs_to_args(
            analysis_type, pipeline_outputs
        )
        script_args["output_dir"] = str(output_dir)

        # Add user-specified params
        if params:
            script_args.update(params)

        # Add analysis-specific params from config
        config_params = self.analysis_params.get(analysis_type, {})
        for key, val in config_params.items():
            if key not in script_args:
                script_args[key] = str(val)

        start_time = time.time()

        # Run the script
        if route["runner"] == "r":
            success, stdout, stderr = await self.r_runner.run(
                script_path, script_args
            )
        else:
            success, stdout, stderr = await self.py_runner.run(
                script_path, script_args
            )

        elapsed = time.time() - start_time

        # Parse summary.json if script produced one
        summary = {}
        key_files = {}
        summary_file = output_dir / "summary.json"
        if summary_file.exists():
            try:
                summary = json.loads(summary_file.read_text())
            except json.JSONDecodeError:
                pass

        # Find key output files
        key_files = self._find_key_files(analysis_type, output_dir)

        return AnalysisResult(
            analysis_type=analysis_type,
            success=success,
            output_dir=output_dir,
            summary=summary,
            key_files=key_files,
            execution_time_seconds=elapsed,
            error=stderr[:500] if not success else "",
        )

    def _map_outputs_to_args(
        self,
        analysis_type: str,
        pipeline_outputs: Dict[str, List[str]],
    ) -> Dict[str, str]:
        """Map nf-core output file categories to script arguments."""
        mapping = OUTPUT_TO_ARGS_MAP.get(analysis_type, {})
        args = {}

        for output_key, arg_name in mapping.items():
            files = pipeline_outputs.get(output_key, [])
            if files:
                # Use the first matching file/directory
                args[arg_name] = files[0]

        return args

    def _find_key_files(
        self, analysis_type: str, output_dir: Path
    ) -> Dict[str, str]:
        """Find key output files produced by the analysis script."""
        key_patterns = {
            "deseq2": {
                "results": "deseq2_results.csv",
                "significant_degs": "significant_degs.csv",
                "volcano_plot": "volcano_plot.pdf",
                "pca_plot": "pca_plot.pdf",
                "heatmap": "heatmap_top50.pdf",
                "summary": "summary.json",
            },
            "seurat": {
                "seurat_object": "seurat_object.rds",
                "cluster_markers": "cluster_markers.csv",
                "top_markers": "top_markers.csv",
                "umap_plot": "umap_clusters.pdf",
                "violin_qc": "violin_qc.pdf",
                "summary": "summary.json",
            },
            "scanpy": {
                "markers": "markers.csv",
                "umap_plot": "umap.pdf",
                "summary": "summary.json",
            },
            "peak_diff": {
                "diff_peaks": "diff_peaks.csv",
                "peak_annotation": "peak_annotation.csv",
                "summary": "summary.json",
            },
        }

        found = {}
        patterns = key_patterns.get(analysis_type, {})

        for name, filename in patterns.items():
            path = output_dir / filename
            if path.exists():
                found[name] = str(path)

        return found
