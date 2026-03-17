"""ScanInstructionsLink — Scan filesystem for *.instructions.md files.

Reads instruction directories and creates CapabilityDefinition entries
for each .instructions.md file found.

Input:  payload["instructions_paths"] (optional, defaults from settings)
Output: payload["scanned_capabilities"] (list of CapabilityDefinition, appended)
"""

import hashlib
from pathlib import Path

from codeupipe import Payload

from codeupipe.ai.config import get_settings
from codeupipe.ai.discovery.models import CapabilityDefinition, CapabilityType


class ScanInstructionsLink:
    """Scan configured directories for *.instructions.md files."""

    async def call(self, payload: Payload) -> Payload:
        settings = get_settings()
        instructions_paths: list[Path] = (
            payload.get("instructions_paths") or settings.instructions_paths
        )
        project_root: Path = payload.get("project_root") or settings.project_root

        existing = payload.get("scanned_capabilities") or []
        capabilities: list[CapabilityDefinition] = list(existing)

        for base_path in instructions_paths:
            base = Path(base_path)
            # Resolve relative paths against project root
            if not base.is_absolute():
                base = project_root / base
            if not base.exists():
                continue

            for instr_file in sorted(base.rglob("*.instructions.md")):
                content = instr_file.read_text(encoding="utf-8", errors="replace")
                name = self._extract_name(instr_file)
                description = self._extract_description(content)
                content_hash = hashlib.sha256(content.encode()).hexdigest()

                cap = CapabilityDefinition(
                    name=name,
                    description=description,
                    capability_type=CapabilityType.INSTRUCTION,
                    source_path=str(instr_file),
                    content_hash=content_hash,
                    metadata={"applies_to": self._extract_applies_to(content)},
                )
                capabilities.append(cap)

        return payload.insert("scanned_capabilities", capabilities)

    @staticmethod
    def _extract_name(path: Path) -> str:
        """Derive instruction name from filename."""
        # foo.instructions.md → foo
        stem = path.name
        if stem.endswith(".instructions.md"):
            return stem[: -len(".instructions.md")]
        return path.stem

    @staticmethod
    def _extract_description(content: str) -> str:
        """Extract first heading or first paragraph as description."""
        lines = content.splitlines()
        past_frontmatter = False
        fence_count = 0

        for line in lines:
            stripped = line.strip()
            if stripped == "---":
                fence_count += 1
                if fence_count >= 2:
                    past_frontmatter = True
                continue
            # If no frontmatter, start immediately
            if fence_count == 0:
                past_frontmatter = True

            if past_frontmatter and stripped:
                # Use first heading text
                if stripped.startswith("#"):
                    return stripped.lstrip("#").strip()
                return stripped

        return ""

    @staticmethod
    def _extract_applies_to(content: str) -> str:
        """Extract applyTo from frontmatter."""
        in_frontmatter = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped == "---":
                if in_frontmatter:
                    break
                in_frontmatter = True
                continue
            if in_frontmatter and stripped.startswith("applyTo:"):
                return stripped[8:].strip().strip("'\"")
        return "**"
