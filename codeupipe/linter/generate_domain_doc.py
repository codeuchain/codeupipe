"""
generate_domain_doc: Build ``agents/<domain>.md`` for each skill domain.

Generates a focused, agent-optimized reference doc for each discovered
skill domain.  Respects hand-maintained docs: if a file exists without
the ``<!-- agent-docs:generated -->`` marker, it is left untouched.
"""

from __future__ import annotations

from pathlib import Path
from string import Template
from typing import Any, Dict, List


_GENERATED_MARKER = "<!-- agent-docs:generated -->"

_DOMAIN_TEMPLATE = Template("""\
${generated_marker}
# ${project_name} ${domain_title} — Agent Reference

> `curl ${site_url}/agents/${domain_name}.txt`

---

## Exports

| Export | Module |
|--------|--------|
${export_rows}

---

## Quick Start

<!-- TODO: Add quick start examples for ${domain_title} -->

---

## Examples

<!-- TODO: Add copy-paste ready examples for ${domain_title} -->
""")


class GenerateDomainDocs:
    """Generate ``agents/<domain>.md`` for each skill domain.

    Reads ``skill_domains``, ``site_url``, ``project_name``, and
    ``docs_dir`` from the payload.

    Sets ``domain_docs`` — a dict mapping domain name to generated
    content, and ``domain_docs_written`` — list of paths that were
    actually written (skips hand-maintained files).
    """

    def call(self, payload):
        domains = payload.get("skill_domains", [])
        site_url = payload.get("site_url", "").rstrip("/")
        project_name = payload.get("project_name", "project")
        docs_dir = payload.get("docs_dir", "docs")
        mode = payload.get("agent_docs_mode", "validate")

        docs = {}
        written = []
        agents_dir = Path(docs_dir) / "agents"

        for domain in domains:
            name = domain["name"]
            content = self._render_domain(domain, site_url, project_name)
            docs[name] = content

            if mode in ("init", "update"):
                target = agents_dir / f"{name}.md"
                if self._should_write(target, mode):
                    agents_dir.mkdir(parents=True, exist_ok=True)
                    target.write_text(content, encoding="utf-8")
                    written.append(str(target))

        payload = payload.insert("domain_docs", docs)
        payload = payload.insert("domain_docs_written", written)
        return payload

    @staticmethod
    def _render_domain(
        domain: Dict[str, Any], site_url: str, project_name: str,
    ) -> str:
        """Render a single domain doc from template."""
        name = domain["name"]
        title = name.replace("_", " ").replace("-", " ").title()
        exports = domain.get("exports", [])

        if exports:
            rows = []
            modules = domain.get("modules", [])
            mod_str = ", ".join(modules) if modules else "—"
            for exp in exports:
                rows.append(f"| `{exp}` | {mod_str} |")
            export_rows = "\n".join(rows)
        else:
            export_rows = "| *(no exports discovered)* | — |"

        return _DOMAIN_TEMPLATE.substitute(
            generated_marker=_GENERATED_MARKER,
            project_name=project_name,
            domain_title=title,
            domain_name=name,
            site_url=site_url,
            export_rows=export_rows,
        )

    @staticmethod
    def _should_write(target: Path, mode: str) -> bool:
        """Determine whether to write/overwrite a domain doc.

        - ``init`` mode: only write if file doesn't exist
        - ``update`` mode: write if file doesn't exist OR has the generated
          marker (hand-maintained files are left alone)
        """
        if not target.exists():
            return True
        if mode == "init":
            return False  # don't overwrite on init

        # update mode: check for generated marker
        try:
            content = target.read_text(encoding="utf-8")
            return content.startswith(_GENERATED_MARKER)
        except (OSError, UnicodeDecodeError):
            return False
