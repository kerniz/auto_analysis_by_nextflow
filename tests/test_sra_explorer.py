"""
Tests for core/sra_explorer.py
"""

from unittest.mock import MagicMock, mock_open, patch

from core.sra_explorer import SRAExplorer


class TestSRAExplorerInit:
    @patch("os.makedirs")
    def test_init(self, mock_makedirs):
        explorer = SRAExplorer()
        assert explorer.base_url == "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        assert explorer.raw_data_dir == "./results/raw_data"
        assert explorer.samplesheet_dir == "./results"
        assert mock_makedirs.call_count == 2

    @patch("os.makedirs")
    def test_init_custom_dir(self, mock_makedirs):
        explorer = SRAExplorer(results_dir="/tmp/test")
        assert explorer.raw_data_dir == "/tmp/test/raw_data"
        assert explorer.samplesheet_dir == "/tmp/test"


class TestExploreSraDatasets:
    @patch("os.makedirs")
    def test_empty_sra_links(self, mock_makedirs):
        explorer = SRAExplorer()
        result = explorer.explore_sra_datasets("12345", [])
        assert result["pmid"] == "12345"
        assert result["downloadable"] is False
        assert result["public_sra_ids"] == []

    @patch("os.makedirs")
    def test_success_with_public_ids(self, mock_makedirs):
        explorer = SRAExplorer()
        metadata = {
            "SRA001": {
                "Runs": [{"acc": "SRR001"}],
            }
        }
        with patch.object(explorer, "_fetch_sra_metadata", return_value=metadata), \
             patch.object(explorer, "_filter_public_sra", return_value=(["SRR001"], [])), \
             patch.object(explorer, "_estimate_data_size", return_value=5.0), \
             patch.object(explorer, "_create_samplesheet", return_value="/ws/sheet.csv"):

            result = explorer.explore_sra_datasets("12345", ["SRA001"])
            assert result["downloadable"] is True
            assert result["public_sra_ids"] == ["SRR001"]
            assert result["total_size_gb"] == 5.0
            assert result["samplesheet"] == "/ws/sheet.csv"

    @patch("os.makedirs")
    def test_only_controlled_ids(self, mock_makedirs):
        explorer = SRAExplorer()
        with patch.object(explorer, "_fetch_sra_metadata", return_value={"SRA001": {}}), \
             patch.object(explorer, "_filter_public_sra", return_value=([], ["SRR999"])):

            result = explorer.explore_sra_datasets("12345", ["SRA001"])
            assert result["downloadable"] is False
            assert result["controlled_sra_ids"] == ["SRR999"]

    @patch("os.makedirs")
    def test_exception(self, mock_makedirs):
        explorer = SRAExplorer()
        with patch.object(explorer, "_fetch_sra_metadata", side_effect=Exception("err")):
            result = explorer.explore_sra_datasets("12345", ["SRA001"])
            assert result["downloadable"] is False


class TestFetchSraMetadata:
    @patch("os.makedirs")
    @patch("core.sra_explorer.requests")
    @patch("core.sra_explorer.time")
    def test_success(self, mock_time, mock_requests, mock_makedirs):
        explorer = SRAExplorer()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": {"SRA001": {"LibStrategy": "RNA-SEQ"}}}
        mock_requests.get.return_value = mock_resp

        result = explorer._fetch_sra_metadata(["SRA001"])
        assert "SRA001" in result
        assert result["SRA001"]["LibStrategy"] == "RNA-SEQ"

    @patch("os.makedirs")
    @patch("core.sra_explorer.requests")
    @patch("core.sra_explorer.time")
    def test_non_200(self, mock_time, mock_requests, mock_makedirs):
        explorer = SRAExplorer()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_requests.get.return_value = mock_resp

        result = explorer._fetch_sra_metadata(["SRA001"])
        assert result == {}

    @patch("os.makedirs")
    @patch("core.sra_explorer.requests")
    @patch("core.sra_explorer.time")
    def test_exception(self, mock_time, mock_requests, mock_makedirs):
        explorer = SRAExplorer()
        mock_requests.get.side_effect = Exception("timeout")

        result = explorer._fetch_sra_metadata(["SRA001"])
        assert result == {}

    @patch("os.makedirs")
    @patch("core.sra_explorer.requests")
    @patch("core.sra_explorer.time")
    def test_limits_to_10(self, mock_time, mock_requests, mock_makedirs):
        explorer = SRAExplorer()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": {}}
        mock_requests.get.return_value = mock_resp

        ids = [f"SRA{i:03d}" for i in range(15)]
        explorer._fetch_sra_metadata(ids)
        # Should only make 10 API calls
        assert mock_requests.get.call_count == 10

    @patch("os.makedirs")
    @patch("core.sra_explorer.requests")
    @patch("core.sra_explorer.time")
    def test_missing_result(self, mock_time, mock_requests, mock_makedirs):
        explorer = SRAExplorer()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": {"OTHER_ID": {"data": True}}}
        mock_requests.get.return_value = mock_resp

        result = explorer._fetch_sra_metadata(["SRA001"])
        assert result == {}


