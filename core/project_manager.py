"""
Research Project Manager
연구 주제별 프로젝트 디렉토리 관리
"""
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any


@dataclass
class ResearchProject:
    name: str                          # "류마티스-봉독 유전체 연관 탐색"
    slug: str                          # "ra_bee_venom"
    description: str = ""
    keywords: List[str] = field(default_factory=list)
    pmids: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    @property
    def subdirs(self) -> List[str]:
        return ["results", "nextflow_work", "nfcore_output", "analysis", "logs", "literature"]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResearchProject":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class ProjectManager:
    """연구 프로젝트 디렉토리 관리자"""

    def __init__(self, base_dir: Path = Path("./research_projects")):
        self.base_dir = base_dir

    @staticmethod
    def slugify(name: str) -> str:
        """프로젝트명을 안전한 디렉토리명으로 변환"""
        slug = re.sub(r'[^\w\s-]', '', name.lower())
        slug = re.sub(r'[-\s]+', '_', slug).strip('_')
        return slug or "unnamed_project"

    def create_project(self, name: str, description: str = "",
                       keywords: List[str] = None, pmids: List[str] = None) -> ResearchProject:
        """새 연구 프로젝트 생성"""
        slug = self.slugify(name)
        now = datetime.now().isoformat()

        project = ResearchProject(
            name=name, slug=slug, description=description,
            keywords=keywords or [], pmids=pmids or [],
            created_at=now, updated_at=now,
        )

        # 디렉토리 구조 생성
        project_dir = self.base_dir / slug
        project_dir.mkdir(parents=True, exist_ok=True)
        for subdir in project.subdirs:
            (project_dir / subdir).mkdir(exist_ok=True)

        # project.json 저장
        self._save_project(project)

        # pmids.txt 저장 (있으면)
        if pmids:
            self._save_pmids(project)

        return project

    def list_projects(self) -> List[ResearchProject]:
        """모든 프로젝트 목록"""
        projects = []
        if not self.base_dir.exists():
            return projects
        for pdir in sorted(self.base_dir.iterdir()):
            pfile = pdir / "project.json"
            if pfile.exists():
                projects.append(self._load_project(pfile))
        return projects

    def get_project(self, slug: str) -> Optional[ResearchProject]:
        """slug으로 프로젝트 조회"""
        pfile = self.base_dir / slug / "project.json"
        if pfile.exists():
            return self._load_project(pfile)
        return None

    def get_project_dir(self, slug: str) -> Path:
        """프로젝트 루트 디렉토리"""
        return self.base_dir / slug

    def get_results_dir(self, slug: str) -> Path:
        """프로젝트 결과 디렉토리"""
        return self.base_dir / slug / "results"

    def add_pmids(self, slug: str, pmids: List[str]) -> Optional[ResearchProject]:
        """프로젝트에 PMID 추가"""
        project = self.get_project(slug)
        if not project:
            return None
        existing = set(project.pmids)
        for pmid in pmids:
            if pmid not in existing:
                project.pmids.append(pmid)
        project.updated_at = datetime.now().isoformat()
        self._save_project(project)
        self._save_pmids(project)
        return project

    def _save_project(self, project: ResearchProject):
        pfile = self.base_dir / project.slug / "project.json"
        pfile.write_text(json.dumps(project.to_dict(), indent=2, ensure_ascii=False))

    def _save_pmids(self, project: ResearchProject):
        pmid_file = self.base_dir / project.slug / "pmids.txt"
        pmid_file.write_text("\n".join(project.pmids) + "\n")

    def _load_project(self, pfile: Path) -> ResearchProject:
        data = json.loads(pfile.read_text())
        return ResearchProject.from_dict(data)
