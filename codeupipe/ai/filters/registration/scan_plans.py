"""ScanPlansLink — Scan docs directories for plan .md files.

Reads plan directories and creates CapabilityDefinition entries
for each .md file found.

Input:  payload["plans_paths"] (optional, defaults from settings)
Output: payload["scanned_capabilities"] (list of CapabilityDefinition, appended)
"""

import hashlib
from pathlib import Path

from codeupipe import Payload

from codeupipe.ai.config import get_settings
from codeupipe.ai.discovery.models import CapabilityDefinition, CapabilityType


class ScanPlansLink:
    """Scan configured directories for .md plan documents."""

    async def call(self, payload: Payload) -> Payload:
        settings = get_settings()
        plans_paths: list[Path] = payload.get("plans_paths") or settings.plans_paths
        project_root: Path = payload.get("project_root") or settings.project_root

        existing = payload.get("scanned_capabilities") or []
        capabilities: list[CapabilityDefinition] = list(existing)

        for base_path in plans_paths:
            base = Path(base_path)
            # Resolve relative paths against project root
            if not base.is_absolute():
                base = project_root / base
            if not base.exists():
                continue

            for plan_file in sorted(base.rglob("*.md")):
                content = plan_file.read_text(encoding="utf-8", errors="replace")
                name = self._extract_name(plan_file)
                description = self._extract_description(content)
                content_hash = hashlib.sha256(content.encode()).hexdigest()

                cap = CapabilityDefinition(
                    name=name,
                    description=description,
                    capability_type=CapabilityType.PLAN,
                    source_path=str(plan_file),
                    content_hash=content_hash,
                    metadata={},
                )
                capabilities.append(cap)

        return payload.insert("scanned_capabilities", capabilities)

    @staticmethod
    def _extract_name(path: Path) -> str:
        """Derive plan name from filename without extension."""
        return path.stem

    @staticmethod
    def _extract_description(content: str) -> str:
        """Extract first heading as description."""
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                return stripped.lstrip("#").strip()
        return ""