class TestFilterPublicSra:
    @patch("os.makedirs")
    def test_public_runs(self, mock_makedirs):
        explorer = SRAExplorer()
        metadata = {
            "SRA001": {"Runs": [{"acc": "SRR001"}, {"acc": "SRR002"}]},
        }
        with patch.object(explorer, "_is_public_run", return_value=True):
            public, controlled = explorer._filter_public_sra(metadata)
            assert len(public) == 2
            assert len(controlled) == 0

    @patch("os.makedirs")
    def test_controlled_runs(self, mock_makedirs):
        explorer = SRAExplorer()
        metadata = {
            "SRA001": {"Runs": [{"acc": "SRR001"}]},
        }
        with patch.object(explorer, "_is_public_run", return_value=False):
            public, controlled = explorer._filter_public_sra(metadata)
            assert len(public) == 0
            assert len(controlled) == 1

    @patch("os.makedirs")
    def test_non_srr_prefix(self, mock_makedirs):
        explorer = SRAExplorer()
        metadata = {
            "SRA001": {"Runs": [{"acc": "ERR001"}]},  # Not SRR prefix
        }
        public, controlled = explorer._filter_public_sra(metadata)
        assert public == []
        assert controlled == []

    @patch("os.makedirs")
    def test_empty_runs(self, mock_makedirs):
        explorer = SRAExplorer()
        metadata = {"SRA001": {"Runs": []}}
        public, controlled = explorer._filter_public_sra(metadata)
        assert public == []
        assert controlled == []

    @patch("os.makedirs")
    def test_no_runs_key(self, mock_makedirs):
        explorer = SRAExplorer()
        metadata = {"SRA001": {}}
        public, controlled = explorer._filter_public_sra(metadata)
        assert public == []
        assert controlled == []

    @patch("os.makedirs")
    def test_deduplication(self, mock_makedirs):
        explorer = SRAExplorer()
        metadata = {
            "SRA001": {"Runs": [{"acc": "SRR001"}]},
            "SRA002": {"Runs": [{"acc": "SRR001"}]},  # duplicate
        }
        with patch.object(explorer, "_is_public_run", return_value=True):
            public, controlled = explorer._filter_public_sra(metadata)
            assert len(public) == 1


class TestIsPublicRun:
    @patch("os.makedirs")
    def test_always_true(self, mock_makedirs):
        explorer = SRAExplorer()
        assert explorer._is_public_run("SRR001") is True


class TestEstimateDataSize:
    @patch("os.makedirs")
    def test_estimate(self, mock_makedirs):
        explorer = SRAExplorer()
        result = explorer._estimate_data_size(["SRR001", "SRR002"])
        assert result == 10.0

    @patch("os.makedirs")
    def test_empty(self, mock_makedirs):
        explorer = SRAExplorer()
        result = explorer._estimate_data_size([])
        assert result == 0.0


class TestCreateSamplesheet:
    @patch("os.makedirs")
    def test_success(self, mock_makedirs):
        explorer = SRAExplorer()
        with patch("core.sra_explorer.pd") as mock_pd:
            mock_df = MagicMock()
            mock_pd.DataFrame.return_value = mock_df

            result = explorer._create_samplesheet("12345", ["SRR001", "SRR002"], {})
            assert "samplesheet_12345.csv" in result
            mock_df.to_csv.assert_called_once()

    @patch("os.makedirs")
    def test_creates_correct_data(self, mock_makedirs):
        explorer = SRAExplorer()
        with patch("core.sra_explorer.pd") as mock_pd:
            mock_df = MagicMock()
            mock_pd.DataFrame.return_value = mock_df

            explorer._create_samplesheet("12345", ["SRR001"], {})
            call_args = mock_pd.DataFrame.call_args[0][0]
            assert len(call_args) == 1
            assert call_args[0]["sample_id"] == "SRR001"
            assert call_args[0]["fastq_1"] == "SRR001_1.fastq.gz"

    @patch("os.makedirs")
    def test_failure(self, mock_makedirs):
        explorer = SRAExplorer()
        with patch("core.sra_explorer.pd") as mock_pd:
            mock_pd.DataFrame.side_effect = Exception("err")
            result = explorer._create_samplesheet("12345", ["SRR001"], {})
            assert result == ""


