"""Tests for the switch2 consumption and cost statistics."""

from __future__ import annotations

from datetime import datetime

from switch2 import BillCharge, BillDetail, MeterReading

from custom_components.switch2.statistics import (
    LONDON_TZ,
    consumption_rows,
    cost_rows,
)


def _reading(day: int, month: int, amount: float, kind: str = "Actual") -> MeterReading:
    return MeterReading(datetime(2026, month, day), amount, "kWh", kind)


def _bill(period_from: datetime, period_to: datetime, total: float) -> BillDetail:
    return BillDetail(
        invoice_number="1",
        date_of_issue=period_to,
        period_from=period_from,
        period_to=period_to,
        consumption_charges=[BillCharge("Heat", "1 kWh", 1.0)],
        other_charges=[],
        total_excl_vat=total,
        vat=0.0,
        total=total,
        previous_balance=0.0,
        payments_received=0.0,
        balance=total,
        download_url="",
    )


def _summary(rows: list) -> list[tuple[str, float]]:
    return [(row["start"].date().isoformat(), row["sum"]) for row in rows]


def test_consumption_is_spread_between_readings() -> None:
    rows = consumption_rows([_reading(4, 10, 130.0), _reading(1, 10, 100.0)])

    assert _summary(rows) == [
        ("2026-10-01", 100.0),
        ("2026-10-02", 110.0),
        ("2026-10-03", 120.0),
        ("2026-10-04", 130.0),
    ]
    assert rows[0]["start"].tzinfo == LONDON_TZ
    assert rows[0]["start"].hour == 0


def test_consumption_prefers_actual_over_estimated() -> None:
    rows = consumption_rows(
        [
            _reading(2, 10, 150.0, "Estimated"),
            _reading(2, 10, 120.0),
            _reading(1, 10, 100.0),
        ]
    )

    assert _summary(rows) == [("2026-10-01", 100.0), ("2026-10-02", 120.0)]


def test_consumption_without_readings() -> None:
    assert consumption_rows([]) == []


def test_cost_is_spread_over_the_billing_period() -> None:
    rows = cost_rows([_bill(datetime(2026, 10, 1), datetime(2026, 10, 3), 30.0)])

    assert _summary(rows) == [
        ("2026-09-30", 0.0),
        ("2026-10-01", 10.0),
        ("2026-10-02", 20.0),
        ("2026-10-03", 30.0),
    ]


def test_cost_continues_after_the_last_recorded_day() -> None:
    bills = [
        _bill(datetime(2026, 10, 1), datetime(2026, 10, 2), 20.0),
        _bill(datetime(2026, 10, 3), datetime(2026, 10, 4), 4.0),
    ]

    rows = cost_rows(bills, after=datetime(2026, 10, 2).date(), total=20.0)

    assert _summary(rows) == [("2026-10-03", 22.0), ("2026-10-04", 24.0)]
