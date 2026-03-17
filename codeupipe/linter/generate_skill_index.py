"""
generate_skill_index: Build the ``agents.md`` skill index from discovered domains.

Produces a lightweight skill index following the Anthropic skill-reference
pattern: discovery protocol, project summary, skill catalog table with
curl URLs, key types quick reference, full page map, and agent notes.
"""

from __future__ import annotations

from string import Template
from typing import Any, Dict, List


_INDEX_TEMPLATE = Template("""\
# ${project_name} — Agent Skill Index

> **Entry point for AI agents, LLMs, and automated tools.**
> Read this file first. It tells you what ${project_name} can do and where to
> find the details. Each skill below links to a focused reference doc
> available as plain-text Markdown — no HTML parsing required.

---

## Discovery Protocol

```bash
# 1. Read this index (you're here)
curl ${site_url}/agents.txt

# 2. Pick the skill you need from the catalog below
curl ${site_url}/agents/<skill>.txt

# 3. All page URLs
curl ${site_url}/curl.txt
```

---

## Skill Catalog

Each skill has a dedicated reference doc. Curl the URL to get the full guide.

| Skill | URL | Summary |
|-------|-----|---------|
${skill_rows}

---

## Page Map

| Path | Description |
|------|-------------|
| `/agents.txt` | This file — skill index and discovery protocol |
${domain_page_rows}

All URLs are under `${site_url}/`.

---

## Notes for Agents

- **HTML comments** (`<!-- cup:ref ... -->`) in `.txt` files are doc-freshness
  markers for `cup doc-check`. Ignore them — they're not content.
- **Payload is immutable** — `.insert()` returns a new Payload. Forgetting
  to capture the return value is the #1 agent mistake.
- All examples are verified by the test suite.
""")


class GenerateSkillIndex:
    """Generate the ``agents.md`` skill index from discovered domains.

    Reads ``skill_domains``, ``site_url``, and ``project_name`` from the
    payload.  Sets ``skill_index_content`` (the full markdown string) and
    ``skill_index_path`` (relative path where it should be written).
    """

    def call(self, payload):
        domains = payload.get("skill_domains", [])
        site_url = payload.get("site_url", "").rstrip("/")
        project_name = payload.get("project_name", "project")
        docs_dir = payload.get("docs_dir", "docs")

        skill_rows = self._build_skill_rows(domains, site_url)
        page_rows = self._build_page_rows(domains)

        content = _INDEX_TEMPLATE.substitute(
            project_name=project_name,
            site_url=site_url,
            skill_rows=skill_rows,
            domain_page_rows=page_rows,
        )

        payload = payload.insert("skill_index_content", content)
        payload = payload.insert("skill_index_path", f"{docs_dir}/agents.md")
        return payload

    @staticmethod
    def _build_skill_rows(
        domains: List[Dict[str, Any]], site_url: str,
    ) -> str:
        lines = []
        for d in domains:
            name = d["name"]
            title = name.replace("_", " ").replace("-", " ").title()
            url = f"`/agents/{name}.txt`"
            summary = d.get("summary", "")
            lines.append(f"| **{title}** | [{url}](agents/{name}.md) | {summary} |")
        return "\n".join(lines)

    @staticmethod
    def _build_page_rows(domains: List[Dict[str, Any]]) -> str:
        lines = []
        for d in domains:
            name = d["name"]
            title = name.replace("_", " ").replace("-", " ").title()
            summary = d.get("summary", "")
            lines.append(f"| `/agents/{name}.txt` | {title} — {summary} |")
        return "\n".join(lines)