class TestDownloadSraData:
    @patch("os.makedirs")
    def test_success(self, mock_makedirs):
        explorer = SRAExplorer()
        with patch.object(explorer, "_download_single_sra", return_value=True), \
             patch.object(explorer, "_calculate_downloaded_size", return_value=10.0):
            result = explorer.download_sra_data(["SRR001", "SRR002"])
            assert result["total_requested"] == 2
            assert len(result["successful_downloads"]) == 2
            assert len(result["failed_downloads"]) == 0
            assert result["total_size_gb"] == 10.0

    @patch("os.makedirs")
    def test_failure(self, mock_makedirs):
        explorer = SRAExplorer()
        with patch.object(explorer, "_download_single_sra", return_value=False), \
             patch.object(explorer, "_calculate_downloaded_size", return_value=0.0):
            result = explorer.download_sra_data(["SRR001"])
            assert len(result["failed_downloads"]) == 1

    @patch("os.makedirs")
    def test_exception(self, mock_makedirs):
        explorer = SRAExplorer()
        with patch.object(explorer, "_download_single_sra", side_effect=Exception("err")), \
             patch.object(explorer, "_calculate_downloaded_size", return_value=0.0):
            result = explorer.download_sra_data(["SRR001"])
            assert len(result["failed_downloads"]) == 1


class TestDownloadSingleSra:
    @patch("os.makedirs")
    @patch("core.sra_explorer.subprocess")
    @patch("core.sra_explorer.os.path.exists")
    def test_success(self, mock_exists, mock_subprocess, mock_makedirs):
        explorer = SRAExplorer()
        mock_exists.return_value = True
        prefetch_result = MagicMock(returncode=0)
        fasterq_result = MagicMock(returncode=0)
        gzip_result = MagicMock(returncode=0)
        mock_subprocess.run.side_effect = [prefetch_result, fasterq_result, gzip_result, gzip_result]

        result = explorer._download_single_sra("SRR001")
        assert result is True

    @patch("os.makedirs")
    @patch("core.sra_explorer.subprocess")
    def test_prefetch_failure(self, mock_subprocess, mock_makedirs):
        explorer = SRAExplorer()
        mock_subprocess.run.return_value = MagicMock(returncode=1)

        result = explorer._download_single_sra("SRR001")
        assert result is False

    @patch("os.makedirs")
    @patch("core.sra_explorer.subprocess")
    def test_fasterq_failure(self, mock_subprocess, mock_makedirs):
        explorer = SRAExplorer()
        prefetch_ok = MagicMock(returncode=0)
        fasterq_fail = MagicMock(returncode=1)
        mock_subprocess.run.side_effect = [prefetch_ok, fasterq_fail]

        result = explorer._download_single_sra("SRR001")
        assert result is False

    @patch("os.makedirs")
    @patch("core.sra_explorer.subprocess")
    def test_timeout(self, mock_subprocess, mock_makedirs):
        import subprocess
        explorer = SRAExplorer()
        mock_subprocess.run.side_effect = subprocess.TimeoutExpired(cmd="prefetch", timeout=1800)
        mock_subprocess.TimeoutExpired = subprocess.TimeoutExpired

        result = explorer._download_single_sra("SRR001")
        assert result is False

    @patch("os.makedirs")
    @patch("core.sra_explorer.subprocess")
    def test_exception(self, mock_subprocess, mock_makedirs):
        import subprocess
        explorer = SRAExplorer()
        mock_subprocess.run.side_effect = Exception("err")
        mock_subprocess.TimeoutExpired = subprocess.TimeoutExpired

        result = explorer._download_single_sra("SRR001")
        assert result is False


class TestCalculateDownloadedSize:
    @patch("os.makedirs")
    def test_with_files(self, mock_makedirs):
        explorer = SRAExplorer()
        with patch("core.sra_explorer.os.path.exists", return_value=True), \
             patch("core.sra_explorer.os.path.getsize", return_value=1024**3):
            result = explorer._calculate_downloaded_size(["SRR001"])
            assert result == 2.0  # 2 files, 1 GB each

    @patch("os.makedirs")
    def test_no_files(self, mock_makedirs):
        explorer = SRAExplorer()
        with patch("core.sra_explorer.os.path.exists", return_value=False):
            result = explorer._calculate_downloaded_size(["SRR001"])
            assert result == 0.0

    @patch("os.makedirs")
    def test_empty_list(self, mock_makedirs):
        explorer = SRAExplorer()
        result = explorer._calculate_downloaded_size([])
        assert result == 0.0


class TestSaveSraResults:
    @patch("os.makedirs")
    def test_success(self, mock_makedirs):
        explorer = SRAExplorer()
        results = {"pmid": "12345", "downloadable": True}

        m = mock_open()
        with patch("builtins.open", m):
            filename = explorer.save_sra_results(results, "12345")
            assert "sra_exploration_12345.json" in filename

    @patch("os.makedirs")
    def test_failure(self, mock_makedirs):
        explorer = SRAExplorer()
        with patch("builtins.open", side_effect=Exception("err")):
            result = explorer.save_sra_results({}, "12345")
            assert result == ""
