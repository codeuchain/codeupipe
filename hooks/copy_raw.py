"""MkDocs hook — copy every .md source as .txt in the built site.

This makes the docs curl-friendly: ``curl .../concepts.txt`` returns the
raw Markdown instead of the HTML wrapper.  A ``curl.txt`` sitemap is
generated automatically so ``curl .../curl.txt`` shows all available pages.
"""

import shutil
from pathlib import Path


_SITE_URL = "https://codeuchain.github.io/codeupipe"


def on_post_build(config, **kwargs):
    docs_dir = Path(config["docs_dir"])
    site_dir = Path(config["site_dir"])

    pages = []

    for md_file in sorted(docs_dir.rglob("*.md")):
        rel = md_file.relative_to(docs_dir)
        txt_dest = site_dir / rel.with_suffix(".txt")
        txt_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(md_file, txt_dest)
        pages.append(str(rel.with_suffix(".txt")))

    # Generate sitemap for curl users
    lines = [
        "codeupipe documentation (curl-friendly)",
        "=" * 43,
        "",
        "Usage:",
        f"  curl {_SITE_URL}/curl.txt              # this sitemap",
        f"  curl {_SITE_URL}/getting-started.txt   # quick start",
        f"  curl {_SITE_URL}/concepts.txt          # full API reference",
        "",
        "Available pages:",
        "",
    ]
    for page in pages:
        lines.append(f"  curl {_SITE_URL}/{page}")

    lines.append("")
    lines.append("Browse with a browser: " + _SITE_URL)
    lines.append("")

    (site_dir / "curl.txt").write_text("\n".join(lines))
