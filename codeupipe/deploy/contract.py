"""
Platform contract loader and environment variable validator.

Contracts are JSON files describing platform-specific constraints
for environment variables: naming rules, size limits, required
vars, and supported secret backends.

Absorbed from the Zero-Trust Deploy Config prototype. The JSON
files live in deploy/contracts/ — 23 platforms, from AWS Lambda
to Terraform.

Zero external dependencies — stdlib only.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "load_contract",
    "list_contracts",
    "validate_env",
    "ContractError",
    "ValidationResult",
]

_CONTRACTS_DIR = Path(__file__).parent / "contracts"


class ContractError(Exception):
    """Raised when a contract cannot be loaded or is malformed."""


class ValidationResult:
    """Result of validating environment variables against a contract.

    Attributes:
        valid: True if all checks pass.
        errors: List of hard failures (must fix).
        warnings: List of advisory notices (may fix).
        contract_id: The platform contract ID validated against.
    """

    __slots__ = ("valid", "errors", "warnings", "contract_id")

    def __init__(
        self,
        contract_id: str,
        errors: Optional[List[str]] = None,
        warnings: Optional[List[str]] = None,
    ):
        self.contract_id = contract_id
        self.errors = errors or []
        self.warnings = warnings or []
        self.valid = len(self.errors) == 0

    def __repr__(self) -> str:
        status = "PASS" if self.valid else "FAIL"
        return (
            f"ValidationResult({status}, contract={self.contract_id!r}, "
            f"errors={len(self.errors)}, warnings={len(self.warnings)})"
        )


def list_contracts() -> List[Dict[str, str]]:
    """List all available platform contracts.

    Returns:
        List of dicts with 'id', 'name', and 'category' for each contract.
    """
    index_path = _CONTRACTS_DIR / "index.json"
    if not index_path.exists():
        return []
    data = json.loads(index_path.read_text(encoding="utf-8"))
    # index.json may be {"contracts": [...]} or a plain list
    items = data.get("contracts", data) if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    result = []
    for item in items:
        if isinstance(item, str):
            try:
                c = load_contract(item)
                result.append({"id": c["id"], "name": c.get("name", item), "category": c.get("category", "")})
            except ContractError:
                result.append({"id": item, "name": item, "category": ""})
        elif isinstance(item, dict):
            result.append({"id": item.get("id", ""), "name": item.get("name", ""), "category": item.get("category", "")})
    return result


def load_contract(contract_id: str) -> Dict[str, Any]:
    """Load a platform contract by ID.

    Args:
        contract_id: Platform slug (e.g. 'aws-lambda', 'kubernetes').

    Returns:
        The full contract dict.

    Raises:
        ContractError: If the contract file doesn't exist or is malformed.
    """
    path = _CONTRACTS_DIR / f"{contract_id}.json"
    if not path.exists():
        available = [p.stem for p in _CONTRACTS_DIR.glob("*.json") if p.stem not in ("index", "_schema")]
        raise ContractError(
            f"Unknown contract {contract_id!r}. "
            f"Available: {', '.join(sorted(available))}"
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ContractError(f"Failed to load contract {contract_id!r}: {exc}") from exc


def validate_env(
    env_vars: Dict[str, str],
    contract_id: str,
    *,
    contract: Optional[Dict[str, Any]] = None,
) -> ValidationResult:
    """Validate environment variables against a platform contract.

    Args:
        env_vars: Dict of key→value pairs to validate.
        contract_id: Platform slug to validate against.
        contract: Pre-loaded contract dict (avoids re-reading file).

    Returns:
        ValidationResult with errors and warnings.
    """
    if contract is None:
        contract = load_contract(contract_id)

    errors: List[str] = []
    warnings: List[str] = []

    # ── Required vars ──
    for req in contract.get("required_vars", []):
        if req not in env_vars:
            errors.append(f"Missing required variable: {req}")

    # ── Naming rules ──
    naming = contract.get("naming", {})
    pattern_str = naming.get("pattern")
    forbidden_prefixes = naming.get("forbidden_prefixes", [])

    if pattern_str:
        try:
            pattern = re.compile(pattern_str)
        except re.error:
            warnings.append(f"Contract has invalid naming pattern: {pattern_str}")
            pattern = None
    else:
        pattern = None

    for key in env_vars:
        if pattern and not pattern.match(key):
            errors.append(
                f"Variable {key!r} violates naming rule: {naming.get('description', pattern_str)}"
            )
        for prefix in forbidden_prefixes:
            if key.startswith(prefix):
                warnings.append(
                    f"Variable {key!r} uses reserved prefix {prefix!r}"
                )

    # ── Size limits ──
    limits = contract.get("limits", {})
    key_max = limits.get("key_max_length")
    val_max = limits.get("value_max_length")
    max_total = limits.get("max_total_size")
    max_vars = limits.get("max_vars")

    if max_vars is not None and len(env_vars) > max_vars:
        errors.append(
            f"Too many variables: {len(env_vars)} exceeds limit of {max_vars}"
        )

    total_size = 0
    for key, value in env_vars.items():
        if key_max is not None and len(key) > key_max:
            errors.append(f"Key {key!r} exceeds max length {key_max}")
        if val_max is not None and len(str(value)) > val_max:
            errors.append(f"Value for {key!r} exceeds max length {val_max}")
        total_size += len(key) + len(str(value))

    if max_total is not None and total_size > max_total:
        errors.append(
            f"Total env size {total_size} bytes exceeds platform limit of {max_total} bytes"
        )

    # ── Optional var suggestions ──
    for opt in contract.get("optional_vars", []):
        if opt not in env_vars:
            warnings.append(f"Optional variable not set: {opt}")

    return ValidationResult(contract_id, errors, warnings)
