"""Config flow for Switch2 integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import probatio
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from switch2 import (
    CustomerInfo,
    Switch2ApiClient,
    Switch2AuthError,
    Switch2ConnectionError,
)

from .const import CONF_EMAIL, CONF_PASSWORD, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_EMAIL): str,
        probatio.Required(CONF_PASSWORD): str,
    }
)

STEP_REAUTH_DATA_SCHEMA = probatio.Schema({probatio.Required(CONF_PASSWORD): str})


async def _login(email: str, password: str) -> CustomerInfo:
    client = Switch2ApiClient(email, password)
    try:
        customer, _ = await client.authenticate()
    finally:
        await client.close()
    return customer


class Switch2ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Switch2."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                customer = await _login(
                    user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
                )
            except Switch2AuthError:
                errors["base"] = "invalid_auth"
            except Switch2ConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during login")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(customer.account_number)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Switch2 ({customer.name})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle rejected credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new password."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        email = reauth_entry.data[CONF_EMAIL]

        if user_input is not None:
            try:
                customer = await _login(email, user_input[CONF_PASSWORD])
            except Switch2AuthError:
                errors["base"] = "invalid_auth"
            except Switch2ConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during login")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(customer.account_number)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_DATA_SCHEMA,
            description_placeholders={"email": email},
            errors=errors,
        )
