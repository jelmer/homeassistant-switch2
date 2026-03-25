"""Sensor platform for Switch2."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import Switch2ConfigEntry
from .const import DOMAIN
from .coordinator import Switch2Coordinator


def _device_info(
    entry: Switch2ConfigEntry, coordinator: Switch2Coordinator
) -> DeviceInfo:
    customer = coordinator.data.customer
    return DeviceInfo(
        identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
        name=f"Switch2 {customer.name}",
        manufacturer="Switch2",
        entry_type=DeviceEntryType.SERVICE,
        configuration_url="https://my.switch2.co.uk",
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Switch2ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Switch2 sensor entities."""
    coordinator = entry.runtime_data

    entities: list[SensorEntity] = []
    for register_id, register_name in coordinator.data.registers.items():
        entities.append(
            Switch2MeterSensor(coordinator, entry, register_id, register_name)
        )

    entities.append(Switch2LatestBillSensor(coordinator, entry))
    entities.append(Switch2AccountBalanceSensor(coordinator, entry))

    if coordinator.bill_detail is not None:
        for i, charge in enumerate(coordinator.bill_detail.consumption_charges):
            entities.append(
                Switch2BillChargeSensor(
                    coordinator, entry, "consumption", i, charge.description
                )
            )
        for i, charge in enumerate(coordinator.bill_detail.other_charges):
            entities.append(
                Switch2BillChargeSensor(
                    coordinator, entry, "other", i, charge.description
                )
            )

    async_add_entities(entities)


class Switch2MeterSensor(CoordinatorEntity[Switch2Coordinator], SensorEntity):
    """Sensor for a Switch2 meter register."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: Switch2Coordinator,
        entry: Switch2ConfigEntry,
        register_id: str,
        register_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._register_id = register_id
        self._attr_unique_id = f"{entry.unique_id}_register_{register_id}"
        self._attr_name = register_name
        self._attr_device_info = _device_info(entry, coordinator)

    @property
    def native_value(self) -> float | None:
        """Return the latest meter reading."""
        readings = self.coordinator.data.readings
        if not readings:
            return None
        return readings[0].amount

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Return additional attributes."""
        readings = self.coordinator.data.readings
        customer = self.coordinator.data.customer
        attrs: dict[str, str | None] = {
            "account_number": customer.account_number,
            "address": customer.address,
        }
        if readings:
            attrs["reading_date"] = readings[0].date.isoformat()
            attrs["reading_type"] = readings[0].reading_type
        return attrs


class Switch2LatestBillSensor(CoordinatorEntity[Switch2Coordinator], SensorEntity):
    """Sensor showing the latest bill amount."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "GBP"
    _attr_has_entity_name = True
    _attr_name = "Latest bill"

    def __init__(
        self,
        coordinator: Switch2Coordinator,
        entry: Switch2ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.unique_id}_latest_bill"
        self._attr_device_info = _device_info(entry, coordinator)

    @property
    def native_value(self) -> float | None:
        """Return the latest bill amount."""
        bills = self.coordinator.data.bills
        if not bills:
            return None
        return bills[0].amount

    @property
    def extra_state_attributes(self) -> dict[str, str | float | None]:
        """Return additional attributes."""
        bills = self.coordinator.data.bills
        if not bills:
            return {}
        attrs: dict[str, str | float | None] = {
            "bill_date": bills[0].date.isoformat(),
            "detail_url": bills[0].detail_url,
        }
        bill_detail = self.coordinator.bill_detail
        if bill_detail is not None:
            attrs["invoice_number"] = bill_detail.invoice_number
            attrs["period_from"] = bill_detail.period_from.isoformat()
            attrs["period_to"] = bill_detail.period_to.isoformat()
        return attrs


class Switch2AccountBalanceSensor(CoordinatorEntity[Switch2Coordinator], SensorEntity):
    """Sensor showing the current account balance."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "GBP"
    _attr_has_entity_name = True
    _attr_name = "Account balance"

    def __init__(
        self,
        coordinator: Switch2Coordinator,
        entry: Switch2ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.unique_id}_account_balance"
        self._attr_device_info = _device_info(entry, coordinator)

    @property
    def native_value(self) -> float | None:
        """Return the current account balance."""
        bill_detail = self.coordinator.bill_detail
        if bill_detail is None:
            return None
        return bill_detail.balance

    @property
    def extra_state_attributes(self) -> dict[str, str | float | None]:
        """Return additional attributes."""
        bill_detail = self.coordinator.bill_detail
        if bill_detail is None:
            return {}
        return {
            "previous_balance": bill_detail.previous_balance,
            "payments_received": bill_detail.payments_received,
        }


class Switch2BillChargeSensor(CoordinatorEntity[Switch2Coordinator], SensorEntity):
    """Sensor showing a bill charge line item."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "GBP"
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: Switch2Coordinator,
        entry: Switch2ConfigEntry,
        charge_type: str,
        index: int,
        description: str,
    ) -> None:
        super().__init__(coordinator)
        self._charge_type = charge_type
        self._index = index
        self._attr_unique_id = f"{entry.unique_id}_charge_{charge_type}_{index}"
        self._attr_name = description
        self._attr_device_info = _device_info(entry, coordinator)

    @property
    def _charges(self) -> list:
        """Return the relevant charges list."""
        bill_detail = self.coordinator.bill_detail
        if bill_detail is None:
            return []
        if self._charge_type == "consumption":
            return bill_detail.consumption_charges
        return bill_detail.other_charges

    @property
    def native_value(self) -> float | None:
        """Return the charge amount."""
        charges = self._charges
        if self._index >= len(charges):
            return None
        return charges[self._index].charge

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Return additional attributes."""
        charges = self._charges
        if self._index >= len(charges):
            return {}
        return {
            "units": charges[self._index].units,
        }
