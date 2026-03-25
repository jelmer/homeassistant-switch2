"""DataUpdateCoordinator for Switch2."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from switch2 import Switch2ApiClient, Switch2ConnectionError, Switch2Data

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(hours=6)


class Switch2Coordinator(DataUpdateCoordinator[Switch2Data]):
    """Coordinator to fetch data from Switch2."""

    def __init__(self, hass: HomeAssistant, client: Switch2ApiClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Switch2",
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> Switch2Data:
        try:
            return await self.client.fetch_data()
        except Switch2ConnectionError as err:
            raise UpdateFailed(f"Error fetching Switch2 data: {err}") from err
