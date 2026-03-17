"""EmbedCapabilityLink — Embed capability descriptions for indexing.

Takes a list of CapabilityDefinition objects and produces
embeddings for each, ready for storage in the registry.

Input:  payload["scanned_capabilities"] (list of CapabilityDefinition)
Output: payload["embedded_capabilities"] (list of (CapabilityDefinition, np.ndarray))
"""

from codeupipe import Payload

from codeupipe.ai.discovery.embedder import SnowflakeArcticEmbedder


class EmbedCapabilityLink:
    """Embed each capability's description for vector indexing."""

    async def call(self, payload: Payload) -> Payload:
        capabilities = payload.get("scanned_capabilities")
        if capabilities is None:
            raise ValueError("scanned_capabilities is required on context")

        embedder = SnowflakeArcticEmbedder()

        embedded = []
        for cap in capabilities:
            # Build rich text for embedding: name + description
            text = f"{cap.name}: {cap.description}" if cap.description else cap.name
            embedding = embedder.embed_document(text)
            embedded.append((cap, embedding))

        return payload.insert("embedded_capabilities", embedded)
