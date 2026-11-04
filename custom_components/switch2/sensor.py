"""Sensor platform for Switch2."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from switch2 import BillCharge, BillDetail

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


def _all_charges(bill_detail: BillDetail) -> list[BillCharge]:
    return bill_detail.consumption_charges + bill_detail.other_charges


def _charge_unique_id(entry: Switch2ConfigEntry, description: str) -> str:
    return f"{entry.unique_id}_charge_{slugify(description)}"


@callback
def _migrate_charge_unique_ids(
    hass: HomeAssistant, entry: Switch2ConfigEntry, bill_detail: BillDetail
) -> None:
    """Move charge entities from index-based to description-based unique IDs.

    Index-based IDs attach the wrong values to an entity as soon as the set
    or order of line items on the latest bill changes.
    """
    ent_reg = er.async_get(hass)
    for charge_type, charges in (
        ("consumption", bill_detail.consumption_charges),
        ("other", bill_detail.other_charges),
    ):
        for index, charge in enumerate(charges):
            entity_id = ent_reg.async_get_entity_id(
                "sensor", DOMAIN, f"{entry.unique_id}_charge_{charge_type}_{index}"
            )
            if entity_id is None:
                continue
            new_unique_id = _charge_unique_id(entry, charge.description)
            if ent_reg.async_get_entity_id("sensor", DOMAIN, new_unique_id):
                continue
            ent_reg.async_update_entity(entity_id, new_unique_id=new_unique_id)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Switch2ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Switch2 sensor entities."""
    coordinator = entry.runtime_data

    entities: list[SensorEntity] = [
        Switch2MeterSensor(coordinator, entry, register_id, register_name)
        for register_id, register_name in coordinator.data.registers.items()
    ]
    entities.append(Switch2LatestBillSensor(coordinator, entry))
    entities.append(Switch2AccountBalanceSensor(coordinator, entry))
    async_add_entities(entities)

    if coordinator.bill_detail is not None:
        _migrate_charge_unique_ids(hass, entry, coordinator.bill_detail)

    known_unique_ids: set[str] = set()

    @callback
    def _add_new_charge_sensors() -> None:
        bill_detail = coordinator.bill_detail
        if bill_detail is None:
            return
        new_entities: list[SensorEntity] = []
        for charge in _all_charges(bill_detail):
            unique_id = _charge_unique_id(entry, charge.description)
            if unique_id in known_unique_ids:
                continue
            known_unique_ids.add(unique_id)
            new_entities.append(
                Switch2BillChargeSensor(coordinator, entry, charge.description)
            )
        if new_entities:
            async_add_entities(new_entities)

    _add_new_charge_sensors()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_charge_sensors))


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
        # TODO: the API client only fetches readings for the register that
        # the portal selects by default, so with multiple registers every
        # sensor reports that register's readings.
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
            attrs["reading_date"] = readings[0].date.date().isoformat()
            attrs["reading_type"] = readings[0].reading_type
        return attrs


class Switch2LatestBillSensor(CoordinatorEntity[Switch2Coordinator], SensorEntity):
    """Sensor showing the latest bill amount."""

    # No state class: the amount of each bill is independent of the previous
    # one, so it is neither a measurement nor a running total.
    _attr_device_class = SensorDeviceClass.MONETARY
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
    def extra_state_attributes(self) -> dict[str, str | float | int | None]:
        """Return additional attributes."""
        bills = self.coordinator.data.bills
        if not bills:
            return {}
        attrs: dict[str, str | float | int | None] = {
            "bill_date": bills[0].date.date().isoformat(),
            "detail_url": bills[0].detail_url,
        }
        bill_detail = self.coordinator.bill_detail
        if bill_detail is not None:
            attrs["invoice_number"] = bill_detail.invoice_number
            attrs["period_from"] = bill_detail.period_from.date().isoformat()
            attrs["period_to"] = bill_detail.period_to.date().isoformat()
            # Billing periods include both the first and the last day.
            attrs["number_of_days"] = (
                bill_detail.period_to - bill_detail.period_from
            ).days + 1
            attrs["date_of_issue"] = bill_detail.date_of_issue.date().isoformat()
            attrs["total_excl_vat"] = bill_detail.total_excl_vat
            attrs["vat"] = bill_detail.vat
            attrs["previous_balance"] = bill_detail.previous_balance
            attrs["payments_received"] = bill_detail.payments_received
            attrs["balance"] = bill_detail.balance
            attrs["download_url"] = bill_detail.download_url
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
        account_balance = self.coordinator.data.account_balance
        if account_balance is None:
            return None
        return account_balance.balance

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Return additional attributes."""
        account_balance = self.coordinator.data.account_balance
        if account_balance is None:
            return {}
        return {
            "last_updated": account_balance.last_updated.isoformat(),
        }


class Switch2BillChargeSensor(CoordinatorEntity[Switch2Coordinator], SensorEntity):
    """Sensor showing a line item on the latest bill."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "GBP"
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: Switch2Coordinator,
        entry: Switch2ConfigEntry,
        description: str,
    ) -> None:
        super().__init__(coordinator)
        self._description = description
        self._attr_unique_id = _charge_unique_id(entry, description)
        self._attr_name = description
        self._attr_device_info = _device_info(entry, coordinator)

    @property
    def _charge(self) -> BillCharge | None:
        """Return this line item on the latest bill, if it is present."""
        bill_detail = self.coordinator.bill_detail
        if bill_detail is None:
            return None
        for charge in _all_charges(bill_detail):
            if charge.description == self._description:
                return charge
        return None

    @property
    def native_value(self) -> float | None:
        """Return the charge amount."""
        charge = self._charge
        if charge is None:
            return None
        return charge.charge

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Return additional attributes."""
        charge = self._charge
        if charge is None:
            return {}
        return {"units": charge.units}
