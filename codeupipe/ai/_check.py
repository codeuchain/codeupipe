"""Import guard for codeupipe.ai — fail fast with clear instructions."""


def require_ai_deps() -> None:
    """Raise ImportError with install instructions if [ai] extras missing."""
    missing = []
    for mod in ("pydantic", "mcp"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        raise ImportError(
            "codeupipe.ai requires extra dependencies "
            f"(missing: {', '.join(missing)}). "
            "Install with: pip install codeupipe[ai]"
        )
