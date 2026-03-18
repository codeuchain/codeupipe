"""Tests for ``cup ai-keys`` CLI command.

Exercises the _handle_keys handler via direct invocation to verify
argument parsing and output formatting.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from codeupipe.ai.providers.api_key_store import ApiKeyEntry, ApiKeyStore


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def store(tmp_path):
    """Isolated ApiKeyStore backed by tmp_path."""
    return ApiKeyStore(store_path=tmp_path / "keys.enc")


@pytest.fixture()
def openai_entry():
    return ApiKeyEntry(
        name="openai",
        base_url="https://api.openai.com/v1",
        api_key="sk-test-abc123",
        model="gpt-4.1",
    )


# ── Tests: _handle_keys directly via import ──────────────────────────
# We test the handler function directly (unit-style) by mocking args.


class _FakeArgs:
    """Minimal namespace for argparse results."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _patch_store(monkeypatch, store):
    """Patch ApiKeyStore constructor to return our test store."""
    monkeypatch.setattr(
        "codeupipe.ai.providers.api_key_store.ApiKeyStore.__init__",
        lambda self, *a, **kw: store.__init__(
            store_path=store._store_path,
            master_key=store._key,
        ),
    )
    # Also need to ensure the import inside _handle_keys gets our store.
    # Easier: patch at the source module level.
    monkeypatch.setattr(
        "codeupipe.ai.providers.api_key_store.ApiKeyStore",
        lambda *a, **kw: store,
    )


class TestHandleKeysSave:
    """cup ai-keys save."""

    @pytest.mark.unit
    def test_save_success(self, store, monkeypatch, capsys):
        from codeupipe.cli.commands.ai_cmds import _handle_keys

        _patch_store(monkeypatch, store)
        args = _FakeArgs(
            action="save",
            name="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-test-abc",
            model="gpt-4.1",
            json_output=False,
        )
        rc = _handle_keys(args)
        assert rc == 0
        out = capsys.readouterr().out
        assert "Saved" in out
        assert "openai" in out
        # Verify actually persisted
        assert store.get("openai") is not None

    @pytest.mark.unit
    def test_save_missing_name(self, capsys):
        from codeupipe.cli.commands.ai_cmds import _handle_keys

        args = _FakeArgs(
            action="save", name=None,
            base_url="x", api_key="x", model="x",
            json_output=False,
        )
        rc = _handle_keys(args)
        assert rc == 1

    @pytest.mark.unit
    def test_save_missing_fields(self, capsys):
        from codeupipe.cli.commands.ai_cmds import _handle_keys

        args = _FakeArgs(
            action="save", name="foo",
            base_url=None, api_key="x", model=None,
            json_output=False,
        )
        rc = _handle_keys(args)
        assert rc == 1


class TestHandleKeysList:
    """cup ai-keys list."""

    @pytest.mark.unit
    def test_list_empty(self, store, monkeypatch, capsys):
        from codeupipe.cli.commands.ai_cmds import _handle_keys

        _patch_store(monkeypatch, store)
        args = _FakeArgs(action="list", json_output=False)
        rc = _handle_keys(args)
        assert rc == 0
        out = capsys.readouterr().out
        assert "No API keys" in out

    @pytest.mark.unit
    def test_list_with_entries(self, store, openai_entry, monkeypatch, capsys):
        from codeupipe.cli.commands.ai_cmds import _handle_keys

        store.save(openai_entry)
        store.set_active("openai")
        _patch_store(monkeypatch, store)
        args = _FakeArgs(action="list", json_output=False)
        rc = _handle_keys(args)
        assert rc == 0
        out = capsys.readouterr().out
        assert "openai" in out
        assert "(active)" in out

    @pytest.mark.unit
    def test_list_json(self, store, openai_entry, monkeypatch, capsys):
        from codeupipe.cli.commands.ai_cmds import _handle_keys

        store.save(openai_entry)
        _patch_store(monkeypatch, store)
        args = _FakeArgs(action="list", json_output=True)
        rc = _handle_keys(args)
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["count"] == 1


class TestHandleKeysRemove:
    """cup ai-keys remove."""

    @pytest.mark.unit
    def test_remove_existing(self, store, openai_entry, monkeypatch, capsys):
        from codeupipe.cli.commands.ai_cmds import _handle_keys

        store.save(openai_entry)
        _patch_store(monkeypatch, store)
        args = _FakeArgs(action="remove", name="openai", json_output=False)
        rc = _handle_keys(args)
        assert rc == 0
        out = capsys.readouterr().out
        assert "Removed" in out

    @pytest.mark.unit
    def test_remove_missing_name(self, capsys):
        from codeupipe.cli.commands.ai_cmds import _handle_keys

        args = _FakeArgs(action="remove", name=None, json_output=False)
        rc = _handle_keys(args)
        assert rc == 1


class TestHandleKeysActive:
    """cup ai-keys active [--name N]."""

    @pytest.mark.unit
    def test_set_active(self, store, openai_entry, monkeypatch, capsys):
        from codeupipe.cli.commands.ai_cmds import _handle_keys

        store.save(openai_entry)
        _patch_store(monkeypatch, store)
        args = _FakeArgs(action="active", name="openai", json_output=False)
        rc = _handle_keys(args)
        assert rc == 0
        out = capsys.readouterr().out
        assert "Active provider set to" in out

    @pytest.mark.unit
    def test_get_active(self, store, openai_entry, monkeypatch, capsys):
        from codeupipe.cli.commands.ai_cmds import _handle_keys

        store.save(openai_entry)
        store.set_active("openai")
        _patch_store(monkeypatch, store)
        args = _FakeArgs(action="active", name=None, json_output=False)
        rc = _handle_keys(args)
        assert rc == 0
        out = capsys.readouterr().out
        assert "openai" in out
        assert "gpt-4.1" in out

    @pytest.mark.unit
    def test_no_active_set(self, store, monkeypatch, capsys):
        from codeupipe.cli.commands.ai_cmds import _handle_keys

        _patch_store(monkeypatch, store)
        args = _FakeArgs(action="active", name=None, json_output=False)
        rc = _handle_keys(args)
        assert rc == 0
        out = capsys.readouterr().out
        assert "No active provider" in out


class TestHandleKeysShow:
    """cup ai-keys show --name N."""

    @pytest.mark.unit
    def test_show_existing(self, store, openai_entry, monkeypatch, capsys):
        from codeupipe.cli.commands.ai_cmds import _handle_keys

        store.save(openai_entry)
        _patch_store(monkeypatch, store)
        args = _FakeArgs(action="show", name="openai", json_output=False)
        rc = _handle_keys(args)
        assert rc == 0
        out = capsys.readouterr().out
        assert "openai" in out
        assert "gpt-4.1" in out
        # Key should be redacted
        assert "sk-test-abc123" not in out
        assert "sk-t****" in out

    @pytest.mark.unit
    def test_show_not_found(self, store, monkeypatch, capsys):
        from codeupipe.cli.commands.ai_cmds import _handle_keys

        _patch_store(monkeypatch, store)
        args = _FakeArgs(action="show", name="nope", json_output=False)
        rc = _handle_keys(args)
        assert rc == 0
        out = capsys.readouterr().out
        assert "not found" in out
