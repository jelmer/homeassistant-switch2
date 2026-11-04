"""Tests for the switch2 sensor platform."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from switch2 import (
    AccountBalance,
    Bill,
    BillCharge,
    BillDetail,
    CustomerInfo,
    MeterReading,
    Switch2AuthError,
    Switch2Data,
)

from custom_components.switch2.const import DOMAIN

HEAT_STANDING = BillCharge("Heat Standing Charge", "30.00 days", 22.46)
ADMIN_STANDING = BillCharge("Admin Standing Charge", "30.00 days", 33.75)
HEAT = BillCharge("Heat", "252 kWh", 42.87)


def _data() -> Switch2Data:
    return Switch2Data(
        customer=CustomerInfo("Mr. Test", "ACC123", "1 Some Street"),
        readings=[MeterReading(datetime(2026, 10, 26), 9166.0, "kWh", "Estimated")],
        registers={"R1": "Heat Meter"},
        bills=[Bill(datetime(2026, 10, 27), 104.03, "https://example/bill/1")],
        account_balance=AccountBalance(0.0, datetime(2026, 11, 1, 18, 42)),
    )


def _bill_detail(consumption: list[BillCharge], other: list[BillCharge]) -> BillDetail:
    return BillDetail(
        invoice_number="0642002369",
        date_of_issue=datetime(2026, 10, 27),
        period_from=datetime(2026, 9, 27),
        period_to=datetime(2026, 10, 26),
        consumption_charges=consumption,
        other_charges=other,
        total_excl_vat=99.08,
        vat=4.95,
        total=104.03,
        previous_balance=97.21,
        payments_received=-97.21,
        balance=104.03,
        download_url="https://example/bill/1/download",
    )


@pytest.fixture
def client() -> Iterator[MagicMock]:
    fake_client = MagicMock()
    fake_client.fetch_data = AsyncMock(return_value=_data())
    fake_client.fetch_bill_detail = AsyncMock(
        return_value=_bill_detail([HEAT], [HEAT_STANDING, ADMIN_STANDING])
    )
    fake_client.close = AsyncMock()
    with patch("custom_components.switch2.Switch2ApiClient", return_value=fake_client):
        yield fake_client


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"email": "x@y", "password": "p"},
        unique_id="ACC123",
        title="Switch2 (Mr. Test)",
    )
    entry.add_to_hass(hass)
    return entry


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _state(hass: HomeAssistant, unique_id: str) -> State:
    entity_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, unique_id)
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    return state


def _charge_unique_ids(hass: HomeAssistant) -> set[str]:
    return {
        e.unique_id
        for e in er.async_get(hass).entities.values()
        if e.platform == DOMAIN and "_charge_" in e.unique_id
    }


async def test_charge_sensors(
    hass: HomeAssistant, entry: MockConfigEntry, client: MagicMock
) -> None:
    await _setup(hass, entry)

    values = {uid: _state(hass, uid).state for uid in _charge_unique_ids(hass)}
    assert values == {
        "ACC123_charge_heat": "42.87",
        "ACC123_charge_heat_standing_charge": "22.46",
        "ACC123_charge_admin_standing_charge": "33.75",
    }
    assert _state(hass, "ACC123_charge_heat").attributes["units"] == "252 kWh"


async def test_new_charge_added_on_refresh(
    hass: HomeAssistant, entry: MockConfigEntry, client: MagicMock
) -> None:
    client.fetch_bill_detail.return_value = _bill_detail(
        [], [HEAT_STANDING, ADMIN_STANDING]
    )
    await _setup(hass, entry)
    assert _charge_unique_ids(hass) == {
        "ACC123_charge_heat_standing_charge",
        "ACC123_charge_admin_standing_charge",
    }

    client.fetch_bill_detail.return_value = _bill_detail(
        [HEAT], [HEAT_STANDING, ADMIN_STANDING]
    )
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=7))
    await hass.async_block_till_done()

    assert _state(hass, "ACC123_charge_heat").state == "42.87"


async def test_charge_missing_from_latest_bill(
    hass: HomeAssistant, entry: MockConfigEntry, client: MagicMock
) -> None:
    await _setup(hass, entry)

    client.fetch_bill_detail.return_value = _bill_detail(
        [], [HEAT_STANDING, ADMIN_STANDING]
    )
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=7))
    await hass.async_block_till_done()

    assert _state(hass, "ACC123_charge_heat").state == "unknown"
    assert _state(hass, "ACC123_charge_admin_standing_charge").state == "33.75"


async def test_migrate_index_unique_ids(
    hass: HomeAssistant, entry: MockConfigEntry, client: MagicMock
) -> None:
    client.fetch_bill_detail.return_value = _bill_detail(
        [], [HEAT_STANDING, ADMIN_STANDING]
    )
    ent_reg = er.async_get(hass)
    old = ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "ACC123_charge_other_1",
        config_entry=entry,
        suggested_object_id="switch2_admin_standing_charge",
    )

    await _setup(hass, entry)

    state = _state(hass, "ACC123_charge_admin_standing_charge")
    assert state.entity_id == old.entity_id
    assert state.state == "33.75"


async def test_latest_bill(
    hass: HomeAssistant, entry: MockConfigEntry, client: MagicMock
) -> None:
    await _setup(hass, entry)

    state = _state(hass, "ACC123_latest_bill")
    assert state.state == "104.03"
    assert "state_class" not in state.attributes
    assert state.attributes["period_from"] == "2026-09-27"
    assert state.attributes["period_to"] == "2026-10-26"
    assert state.attributes["number_of_days"] == 30
    assert state.attributes["balance"] == 104.03
    assert state.attributes["download_url"] == "https://example/bill/1/download"


async def test_meter_reading(
    hass: HomeAssistant, entry: MockConfigEntry, client: MagicMock
) -> None:
    await _setup(hass, entry)

    state = _state(hass, "ACC123_register_R1")
    assert state.state == "9166.0"
    assert state.attributes["reading_date"] == "2026-10-26"
    assert state.attributes["reading_type"] == "Estimated"


async def test_auth_failure_starts_reauth(
    hass: HomeAssistant, entry: MockConfigEntry, client: MagicMock
) -> None:
    client.fetch_data.side_effect = Switch2AuthError("bad password")

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == ["reauth"]
