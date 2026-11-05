"""Backdated consumption and cost statistics for the Energy dashboard.

Readings can be days or weeks apart, and the entity state only changes
when Home Assistant next polls. Writing external statistics instead puts
consumption and cost on the days they belong to.
Between two readings consumption is spread evenly over the days, and the
total of each bill is spread evenly over the days of its billing period;
there is no finer-grained data to go on.

Consumption is rewritten in full on every update, so estimates that are
later corrected end up right. Its sum is the meter value itself, so it does
not depend on how far back the portal's history goes. Cost has no such
anchor; issued bills do not change, so it is appended from the newest day
already recorded.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
from itertools import pairwise
from zoneinfo import ZoneInfo

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify
from homeassistant.util.unit_conversion import EnergyConverter

from switch2 import BillDetail, MeterReading

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

LONDON_TZ = ZoneInfo("Europe/London")


def consumption_statistic_id(account_number: str, register_id: str) -> str:
    return f"{DOMAIN}:{slugify(account_number)}_{slugify(register_id)}_consumption"


def cost_statistic_id(account_number: str) -> str:
    return f"{DOMAIN}:{slugify(account_number)}_cost"


def _day_start(day: date) -> datetime:
    return datetime.combine(day, time(), LONDON_TZ)


def _reading_per_day(readings: Iterable[MeterReading]) -> dict[date, float]:
    """Pick one reading per day, preferring actual readings over estimates."""
    chosen: dict[date, MeterReading] = {}
    for reading in readings:
        day = reading.date.date()
        current = chosen.get(day)
        if current is None or current.reading_type == "Estimated":
            chosen[day] = reading
    return {day: reading.amount for day, reading in sorted(chosen.items())}


def consumption_rows(readings: Iterable[MeterReading]) -> list[StatisticData]:
    """Return a row per day, with the meter value at the end of that day.

    A reading dated on a day is the meter at the end of that day, which is
    how billing periods line up with readings.
    """
    per_day = list(_reading_per_day(readings).items())
    if not per_day:
        return []
    rows: list[StatisticData] = []

    def add(day: date, value: float) -> None:
        value = round(value, 3)
        rows.append(StatisticData(start=_day_start(day), state=value, sum=value))

    for (day, value), (next_day, next_value) in pairwise(per_day):
        if next_value < value:
            _LOGGER.warning(
                "Meter reading went down from %s on %s to %s on %s",
                value,
                day,
                next_value,
                next_day,
            )
        days = (next_day - day).days
        for offset in range(days):
            add(
                day + timedelta(days=offset),
                value + (next_value - value) * offset / days,
            )
    add(*per_day[-1])
    return rows


def cost_rows(
    bill_details: Iterable[BillDetail],
    after: date | None = None,
    total: float = 0.0,
) -> list[StatisticData]:
    """Return a row per billed day after ``after``, continuing from ``total``."""
    cost_per_day: dict[date, float] = {}
    for detail in bill_details:
        first = detail.period_from.date()
        days = (detail.period_to.date() - first).days + 1
        if days <= 0:
            _LOGGER.warning(
                "Ignoring bill %s with empty period %s to %s",
                detail.invoice_number,
                detail.period_from,
                detail.period_to,
            )
            continue
        for offset in range(days):
            day = first + timedelta(days=offset)
            if after is None or day > after:
                cost_per_day[day] = cost_per_day.get(day, 0.0) + detail.total / days
    if not cost_per_day:
        return []

    rows: list[StatisticData] = []
    if after is None:
        # The dashboard shows the difference to the previous row, so the
        # first billed day needs a row before it to count from.
        first_day = min(cost_per_day)
        rows.append(
            StatisticData(start=_day_start(first_day - timedelta(days=1)), sum=total)
        )
    for day, cost in sorted(cost_per_day.items()):
        total += cost
        rows.append(StatisticData(start=_day_start(day), sum=round(total, 4)))
    return rows


async def _async_last_row(
    hass: HomeAssistant, statistic_id: str
) -> tuple[date, float] | None:
    last = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, statistic_id, True, {"sum"}
    )
    rows = last.get(statistic_id)
    if not rows:
        return None
    start = dt_util.utc_from_timestamp(rows[0]["start"]).astimezone(LONDON_TZ)
    return start.date(), rows[0].get("sum") or 0.0


async def async_import_statistics(
    hass: HomeAssistant,
    account_number: str,
    registers: dict[str, str],
    register_readings: dict[str, list[MeterReading]],
    bill_details: Iterable[BillDetail] | None,
) -> None:
    """Write the consumption of each register and the cost of all bills.

    ``bill_details`` must cover every bill so far, or be None to leave cost
    alone for now; appending after a missing bill would lose it for good.
    """
    for register_id, readings in register_readings.items():
        units = {reading.unit for reading in readings}
        if units - {"kWh"}:
            # TODO: support registers that are not metered in kWh.
            _LOGGER.warning(
                "Not importing statistics for register %s, metered in %s",
                register_id,
                ", ".join(sorted(units)),
            )
            continue
        rows = consumption_rows(readings)
        if not rows:
            continue
        async_add_external_statistics(
            hass,
            StatisticMetaData(
                has_mean=False,
                has_sum=True,
                mean_type=StatisticMeanType.NONE,
                name=f"Switch2 {registers.get(register_id, register_id)}",
                source=DOMAIN,
                statistic_id=consumption_statistic_id(account_number, register_id),
                unit_class=EnergyConverter.UNIT_CLASS,
                unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            ),
            rows,
        )

    if bill_details is None:
        return
    statistic_id = cost_statistic_id(account_number)
    last = await _async_last_row(hass, statistic_id)
    if last is None:
        rows = cost_rows(bill_details)
    else:
        rows = cost_rows(bill_details, after=last[0], total=last[1])
    if rows:
        async_add_external_statistics(
            hass,
            StatisticMetaData(
                has_mean=False,
                has_sum=True,
                mean_type=StatisticMeanType.NONE,
                name="Switch2 cost",
                source=DOMAIN,
                statistic_id=statistic_id,
                unit_class=None,
                unit_of_measurement="GBP",
            ),
            rows,
        )
