"""Tests for paper selection modes (_select_papers, _filter_by_condition, _parse_selection_indices)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.cli import _filter_by_condition, _parse_selection_indices, _select_papers


def _make_result(pmid="12345", title="Test Paper", abstract="Abstract",
                 year=2024, citation_count=10):
    """테스트용 SearchResult 목업 생성."""
    r = MagicMock()
    r.pmid = pmid
    r.title = title
    r.abstract = abstract
    r.year = year
    r.citation_count = citation_count
    return r


class TestParseSelectionIndices:
    """_parse_selection_indices 파싱 테스트."""

    def test_single_number(self):
        assert _parse_selection_indices("3", 10) == [2]

    def test_multiple_numbers(self):
        assert _parse_selection_indices("1,3,5", 10) == [0, 2, 4]

    def test_range(self):
        assert _parse_selection_indices("1-5", 10) == [0, 1, 2, 3, 4]

    def test_mixed_range_and_numbers(self):
        result = _parse_selection_indices("1-3,7,9", 10)
        assert result == [0, 1, 2, 6, 8]

    def test_space_separated(self):
        assert _parse_selection_indices("1 3 5", 10) == [0, 2, 4]

    def test_invalid_text(self):
        assert _parse_selection_indices("abc", 10) is None

    def test_empty(self):
        assert _parse_selection_indices("", 10) is None

    def test_large_range(self):
        result = _parse_selection_indices("1-48", 50)
        assert len(result) == 48
        assert result[0] == 0
        assert result[-1] == 47


class TestFilterByCondition:
    """_filter_by_condition 조건 필터 테스트."""

    def setup_method(self):
        self.results = [
            _make_result(pmid="1", year=2020, citation_count=5, title="Old cancer paper"),
            _make_result(pmid="2", year=2022, citation_count=50, title="Immunotherapy study"),
            _make_result(pmid="3", year=2024, citation_count=120, title="Recent RNA-seq analysis"),
            _make_result(pmid="4", year=2024, citation_count=200, title="Cancer genomics paper"),
            _make_result(pmid=None, year=2023, citation_count=30, title="No PMID paper"),
        ]

    def test_year_greater(self):
        filtered = _filter_by_condition(self.results, ">2023")
        assert len(filtered) == 2
        assert all(r.year > 2023 for r in filtered)

    def test_year_greater_equal(self):
        filtered = _filter_by_condition(self.results, ">=2024")
        assert len(filtered) == 2

    def test_year_less(self):
        filtered = _filter_by_condition(self.results, "<2022")
        assert len(filtered) == 1
        assert filtered[0].pmid == "1"

    def test_year_equal(self):
        filtered = _filter_by_condition(self.results, "=2022")
        assert len(filtered) == 1
        assert filtered[0].pmid == "2"

    def test_cited_greater(self):
        filtered = _filter_by_condition(self.results, "cited>50")
        assert len(filtered) == 2
        assert all(r.citation_count > 50 for r in filtered)

    def test_cited_greater_equal(self):
        filtered = _filter_by_condition(self.results, "cite>=50")
        assert len(filtered) == 3

    def test_cited_less(self):
        filtered = _filter_by_condition(self.results, "cited<30")
        assert len(filtered) == 1

    def test_keyword_title(self):
        filtered = _filter_by_condition(self.results, '"cancer"')
        assert len(filtered) == 2

    def test_keyword_abstract(self):
        # abstract is "Abstract" for all
        filtered = _filter_by_condition(self.results, '"abstract"')
        assert len(filtered) == 5

    def test_keyword_single_quotes(self):
        filtered = _filter_by_condition(self.results, "'RNA-seq'")
        assert len(filtered) == 1
        assert filtered[0].pmid == "3"

    def test_not_a_condition(self):
        """일반 텍스트는 None 반환."""
        assert _filter_by_condition(self.results, "abc") is None
        assert _filter_by_condition(self.results, "1,3,5") is None

    def test_no_match(self):
        filtered = _filter_by_condition(self.results, ">2030")
        assert filtered == []

    def test_case_insensitive_cited(self):
        filtered = _filter_by_condition(self.results, "CITED>100")
        assert len(filtered) == 2


class TestSelectPapersIntegration:
    """_select_papers 통합 테스트 (입력 시뮬레이션)."""

    def setup_method(self):
        self.results = [
            _make_result(pmid="111", year=2020, citation_count=5, title="Paper A"),
            _make_result(pmid="222", year=2022, citation_count=50, title="Paper B"),
            _make_result(pmid="333", year=2024, citation_count=120, title="Paper C"),
        ]

    @patch("core.cli._read_input", return_value="1,3")
    def test_number_selection(self, mock_input):
        pmids = _select_papers(self.results)
        assert pmids == ["111", "333"]

    @patch("core.cli._read_input", return_value="1-3")
    def test_range_selection(self, mock_input):
        pmids = _select_papers(self.results)
        assert pmids == ["111", "222", "333"]

    @patch("core.cli._read_input", return_value="a")
    def test_all_selection(self, mock_input):
        pmids = _select_papers(self.results)
        assert pmids == ["111", "222", "333"]

    @patch("core.cli._read_input", return_value="all")
    def test_all_word_selection(self, mock_input):
        pmids = _select_papers(self.results)
        assert pmids == ["111", "222", "333"]

    @patch("core.cli._read_input", return_value=">2023")
    def test_year_condition(self, mock_input):
        pmids = _select_papers(self.results)
        assert pmids == ["333"]

    @patch("core.cli._read_input", return_value="cited>50")
    def test_cited_condition(self, mock_input):
        pmids = _select_papers(self.results)
        assert pmids == ["333"]

    @patch("core.cli._read_input", return_value='"Paper B"')
    def test_keyword_condition(self, mock_input):
        pmids = _select_papers(self.results)
        assert pmids == ["222"]

    @patch("core.cli._read_input", return_value="q")
    def test_quit(self, mock_input):
        pmids = _select_papers(self.results)
        assert pmids == []

    @patch("core.cli._read_input", side_effect=["abc", "1"])
    def test_retry_then_valid(self, mock_input):
        pmids = _select_papers(self.results)
        assert pmids == ["111"]

    @patch("core.cli._read_input", side_effect=["", "2"])
    def test_empty_then_valid(self, mock_input):
        pmids = _select_papers(self.results)
        assert pmids == ["222"]


class TestSelectPapersNoPmid:
    """PMID 없는 결과 처리."""

    @patch("core.cli._read_input", return_value="a")
    def test_all_with_no_pmid(self, mock_input):
        results = [
            _make_result(pmid=None, title="No PMID"),
        ]
        pmids = _select_papers(results)
        assert pmids == []

    @patch("core.cli._read_input", side_effect=["1", "q"])
    def test_select_no_pmid_then_quit(self, mock_input):
        results = [
            _make_result(pmid=None, title="No PMID"),
        ]
        pmids = _select_papers(results)
        assert pmids == []


class TestPrintResultsTable:
    """print_results_table 페이지네이션 테스트."""

    def test_small_list_no_pagination(self, capsys):
        from core.terminal_fx import print_results_table
        results = [_make_result(pmid=str(i)) for i in range(5)]
        print_results_table(results, page_size=20)
        captured = capsys.readouterr()
        assert "총 5건" in captured.out

    @patch("builtins.input", return_value="q")
    def test_large_list_quit(self, mock_input, capsys):
        from core.terminal_fx import print_results_table
        results = [_make_result(pmid=str(i), title=f"Paper {i}") for i in range(48)]
        print_results_table(results, page_size=20)
        captured = capsys.readouterr()
        # 첫 20건 + "총 48건" 표시
        assert "20/48" in captured.out
        assert "총 48건" in captured.out

    @patch("builtins.input", return_value="a")
    def test_large_list_show_all(self, mock_input, capsys):
        from core.terminal_fx import print_results_table
        results = [_make_result(pmid=str(i), title=f"Paper {i}") for i in range(30)]
        print_results_table(results, page_size=20)
        captured = capsys.readouterr()
        assert "총 30건" in captured.out
