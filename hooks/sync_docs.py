"""MkDocs hook — sync root .md files into docs/ before build.

Root-level Markdown files (CONCEPTS.md, BEST_PRACTICES.md, INDEX.md,
ROADMAP.md) are the **single source of truth**.  This hook copies them
into the docs/ directory with the filenames mkdocs nav expects, so the
site always reflects the latest content without manual duplication.

Runs during the ``on_pre_build`` event — before MkDocs reads any pages.
"""

import shutil
from pathlib import Path

# Root .md file → docs/ filename expected by mkdocs.yml nav
_FILE_MAP = {
    "CONCEPTS.md": "concepts.md",
    "BEST_PRACTICES.md": "best-practices.md",
    "INDEX.md": "module-index.md",
    "ROADMAP.md": "roadmap.md",
}


def on_pre_build(config, **kwargs):
    """Copy root .md files into docs_dir so mkdocs can serve them."""
    project_root = Path(config["config_file_path"]).parent
    docs_dir = Path(config["docs_dir"])

    for root_name, docs_name in _FILE_MAP.items():
        src = project_root / root_name
        dst = docs_dir / docs_name

        if not src.exists():
            print(f"  [sync_docs] WARNING: {root_name} not found, skipping")
            continue

        shutil.copy2(str(src), str(dst))
        print(f"  [sync_docs] {root_name} → docs/{docs_name}")
