"""Tests for switch2 integration setup."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_setup_entry_no_deprecation_warnings(hass, caplog):
    """Loading the integration must not emit deprecation warnings.

    Regression test for the DataUpdateCoordinator ContextVar deprecation
    introduced in HA 2026.x.
    """
    import logging

    from custom_components.switch2.const import DOMAIN

    caplog.set_level(logging.WARNING)

    fake_customer = MagicMock(account_number="ACC123", name="Jelmer", address="addr")
    fake_reading = MagicMock(amount=100.0, date=date(2026, 5, 1), reading_type="actual")
    fake_data = MagicMock(
        customer=fake_customer,
        registers={"R1": "Heat"},
        readings=[fake_reading],
        bills=[],
        account_balance=None,
    )
    fake_client = MagicMock()
    fake_client.fetch_data = AsyncMock(return_value=fake_data)
    fake_client.close = AsyncMock()

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"email": "x@y", "password": "p"},
        unique_id="ACC123",
        title="Switch2 (Jelmer)",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.switch2.Switch2ApiClient", return_value=fake_client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    deprecation_messages = [
        rec.getMessage()
        for rec in caplog.records
        if "Detected that custom integration" in rec.getMessage()
        or "relies on ContextVar" in rec.getMessage()
    ]
    assert deprecation_messages == [], deprecation_messages
