"""Tests for the switch2 sensor platform."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
)
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)
from switch2 import (
    AccountBalance,
    Bill,
    BillCharge,
    BillDetail,
    CustomerInfo,
    MeterReading,
    Switch2AuthError,
    Switch2ConnectionError,
    Switch2Data,
)

from custom_components.switch2.const import DOMAIN
from custom_components.switch2.statistics import LONDON_TZ

HEAT_STANDING = BillCharge("Heat Standing Charge", "30.00 days", 22.46)
ADMIN_STANDING = BillCharge("Admin Standing Charge", "30.00 days", 33.75)
HEAT = BillCharge("Heat", "252 kWh", 42.87)


OCTOBER_BILL = Bill(datetime(2026, 10, 27), 104.03, "https://example/bill/1")
NOVEMBER_BILL = Bill(datetime(2026, 11, 27), 120.00, "https://example/bill/2")

READINGS = [
    MeterReading(datetime(2026, 10, 26), 9166.0, "kWh", "Estimated"),
    MeterReading(datetime(2026, 9, 26), 8914.0, "kWh", "Estimated"),
]


def _data(bills: list[Bill] | None = None) -> Switch2Data:
    return Switch2Data(
        customer=CustomerInfo("Mr. Test", "ACC123", "1 Some Street"),
        readings=READINGS,
        registers={"R1": "Heat Meter"},
        bills=[OCTOBER_BILL] if bills is None else bills,
        account_balance=AccountBalance(0.0, datetime(2026, 11, 1, 18, 42)),
        register_readings={"R1": READINGS},
    )


async def _wait_for_update(hass: HomeAssistant) -> None:
    # Updates wait on the recorder thread, which async_block_till_done
    # does not know about.
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)
    await hass.async_block_till_done()


async def _refresh_with_new_bill(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    client: MagicMock,
    detail: BillDetail,
) -> None:
    client.fetch_data.return_value = _data([NOVEMBER_BILL, OCTOBER_BILL])
    client.fetch_bill_detail.return_value = detail
    await entry.runtime_data.async_refresh()
    await _wait_for_update(hass)


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
    await _wait_for_update(hass)


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

    await _refresh_with_new_bill(
        hass, entry, client, _bill_detail([HEAT], [HEAT_STANDING, ADMIN_STANDING])
    )

    assert _state(hass, "ACC123_charge_heat").state == "42.87"


async def test_charge_missing_from_latest_bill(
    hass: HomeAssistant, entry: MockConfigEntry, client: MagicMock
) -> None:
    await _setup(hass, entry)

    await _refresh_with_new_bill(
        hass, entry, client, _bill_detail([], [HEAT_STANDING, ADMIN_STANDING])
    )

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


async def test_rate_sensors(
    hass: HomeAssistant, entry: MockConfigEntry, client: MagicMock
) -> None:
    await _setup(hass, entry)

    heat = _state(hass, "ACC123_rate_heat")
    assert float(heat.state) == pytest.approx(42.87 / 252)
    assert heat.attributes["unit_of_measurement"] == "GBP/kWh"
    standing = _state(hass, "ACC123_rate_heat_standing_charge")
    assert float(standing.state) == pytest.approx(22.46 / 30)
    assert standing.attributes["unit_of_measurement"] == "GBP/day"


async def test_meter_per_register(
    hass: HomeAssistant, entry: MockConfigEntry, client: MagicMock
) -> None:
    data = _data()
    data.registers["R2"] = "Hot Water Meter"
    data.register_readings["R2"] = [
        MeterReading(datetime(2026, 10, 26), 512.0, "kWh", "Actual")
    ]
    client.fetch_data.return_value = data

    await _setup(hass, entry)

    assert _state(hass, "ACC123_register_R1").state == "9166.0"
    hot_water = _state(hass, "ACC123_register_R2")
    assert hot_water.state == "512.0"
    assert hot_water.attributes["reading_type"] == "Actual"
    assert hot_water.attributes["statistic_id"] == "switch2:acc123_r2_consumption"


async def _statistics(
    hass: HomeAssistant, statistic_id: str
) -> list[tuple[str, float | None]]:
    stats = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        datetime(2026, 1, 1, tzinfo=dt_util.UTC),
        None,
        {statistic_id},
        "hour",
        None,
        {"sum"},
    )
    return [
        (
            dt_util.utc_from_timestamp(row["start"])
            .astimezone(LONDON_TZ)
            .date()
            .isoformat(),
            row["sum"],
        )
        for row in stats.get(statistic_id, [])
    ]


async def test_statistics_written(
    hass: HomeAssistant, entry: MockConfigEntry, client: MagicMock
) -> None:
    await _setup(hass, entry)

    consumption = await _statistics(hass, "switch2:acc123_r1_consumption")
    assert len(consumption) == 31
    assert consumption[0] == ("2026-09-26", 8914.0)
    assert consumption[-1] == ("2026-10-26", 9166.0)

    cost = await _statistics(hass, "switch2:acc123_cost")
    assert len(cost) == 31
    assert cost[0] == ("2026-09-26", 0.0)
    assert cost[-1] == ("2026-10-26", pytest.approx(104.03))


async def test_cost_appended_for_new_bill(
    hass: HomeAssistant, entry: MockConfigEntry, client: MagicMock
) -> None:
    await _setup(hass, entry)

    november = _bill_detail([HEAT], [HEAT_STANDING, ADMIN_STANDING])
    november.period_from = datetime(2026, 10, 27)
    november.period_to = datetime(2026, 11, 26)
    november.total = 120.0
    await _refresh_with_new_bill(hass, entry, client, november)

    cost = await _statistics(hass, "switch2:acc123_cost")
    assert cost[-1] == ("2026-11-26", pytest.approx(224.03))
    assert len(cost) == 62


async def test_no_cost_while_a_bill_is_missing(
    hass: HomeAssistant, entry: MockConfigEntry, client: MagicMock
) -> None:
    client.fetch_bill_detail.side_effect = Switch2ConnectionError("timeout")

    await _setup(hass, entry)

    assert await _statistics(hass, "switch2:acc123_cost") == []
    assert len(await _statistics(hass, "switch2:acc123_r1_consumption")) == 31
