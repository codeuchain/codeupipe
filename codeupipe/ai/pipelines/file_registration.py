"""FileRegistrationChain — Register file-based capabilities.

Composes the file scanner Links with sync and registration:
  ScanSkills → ScanInstructions → ScanPlans → SyncLocal → Embed → Insert

Scans local filesystem for skills, instructions, and plans,
diffs against the registry, and registers only new/changed items.

Context requirements:
    - capability_registry: CapabilityRegistry

Context outputs:
    - scanned_capabilities: list[CapabilityDefinition]  (new/changed only)
    - sync_stats: dict  (added, updated, unchanged, removed counts)
    - embedded_capabilities: list[(CapabilityDefinition, np.ndarray)]
    - registered_count: int
"""

from codeupipe import Pipeline

from codeupipe.ai.filters.registration.embed_capability import EmbedCapabilityLink
from codeupipe.ai.filters.registration.insert_capability import InsertCapabilityLink
from codeupipe.ai.filters.registration.scan_instructions import ScanInstructionsLink
from codeupipe.ai.filters.registration.scan_plans import ScanPlansLink
from codeupipe.ai.filters.registration.scan_skills import ScanSkillsLink
from codeupipe.ai.filters.registration.sync_local import SyncLocalSourcesLink


def build_file_registration_chain() -> Pipeline:
    """Build the file-based capability registration chain.

    Flow:
        scan_skills → scan_instructions → scan_plans
            → sync_local → embed → insert

    Files go in, indexed capabilities come out.
    """
    chain = Pipeline()

    # Scanning phase: each scanner appends to ctx["scanned_capabilities"]
    chain.add_filter(ScanSkillsLink(), "scan_skills")
    chain.add_filter(ScanInstructionsLink(), "scan_instructions")
    chain.add_filter(ScanPlansLink(), "scan_plans")

    # Sync phase: diff against registry, filter to new/changed
    chain.add_filter(SyncLocalSourcesLink(), "sync_local")

    # Registration phase: embed and persist
    chain.add_filter(EmbedCapabilityLink(), "embed")
    chain.add_filter(InsertCapabilityLink(), "insert")

    # Sequential pipeline

    return chain
