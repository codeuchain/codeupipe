"""
Marketplace: Connector discovery and indexing for codeupipe.

Provides:
- fetch_index: Download / cache the marketplace index JSON
- search: Search connectors by keyword, category, or provider
- info: Get detailed info for a single connector package
- MarketplaceError: Raised on index fetch or parse failure
"""

from .index import fetch_index, search, info, MarketplaceError

__all__ = [
    "fetch_index",
    "search",
    "info",
    "MarketplaceError",
]
