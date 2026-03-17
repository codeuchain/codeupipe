"""
validate_agent_docs: Check completeness and freshness of agent documentation.

Validates that the skill index and all domain docs exist, are referenced
in the nav config, and have the expected structure.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


class ValidateAgentDocs:
    """Validate agent documentation completeness.

    Reads ``skill_domains`` and ``docs_dir`` from the payload.
    Sets ``agent_docs_report`` with validation results.
    """

    def call(self, payload):
        domains = payload.get("skill_domains", [])
        docs_dir = payload.get("docs_dir", "docs")
        nav_file = payload.get("nav_file", "mkdocs.yml")

        report = self._validate(domains, docs_dir, nav_file)
        return payload.insert("agent_docs_report", report)

    def _validate(
        self,
        domains: List[Dict[str, Any]],
        docs_dir: str,
        nav_file: str,
    ) -> Dict[str, Any]:
        """Run all validation checks."""
        docs_path = Path(docs_dir)
        issues = []
        missing = []
        orphaned = []

        # 1. Check skill index exists
        index_path = docs_path / "agents.md"
        if not index_path.exists():
            issues.append({
                "type": "missing_index",
                "message": "agents.md skill index not found",
                "path": str(index_path),
            })

        # 2. Check each domain doc exists
        agents_dir = docs_path / "agents"
        expected_names = {d["name"] for d in domains}

        for domain in domains:
            name = domain["name"]
            domain_path = agents_dir / f"{name}.md"
            if not domain_path.exists():
                missing.append(name)
                issues.append({
                    "type": "missing_domain",
                    "message": f"agents/{name}.md not found",
                    "path": str(domain_path),
                    "domain": name,
                })

        # 3. Check for orphaned domain docs
        if agents_dir.exists():
            for md_file in sorted(agents_dir.glob("*.md")):
                name = md_file.stem
                if name not in expected_names:
                    orphaned.append(name)
                    issues.append({
                        "type": "orphaned_domain",
                        "message": f"agents/{name}.md has no matching skill domain",
                        "path": str(md_file),
                        "domain": name,
                    })

        # 4. Check each domain doc starts with curl URL
        for domain in domains:
            name = domain["name"]
            domain_path = agents_dir / f"{name}.md"
            if domain_path.exists():
                try:
                    content = domain_path.read_text(encoding="utf-8")
                    if f"/agents/{name}.txt" not in content:
                        issues.append({
                            "type": "missing_curl_url",
                            "message": f"agents/{name}.md missing curl URL",
                            "path": str(domain_path),
                            "domain": name,
                        })
                except (OSError, UnicodeDecodeError):
                    pass

        # 5. Check skill index references all domains
        if index_path.exists():
            try:
                index_content = index_path.read_text(encoding="utf-8")
                for domain in domains:
                    name = domain["name"]
                    if f"/agents/{name}.txt" not in index_content:
                        issues.append({
                            "type": "missing_catalog_entry",
                            "message": f"agents.md skill catalog missing {name}",
                            "domain": name,
                        })
            except (OSError, UnicodeDecodeError):
                pass

        # 6. Check nav file references agent docs
        nav_issues = self._check_nav(nav_file, domains)
        issues.extend(nav_issues)

        documented = len(expected_names) - len(missing)

        return {
            "total_domains": len(domains),
            "documented": documented,
            "missing": missing,
            "orphaned": orphaned,
            "issues": issues,
            "status": "ok" if not issues else "issues_found",
        }

    @staticmethod
    def _check_nav(
        nav_file: str, domains: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Check that the nav config includes agent doc entries."""
        nav_path = Path(nav_file)
        if not nav_path.exists():
            return []

        issues = []
        try:
            content = nav_path.read_text(encoding="utf-8")
            # Simple check: does the nav file mention agents.md?
            if "agents.md" not in content:
                issues.append({
                    "type": "missing_nav_index",
                    "message": "Nav config missing agents.md entry",
                    "path": str(nav_path),
                })

            # Check each domain
            for domain in domains:
                name = domain["name"]
                pattern = f"agents/{name}.md"
                if pattern not in content:
                    issues.append({
                        "type": "missing_nav_domain",
                        "message": f"Nav config missing agents/{name}.md",
                        "domain": name,
                        "path": str(nav_path),
                    })
        except (OSError, UnicodeDecodeError):
            pass

        return issues
