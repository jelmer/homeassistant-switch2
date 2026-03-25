"""Config flow for Switch2 integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from switch2 import Switch2ApiClient, Switch2AuthError, Switch2ConnectionError
from .const import CONF_EMAIL, CONF_PASSWORD, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class Switch2ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Switch2."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            client = Switch2ApiClient(
                user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
            )
            try:
                customer = await client.authenticate()
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
            finally:
                await client.close()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
