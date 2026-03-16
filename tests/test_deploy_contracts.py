"""
Tests for codeupipe.deploy.contract — platform contract loader and env validator.
"""

import pytest

from codeupipe.deploy.contract import (
    ContractError,
    ValidationResult,
    list_contracts,
    load_contract,
    validate_env,
)


# ── list_contracts ──────────────────────────────────────


class TestListContracts:
    def test_returns_list(self):
        result = list_contracts()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_entries_have_required_keys(self):
        for entry in list_contracts():
            assert "id" in entry
            assert "name" in entry

    def test_known_platforms_present(self):
        ids = {e["id"] for e in list_contracts()}
        assert "aws-lambda" in ids
        assert "kubernetes" in ids
        assert "docker" in ids
        assert "vercel" in ids


# ── load_contract ───────────────────────────────────────


class TestLoadContract:
    def test_load_aws_lambda(self):
        c = load_contract("aws-lambda")
        assert c["id"] == "aws-lambda"
        assert c["name"] == "AWS Lambda"
        assert "naming" in c
        assert "limits" in c

    def test_load_kubernetes(self):
        c = load_contract("kubernetes")
        assert c["id"] == "kubernetes"

    def test_load_unknown_raises(self):
        with pytest.raises(ContractError, match="Unknown contract"):
            load_contract("nonexistent-platform-xyz")

    def test_contract_has_expected_fields(self):
        c = load_contract("aws-lambda")
        # Every contract should have these top-level keys
        for key in ("id", "name", "category", "naming", "limits"):
            assert key in c, f"Contract missing {key!r}"


# ── validate_env ────────────────────────────────────────


class TestValidateEnv:
    def test_valid_env_passes(self):
        env = {"MY_VAR": "hello", "DB_HOST": "localhost"}
        result = validate_env(env, "aws-lambda")
        assert result.valid is True
        assert result.errors == []

    def test_naming_violation(self):
        # AWS Lambda naming: ^[a-zA-Z_][a-zA-Z0-9_]*$
        # A key starting with a digit should fail
        env = {"123BAD": "value"}
        result = validate_env(env, "aws-lambda")
        assert result.valid is False
        assert any("naming" in e.lower() or "violates" in e.lower() for e in result.errors)

    def test_forbidden_prefix_warning(self):
        # AWS Lambda forbids AWS_ prefix
        env = {"AWS_CUSTOM": "value"}
        result = validate_env(env, "aws-lambda")
        assert any("AWS_" in w for w in result.warnings)

    def test_total_size_limit(self):
        # AWS Lambda has 4096 byte total limit
        # Create env that exceeds it
        env = {f"VAR_{i}": "x" * 200 for i in range(30)}
        result = validate_env(env, "aws-lambda")
        assert result.valid is False
        assert any("total" in e.lower() for e in result.errors)

    def test_optional_var_warnings(self):
        env = {"MY_VAR": "hello"}
        result = validate_env(env, "aws-lambda")
        # AWS Lambda has optional_vars like AWS_REGION
        assert any("optional" in w.lower() for w in result.warnings)

    def test_pre_loaded_contract(self):
        contract = load_contract("kubernetes")
        env = {"APP_NAME": "test"}
        result = validate_env(env, "kubernetes", contract=contract)
        assert isinstance(result, ValidationResult)
        assert result.contract_id == "kubernetes"

    def test_repr(self):
        result = validate_env({"A": "1"}, "docker")
        assert "ValidationResult" in repr(result)
        assert "PASS" in repr(result) or "FAIL" in repr(result)


# ── ValidationResult ────────────────────────────────────


class TestValidationResult:
    def test_pass(self):
        r = ValidationResult("test", errors=[], warnings=[])
        assert r.valid is True

    def test_fail(self):
        r = ValidationResult("test", errors=["bad"], warnings=[])
        assert r.valid is False

    def test_repr_pass(self):
        r = ValidationResult("test")
        assert "PASS" in repr(r)

    def test_repr_fail(self):
        r = ValidationResult("test", errors=["x"])
        assert "FAIL" in repr(r)
