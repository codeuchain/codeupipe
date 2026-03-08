"""
codeupipe.upgrade — Regenerate project scaffolding to match latest codeupipe.

Reads cup.toml to determine what was originally scaffolded, then regenerates
CI configs, deploy artifacts, and README to incorporate the latest templates.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

__all__ = ["upgrade_project"]


def upgrade_project(
    project_dir: str = ".",
    *,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Upgrade a codeupipe project's scaffolded files to current templates.

    Reads cup.toml for the original project settings, then regenerates:
    - CI configs (using current renderer versions)
    - README.md (with updated instructions)
    - Deploy artifacts (if applicable)

    Args:
        project_dir: Path to the project root.
        dry_run: If True, report what would change without writing.

    Returns:
        Dict with 'updated', 'skipped', 'warnings' keys.
    """
    from codeupipe.deploy.manifest import load_manifest
    from codeupipe.deploy.init import (
        _CI_PROVIDERS, _render_readme, _TEMPLATES, detect_ci, regenerate_ci,
    )

    root = Path(project_dir)
    manifest_path = root / "cup.toml"

    if not manifest_path.exists():
        return {
            "updated": [],
            "skipped": [],
            "warnings": ["No cup.toml found — nothing to upgrade."],
        }

    manifest = load_manifest(str(manifest_path))
    project = manifest.get("project", {})
    name = project.get("name", root.name)
    deploy = manifest.get("deploy", {})
    deploy_target = deploy.get("target", "docker")
    frontend_section = manifest.get("frontend", {})
    frontend = frontend_section.get("framework") if frontend_section else None

    # Detect template from recipes
    template = _detect_template(root)

    updated: List[str] = []
    skipped: List[str] = []
    warnings: List[str] = []

    # 1. Regenerate CI configs
    existing_ci = detect_ci(project_dir)
    for entry in existing_ci:
        provider = entry["provider"]
        if provider not in _CI_PROVIDERS:
            warnings.append(f"Unknown CI provider '{provider}' — skipping")
            skipped.append(entry["path"])
            continue

        renderer, ci_rel_dir, ci_filename = _CI_PROVIDERS[provider]
        new_content = renderer(name, frontend, deploy_target)
        ci_path = root / ci_rel_dir / ci_filename

        if ci_path.exists():
            old_content = ci_path.read_text()
            if old_content == new_content:
                skipped.append(str(ci_path))
                continue

        if not dry_run:
            ci_path.parent.mkdir(parents=True, exist_ok=True)
            ci_path.write_text(new_content)
        updated.append(str(ci_path))

    # 2. Regenerate README.md
    if template:
        readme_path = root / "README.md"
        new_readme = _render_readme(name, template, frontend, deploy_target)
        if readme_path.exists():
            old_readme = readme_path.read_text()
            if old_readme != new_readme:
                if not dry_run:
                    readme_path.write_text(new_readme)
                updated.append(str(readme_path))
            else:
                skipped.append(str(readme_path))
        else:
            if not dry_run:
                readme_path.write_text(new_readme)
            updated.append(str(readme_path))

    if not existing_ci:
        warnings.append("No CI config detected — use 'cup ci --provider github' to add one.")

    return {
        "updated": updated,
        "skipped": skipped,
        "warnings": warnings,
    }


def _detect_template(root: Path) -> Optional[str]:
    """Detect which template was used by looking at pipeline configs."""
    from codeupipe.deploy.init import _TEMPLATES

    pipelines_dir = root / "pipelines"
    if not pipelines_dir.is_dir():
        return None

    recipe_files = {f.stem for f in pipelines_dir.glob("*.json")}

    for template_name, info in _TEMPLATES.items():
        template_recipes = set(info["recipes"])
        if template_recipes & recipe_files:
            return template_name
    return None
