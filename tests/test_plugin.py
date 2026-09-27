"""Behavior and identity tests for the Hermes skill-router plugin."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock


SRC_DIR = Path(__file__).parent.parent / "src"


def _load_plugin(fake_retriever):
    package_name = "hermes_skill_router_test"
    package = types.ModuleType(package_name)
    package.__path__ = [str(SRC_DIR)]
    sys.modules[package_name] = package

    retriever_module = types.ModuleType(f"{package_name}.skill_retriever")
    setattr(retriever_module, "get_skill_retriever", lambda: fake_retriever)
    sys.modules[retriever_module.__name__] = retriever_module

    spec = importlib.util.spec_from_file_location(
        f"{package_name}.plugin",
        SRC_DIR / "plugin.py",
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_l1_hint_includes_skill_view_and_description():
    retriever = MagicMock()
    retriever.retrieve_detailed.return_value = {
        "skills": ["test-driven-development"],
        "layer": "L1",
        "skill_name": "test-driven-development",
    }
    retriever.get_skill_desc.return_value = "TDD workflow"
    plugin = _load_plugin(retriever)

    result = plugin._on_pre_llm_call(user_message="use TDD")

    assert 'skill_view("test-driven-development")' in result["context"]
    assert "TDD workflow" in result["context"]


def test_manifest_and_installer_use_new_identity_and_migrate_old_name():
    manifest = (SRC_DIR / "plugin.yaml").read_text(encoding="utf-8")
    installer = (SRC_DIR.parent / "scripts" / "install.sh").read_text(encoding="utf-8")

    assert "name: hermes-skill-router" in manifest
    assert 'PLUGIN_NAME="hermes-skill-router"' in installer
    assert "eagle-eye" in installer
    assert "hermes plugins disable eagle-eye" in installer