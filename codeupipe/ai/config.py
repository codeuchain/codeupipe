"""Application configuration using pydantic-settings.

Environment variables use the ORCHIE_ prefix:
    ORCHIE_REGISTRY_PATH=/custom/path/registry.db
    ORCHIE_EMBEDDING_MODEL=Snowflake/snowflake-arctic-embed-l-v2.0
    ORCHIE_COARSE_SEARCH_DIMS=256
"""

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support.

    All settings can be overridden via environment variables
    prefixed with ORCHIE_ (e.g., ORCHIE_REGISTRY_PATH).
    """

    model_config = SettingsConfigDict(
        env_prefix="ORCHIE_",
        case_sensitive=False,
        frozen=True,
    )

    # ── Registry ──────────────────────────────────────────────────────

    registry_path: Path = Field(
        default=Path.home() / ".codeupipe" / "registry.db",
        description="Path to SQLite capability registry database",
    )

    # ── Embedding model ───────────────────────────────────────────────

    embedding_model: str = Field(
        default="Snowflake/snowflake-arctic-embed-l-v2.0",
        description="HuggingFace model identifier for embeddings",
    )

    embedding_batch_size: int = Field(
        default=32,
        description="Batch size for embedding generation",
        gt=0,
    )

    embedding_timeout: float = Field(
        default=30.0,
        description="Timeout for embedding generation in seconds",
        gt=0,
    )

    # ── MRL search tuning ─────────────────────────────────────────────

    coarse_search_dims: int = Field(
        default=256,
        description="Number of dimensions for coarse MRL search pass",
        gt=0,
        le=1024,
    )

    coarse_search_top_k: int = Field(
        default=50,
        description="Number of candidates from coarse search",
        gt=0,
    )

    fine_search_top_k: int = Field(
        default=5,
        description="Final number of results after fine ranking",
        gt=0,
    )

    # ── Execution ─────────────────────────────────────────────────────

    process_timeout: float = Field(
        default=30.0,
        description="Timeout for subprocess execution in seconds",
        gt=0,
    )

    # ── File scanning ─────────────────────────────────────────────────

    skills_paths: list[Path] = Field(
        default=[Path.home() / ".copilot" / "skills"],
        description="Directories to scan for SKILL.md files",
    )

    instructions_paths: list[Path] = Field(
        default=[Path("prompts")],
        description="Directories to scan for *.instructions.md files (relative to project)",
    )

    plans_paths: list[Path] = Field(
        default=[Path("docs")],
        description="Directories to scan for *.md plan files (relative to project)",
    )

    project_root: Path = Field(
        default=Path.cwd(),
        description="Project root for resolving relative scan paths",
    )

    # ── Validators ────────────────────────────────────────────────────

    @field_validator("registry_path")
    @classmethod
    def validate_registry_path(cls, v: Path) -> Path:
        """Resolve ~/ and make path absolute."""
        if isinstance(v, str):
            v = Path(v)
        return v.expanduser().resolve()

    @field_validator("coarse_search_dims")
    @classmethod
    def validate_coarse_dims(cls, v: int) -> int:
        """Ensure coarse dims don't exceed model output dimension."""
        if v > 1024:
            raise ValueError("coarse_search_dims cannot exceed 1024")
        return v


# ── Singleton ──────────────────────────────────────────────────────────

_settings: Settings | None = None


def get_settings(**overrides) -> Settings:
    """Get the singleton Settings instance.

    Args:
        **overrides: Override specific settings (useful for testing).

    Returns:
        Application settings.
    """
    global _settings
    if _settings is None or overrides:
        _settings = Settings(**overrides)
    return _settings


def reset_settings() -> None:
    """Reset the singleton. Useful for testing with different configs."""
    global _settings
    _settings = None
