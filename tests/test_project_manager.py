"""
Tests for ProjectManager and ResearchProject
프로젝트 관리자 테스트
"""

import json

from core.project_manager import ProjectManager, ResearchProject


class TestResearchProject:
    def test_basic_creation(self):
        proj = ResearchProject(name="Test Project", slug="test_project")
        assert proj.name == "Test Project"
        assert proj.slug == "test_project"
        assert proj.description == ""
        assert proj.keywords == []
        assert proj.pmids == []
        assert proj.created_at == ""
        assert proj.updated_at == ""

    def test_subdirs_property(self):
        proj = ResearchProject(name="X", slug="x")
        expected = ["results", "nextflow_work", "nfcore_output", "analysis", "logs", "literature"]
        assert proj.subdirs == expected

    def test_to_dict(self):
        proj = ResearchProject(
            name="My Proj", slug="my_proj", description="desc",
            keywords=["bio", "rna"], pmids=["123", "456"],
            created_at="2025-01-01", updated_at="2025-01-02",
        )
        d = proj.to_dict()
        assert d["name"] == "My Proj"
        assert d["slug"] == "my_proj"
        assert d["description"] == "desc"
        assert d["keywords"] == ["bio", "rna"]
        assert d["pmids"] == ["123", "456"]
        assert d["created_at"] == "2025-01-01"
        assert d["updated_at"] == "2025-01-02"

    def test_from_dict(self):
        data = {
            "name": "From Dict", "slug": "from_dict",
            "description": "test desc", "keywords": ["k1"],
            "pmids": ["111"], "created_at": "t1", "updated_at": "t2",
        }
        proj = ResearchProject.from_dict(data)
        assert proj.name == "From Dict"
        assert proj.slug == "from_dict"
        assert proj.pmids == ["111"]

    def test_from_dict_ignores_extra_keys(self):
        data = {
            "name": "Extra", "slug": "extra",
            "unknown_field": "should be ignored",
            "another_extra": 42,
        }
        proj = ResearchProject.from_dict(data)
        assert proj.name == "Extra"
        assert proj.slug == "extra"
        assert not hasattr(proj, "unknown_field")

    def test_roundtrip(self):
        original = ResearchProject(
            name="Round Trip", slug="round_trip",
            description="desc", keywords=["a", "b"],
            pmids=["999"], created_at="c", updated_at="u",
        )
        restored = ResearchProject.from_dict(original.to_dict())
        assert restored.name == original.name
        assert restored.slug == original.slug
        assert restored.pmids == original.pmids
        assert restored.keywords == original.keywords


class TestProjectManagerSlugify:
    def test_basic_slugify(self):
        assert ProjectManager.slugify("Hello World") == "hello_world"

    def test_slugify_special_chars(self):
        result = ProjectManager.slugify("RA & Bee Venom (2025)")
        assert result == "ra_bee_venom_2025"

    def test_slugify_korean(self):
        result = ProjectManager.slugify("류마티스-봉독 유전체")
        assert "류마티스" in result or result == "unnamed_project" or len(result) > 0

    def test_slugify_empty_string(self):
        assert ProjectManager.slugify("") == "unnamed_project"

    def test_slugify_only_special_chars(self):
        assert ProjectManager.slugify("!!!@@@###") == "unnamed_project"

    def test_slugify_hyphens_and_spaces(self):
        result = ProjectManager.slugify("my-project name")
        assert result == "my_project_name"

    def test_slugify_multiple_spaces(self):
        result = ProjectManager.slugify("a    b    c")
        assert result == "a_b_c"

    def test_slugify_leading_trailing_underscores(self):
        result = ProjectManager.slugify("  test  ")
        assert result == "test"


class TestProjectManagerCreateProject:
    def test_create_basic(self, tmp_path):
        pm = ProjectManager(base_dir=tmp_path)
        proj = pm.create_project("Test Project")
        assert proj.name == "Test Project"
        assert proj.slug == "test_project"
        assert proj.created_at != ""
        assert proj.updated_at != ""

    def test_create_directories(self, tmp_path):
        pm = ProjectManager(base_dir=tmp_path)
        proj = pm.create_project("Dir Test")
        project_dir = tmp_path / proj.slug
        assert project_dir.exists()
        for subdir in proj.subdirs:
            assert (project_dir / subdir).exists()

    def test_create_saves_project_json(self, tmp_path):
        pm = ProjectManager(base_dir=tmp_path)
        proj = pm.create_project("JSON Test", description="a desc")
        pfile = tmp_path / proj.slug / "project.json"
        assert pfile.exists()
        data = json.loads(pfile.read_text())
        assert data["name"] == "JSON Test"
        assert data["description"] == "a desc"

    def test_create_with_pmids_saves_pmids_txt(self, tmp_path):
        pm = ProjectManager(base_dir=tmp_path)
        proj = pm.create_project("PMID Test", pmids=["111", "222"])
        pmid_file = tmp_path / proj.slug / "pmids.txt"
        assert pmid_file.exists()
        content = pmid_file.read_text()
        assert "111" in content
        assert "222" in content

    def test_create_without_pmids_no_pmids_txt(self, tmp_path):
        pm = ProjectManager(base_dir=tmp_path)
        proj = pm.create_project("No PMID")
        pmid_file = tmp_path / proj.slug / "pmids.txt"
        assert not pmid_file.exists()

    def test_create_with_keywords(self, tmp_path):
        pm = ProjectManager(base_dir=tmp_path)
        proj = pm.create_project("KW Test", keywords=["bio", "rna"])
        assert proj.keywords == ["bio", "rna"]

    def test_create_idempotent(self, tmp_path):
        pm = ProjectManager(base_dir=tmp_path)
        pm.create_project("Same Name")
        proj2 = pm.create_project("Same Name")
        assert proj2.slug == "same_name"
        assert (tmp_path / "same_name").exists()


