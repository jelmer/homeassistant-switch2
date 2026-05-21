"""Pytest config for switch2 tests."""

from __future__ import annotations

import pathlib

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture
def hass_config_dir(tmp_path: pathlib.Path) -> str:
    """Test config dir with our custom_components linked in."""
    src = pathlib.Path(__file__).resolve().parent.parent / "custom_components"
    (tmp_path / "custom_components").symlink_to(src)
    return str(tmp_path)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
