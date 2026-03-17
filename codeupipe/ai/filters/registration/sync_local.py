"""SyncLocalSourcesLink — Diff scanned capabilities against registry.

Compares scanned capabilities (from file scanners) with what's
already stored in the registry. Produces a filtered list of only
new or changed capabilities that need embedding + insertion.

Also removes stale entries that no longer exist on disk.

Input:
    payload["scanned_capabilities"] (list of CapabilityDefinition)
    payload["capability_registry"] (CapabilityRegistry)
Output:
    payload["scanned_capabilities"] (filtered: only new/changed items)
    payload["sync_stats"] (dict with added, updated, unchanged, removed counts)
"""

from codeupipe import Payload

from codeupipe.ai.discovery.models import CapabilityDefinition, CapabilityType
from codeupipe.ai.discovery.registry import CapabilityRegistry

# Types that come from local file scanning (not MCP servers)
LOCAL_TYPES = {CapabilityType.SKILL, CapabilityType.INSTRUCTION, CapabilityType.PLAN}


class SyncLocalSourcesLink:
    """Diff scanned capabilities against the registry.

    Filters scanned_capabilities to only items that need
    re-embedding and re-insertion. Handles deletions for
    stale entries that no longer exist on disk.
    """

    async def call(self, payload: Payload) -> Payload:
        scanned = payload.get("scanned_capabilities")
        if scanned is None:
            raise ValueError("scanned_capabilities is required on context")

        registry = payload.get("capability_registry")
        if not isinstance(registry, CapabilityRegistry):
            raise ValueError(
                "capability_registry (CapabilityRegistry) is required on context"
            )

        to_register: list[CapabilityDefinition] = []
        stats = {"added": 0, "updated": 0, "unchanged": 0, "removed": 0}

        # Track which source_paths we've seen from scanners
        seen_source_paths: set[str] = set()

        for cap in scanned:
            if not cap.source_path:
                # No source_path means it's not a file-based capability;
                # pass it through without sync logic
                to_register.append(cap)
                stats["added"] += 1
                continue

            seen_source_paths.add(cap.source_path)
            existing = registry.get_by_source_path(cap.source_path)

            if existing is None:
                # New file — needs embedding + insertion
                to_register.append(cap)
                stats["added"] += 1
            elif existing.content_hash != cap.content_hash:
                # Content changed — remove old, queue new for embedding
                registry.delete_by_source_path(cap.source_path)
                to_register.append(cap)
                stats["updated"] += 1
            else:
                # Unchanged — skip
                stats["unchanged"] += 1

        # Remove stale entries: registered from local files but
        # no longer present in the scan results
        for cap_type in LOCAL_TYPES:
            registered = registry.list_all(type_filter=cap_type)
            for reg in registered:
                if reg.source_path and reg.source_path not in seen_source_paths:
                    registry.delete_by_source_path(reg.source_path)
                    stats["removed"] += 1

        payload = payload.insert("scanned_capabilities", to_register)
        return payload.insert("sync_stats", stats)
