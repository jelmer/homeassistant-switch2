"""DataUpdateCoordinator for Switch2."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from switch2 import (
    Bill,
    BillDetail,
    Switch2ApiClient,
    Switch2AuthError,
    Switch2Data,
    Switch2Error,
)

from .statistics import async_import_statistics

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(hours=6)


class Switch2Coordinator(DataUpdateCoordinator[Switch2Data]):
    """Coordinator to fetch data from Switch2."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: Switch2ApiClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name="Switch2",
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        # Details of the latest bill, kept when a later fetch fails.
        self.bill_detail: BillDetail | None = None
        # Issued bills do not change, so their details are fetched once.
        self._bill_details: dict[str, BillDetail] = {}

    async def _async_update_data(self) -> Switch2Data:
        try:
            data = await self.client.fetch_data()
        except Switch2AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except Switch2Error as err:
            raise UpdateFailed(f"Error fetching Switch2 data: {err}") from err

        complete = await self._async_fetch_bill_details(data.bills)
        if data.bills and data.bills[0].detail_url in self._bill_details:
            self.bill_detail = self._bill_details[data.bills[0].detail_url]

        await async_import_statistics(
            self.hass,
            data.customer.account_number,
            data.registers,
            data.register_readings,
            self._bill_details.values() if complete else None,
        )
        return data

    async def _async_fetch_bill_details(self, bills: list[Bill]) -> bool:
        """Fetch the details of new bills; return whether all are known."""
        complete = True
        for bill in bills:
            if not bill.detail_url:
                _LOGGER.warning("Bill of %s has no detail page", bill.date.date())
                complete = False
                continue
            if bill.detail_url in self._bill_details:
                continue
            try:
                detail = await self.client.fetch_bill_detail(bill)
            except Switch2Error as err:
                _LOGGER.warning(
                    "Failed to fetch bill of %s, will retry: %s", bill.date.date(), err
                )
                complete = False
                continue
            self._bill_details[bill.detail_url] = detail
        return complete