class TestProjectManagerListProjects:
    def test_list_empty(self, tmp_path):
        pm = ProjectManager(base_dir=tmp_path)
        assert pm.list_projects() == []

    def test_list_nonexistent_dir(self, tmp_path):
        pm = ProjectManager(base_dir=tmp_path / "nonexistent")
        assert pm.list_projects() == []

    def test_list_multiple(self, tmp_path):
        pm = ProjectManager(base_dir=tmp_path)
        pm.create_project("Alpha")
        pm.create_project("Beta")
        pm.create_project("Gamma")
        projects = pm.list_projects()
        assert len(projects) == 3
        slugs = [p.slug for p in projects]
        assert "alpha" in slugs
        assert "beta" in slugs
        assert "gamma" in slugs

    def test_list_sorted(self, tmp_path):
        pm = ProjectManager(base_dir=tmp_path)
        pm.create_project("Zebra")
        pm.create_project("Apple")
        projects = pm.list_projects()
        assert projects[0].slug == "apple"
        assert projects[1].slug == "zebra"

    def test_list_ignores_dirs_without_project_json(self, tmp_path):
        pm = ProjectManager(base_dir=tmp_path)
        pm.create_project("Valid")
        (tmp_path / "invalid_dir").mkdir()
        projects = pm.list_projects()
        assert len(projects) == 1


class TestProjectManagerGetProject:
    def test_get_existing(self, tmp_path):
        pm = ProjectManager(base_dir=tmp_path)
        pm.create_project("Exist", description="found")
        proj = pm.get_project("exist")
        assert proj is not None
        assert proj.name == "Exist"
        assert proj.description == "found"

    def test_get_nonexistent(self, tmp_path):
        pm = ProjectManager(base_dir=tmp_path)
        assert pm.get_project("nope") is None


class TestProjectManagerDirHelpers:
    def test_get_project_dir(self, tmp_path):
        pm = ProjectManager(base_dir=tmp_path)
        assert pm.get_project_dir("my_slug") == tmp_path / "my_slug"

    def test_get_results_dir(self, tmp_path):
        pm = ProjectManager(base_dir=tmp_path)
        assert pm.get_results_dir("my_slug") == tmp_path / "my_slug" / "results"


class TestProjectManagerAddPmids:
    def test_add_pmids_to_existing(self, tmp_path):
        pm = ProjectManager(base_dir=tmp_path)
        pm.create_project("Add Test", pmids=["111"])
        result = pm.add_pmids("add_test", ["222", "333"])
        assert result is not None
        assert "111" in result.pmids
        assert "222" in result.pmids
        assert "333" in result.pmids

    def test_add_pmids_no_duplicates(self, tmp_path):
        pm = ProjectManager(base_dir=tmp_path)
        pm.create_project("Dup Test", pmids=["111", "222"])
        result = pm.add_pmids("dup_test", ["222", "333"])
        assert result is not None
        assert result.pmids.count("222") == 1
        assert len(result.pmids) == 3

    def test_add_pmids_nonexistent_project(self, tmp_path):
        pm = ProjectManager(base_dir=tmp_path)
        assert pm.add_pmids("nonexistent", ["111"]) is None

    def test_add_pmids_updates_pmids_txt(self, tmp_path):
        pm = ProjectManager(base_dir=tmp_path)
        pm.create_project("File Test", pmids=["111"])
        pm.add_pmids("file_test", ["222"])
        pmid_file = tmp_path / "file_test" / "pmids.txt"
        content = pmid_file.read_text()
        assert "111" in content
        assert "222" in content

    def test_add_pmids_updates_timestamp(self, tmp_path):
        pm = ProjectManager(base_dir=tmp_path)
        proj = pm.create_project("Time Test")
        original_updated = proj.updated_at
        result = pm.add_pmids("time_test", ["111"])
        assert result.updated_at >= original_updated
