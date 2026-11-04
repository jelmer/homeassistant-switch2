"""Tests for the switch2 config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from switch2 import CustomerInfo, Switch2AuthError

from custom_components.switch2.const import DOMAIN


def _client(account_number: str = "ACC123") -> MagicMock:
    client = MagicMock()
    client.authenticate = AsyncMock(
        return_value=(CustomerInfo("Mr. Test", account_number, "addr"), None)
    )
    client.close = AsyncMock()
    return client


async def test_user_flow(hass: HomeAssistant) -> None:
    with (
        patch(
            "custom_components.switch2.config_flow.Switch2ApiClient",
            return_value=_client(),
        ),
        patch("custom_components.switch2.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data={"email": "x@y", "password": "p"},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Switch2 (Mr. Test)"
    assert result["result"].unique_id == "ACC123"


async def test_user_flow_invalid_auth(hass: HomeAssistant) -> None:
    client = _client()
    client.authenticate.side_effect = Switch2AuthError("nope")
    with patch(
        "custom_components.switch2.config_flow.Switch2ApiClient",
        return_value=client,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data={"email": "x@y", "password": "p"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    client.close.assert_awaited_once()


def _entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"email": "x@y", "password": "old"},
        unique_id="ACC123",
    )
    entry.add_to_hass(hass)
    return entry


async def test_reauth(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    with (
        patch(
            "custom_components.switch2.config_flow.Switch2ApiClient",
            return_value=_client(),
        ),
        patch("custom_components.switch2.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"password": "new"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data == {"email": "x@y", "password": "new"}


async def test_reauth_wrong_account(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    result = await entry.start_reauth_flow(hass)

    with patch(
        "custom_components.switch2.config_flow.Switch2ApiClient",
        return_value=_client("OTHER"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"password": "new"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unique_id_mismatch"
    assert entry.data["password"] == "old"
