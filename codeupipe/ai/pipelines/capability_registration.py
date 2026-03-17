"""CapabilityRegistrationChain — Register MCP server capabilities.

Composes the registration Links into a pipeline:
  ScanServer → EmbedCapability → InsertCapability

Runs once per server dock. Takes server metadata and stores
each capability with its embedding for future discovery.

Context requirements:
    - server_name: str
    - server_tools: list[dict]  (tool metadata from MCP server)
    - capability_registry: CapabilityRegistry

Context outputs:
    - scanned_capabilities: list[CapabilityDefinition]
    - embedded_capabilities: list[(CapabilityDefinition, np.ndarray)]
    - registered_count: int
"""

from codeupipe import Pipeline

from codeupipe.ai.filters.registration.embed_capability import EmbedCapabilityLink
from codeupipe.ai.filters.registration.insert_capability import InsertCapabilityLink
from codeupipe.ai.filters.registration.scan_server import ScanServerLink


def build_capability_registration_chain() -> Pipeline:
    """Build the capability registration chain.

    Flow:
        scan_server → embed_capability → insert_capability

    Server tools go in, indexed capabilities come out.
    """
    chain = Pipeline()

    chain.add_filter(ScanServerLink(), "scan_server")
    chain.add_filter(EmbedCapabilityLink(), "embed_capability")
    chain.add_filter(InsertCapabilityLink(), "insert_capability")

    # Sequential pipeline

    return chain
