"""ScanSkillsLink — Scan filesystem for SKILL.md files.

Reads skill directories and creates CapabilityDefinition entries
for each SKILL.md file found. Uses the file's frontmatter name
and content as the description for embedding.

Input:  payload["skills_paths"] (optional, defaults from settings)
Output: payload["scanned_capabilities"] (list of CapabilityDefinition, appended)
"""

import hashlib
from pathlib import Path

from codeupipe import Payload

from codeupipe.ai.config import get_settings
from codeupipe.ai.discovery.models import CapabilityDefinition, CapabilityType


class ScanSkillsLink:
    """Scan configured directories for SKILL.md skill files."""

    async def call(self, payload: Payload) -> Payload:
        settings = get_settings()
        skills_paths: list[Path] = payload.get("skills_paths") or settings.skills_paths

        existing = payload.get("scanned_capabilities") or []
        capabilities: list[CapabilityDefinition] = list(existing)

        for base_path in skills_paths:
            base = Path(base_path)
            if not base.exists():
                continue

            for skill_file in sorted(base.rglob("SKILL.md")):
                content = skill_file.read_text(encoding="utf-8", errors="replace")
                name = self._extract_name(skill_file, content)
                description = self._extract_description(content)
                content_hash = hashlib.sha256(content.encode()).hexdigest()

                cap = CapabilityDefinition(
                    name=name,
                    description=description,
                    capability_type=CapabilityType.SKILL,
                    source_path=str(skill_file),
                    content_hash=content_hash,
                    metadata={"skill_dir": str(skill_file.parent)},
                )
                capabilities.append(cap)

        return payload.insert("scanned_capabilities", capabilities)

    @staticmethod
    def _extract_name(path: Path, content: str) -> str:
        """Extract skill name from frontmatter or directory name."""
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("name:"):
                value = stripped[5:].strip().strip("'\"")
                if value:
                    return value
        # Fall back to parent directory name
        return path.parent.name

    @staticmethod
    def _extract_description(content: str) -> str:
        """Extract description from frontmatter or first paragraph."""
        lines = content.splitlines()
        in_frontmatter = False
        description_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            if stripped == "---":
                if in_frontmatter:
                    break  # End of frontmatter
                in_frontmatter = True
                continue
            if in_frontmatter and stripped.startswith("description:"):
                value = stripped[12:].strip().strip("'\"").rstrip(">").strip()
                if value:
                    return value
                # Multi-line description follows
                continue

        # Fall back to first non-empty, non-header line after frontmatter
        past_frontmatter = False
        fence_count = 0
        for line in lines:
            stripped = line.strip()
            if stripped == "---":
                fence_count += 1
                if fence_count >= 2:
                    past_frontmatter = True
                continue
            # No frontmatter at all — treat entire file as body
            if fence_count == 0:
                past_frontmatter = True
            if past_frontmatter and stripped and not stripped.startswith("#"):
                description_lines.append(stripped)
                if len(description_lines) >= 3:
                    break

        return " ".join(description_lines) if description_lines else ""
