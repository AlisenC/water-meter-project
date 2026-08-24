from datetime import datetime

from backend.leak_detection import _build_periods
from backend.models import LeakMainMeterReading, LeakSubmeterReading

D0 = datetime(2024, 1, 1)
D1 = datetime(2024, 1, 2)
D2 = datetime(2024, 1, 3)
D3 = datetime(2024, 1, 4)
D4 = datetime(2024, 1, 5)


def submeter(id, mi, record_date, reading, unit=1):
    return LeakSubmeterReading(id=id, session_id=1, mi=mi, reading=reading, record_date=record_date, unit=unit)


def main(id, read_time, read_value):
    return LeakMainMeterReading(id=id, session_id=1, read_time=read_time, read_value=read_value)


def periods_by_range(periods):
    return {(p["period_start"], p["period_end"]): p for p in periods}


def test_single_household_daily_readings_produce_daily_periods():
    submeter_rows = [
        submeter(1, "A", D0, 0.0),
        submeter(2, "A", D1, 1.0),
        submeter(3, "A", D2, 2.0),
    ]
    main_rows = [main(1, D0, 10.0), main(2, D1, 11.0), main(3, D2, 12.5)]

    periods = _build_periods(submeter_rows, main_rows)

    assert len(periods) == 2
    assert periods[0]["period_start"] == D0.isoformat()
    assert periods[0]["period_end"] == D1.isoformat()
    assert periods[0]["submeter_delta"] == 1.0
    assert periods[0]["main_delta"] == 1.0
    assert periods[0]["difference"] == 0.0
    assert periods[0]["is_leak"] is False

    assert periods[1]["submeter_delta"] == 1.0
    assert periods[1]["main_delta"] == 1.5
    assert periods[1]["difference"] == 0.5


def test_household_skipped_day_widens_its_own_period_instead_of_narrow_lump():
    # Household A reports daily; household B skips D2 (Jan 3).
    submeter_rows = [
        submeter(1, "A", D0, 0.0),
        submeter(2, "A", D1, 1.0),
        submeter(3, "A", D2, 2.0),
        submeter(4, "A", D3, 3.0),
        submeter(5, "B", D0, 0.0),
        submeter(6, "B", D1, 1.0),
        submeter(7, "B", D3, 5.0),  # 4 units accrued over the D1->D3 gap
    ]
    # Main meter reports densely and evenly: +1/day.
    main_rows = [main(1, D0, 100.0), main(2, D1, 101.0), main(3, D2, 102.0), main(4, D3, 103.0)]

    periods = _build_periods(submeter_rows, main_rows)
    by_range = periods_by_range(periods)

    # B's gap produces its own widened D1->D3 row, alongside (not instead of) A's
    # normal narrow D1->D2 and D2->D3 rows, which stay unaffected by B's gap.
    assert (D1.isoformat(), D3.isoformat()) in by_range
    gap_period = by_range[(D1.isoformat(), D3.isoformat())]
    assert gap_period["submeter_delta"] == 4.0  # B only: 5.0 - 1.0
    assert gap_period["main_delta"] == 2.0  # true 2-day main flow for that exact window

    narrow_period = by_range[(D1.isoformat(), D2.isoformat())]
    assert narrow_period["submeter_delta"] == 1.0  # A only, B has no reading here
    assert narrow_period["main_delta"] == 1.0
    assert narrow_period["difference"] == 0.0

    normal_period = by_range[(D2.isoformat(), D3.isoformat())]
    assert normal_period["submeter_delta"] == 1.0
    assert normal_period["main_delta"] == 1.0
    assert normal_period["difference"] == 0.0


def test_simultaneous_gaps_in_different_households_produce_separate_or_merged_rows_without_double_counting():
    # Both A and B skip D2, but by different amounts, so their next readings differ.
    submeter_rows = [
        submeter(1, "A", D0, 0.0),
        submeter(2, "A", D1, 1.0),
        submeter(3, "A", D3, 3.0),  # A skips D2, resumes at D3
        submeter(4, "B", D0, 0.0),
        submeter(5, "B", D1, 2.0),
        submeter(6, "B", D3, 6.0),  # B skips D2 too, resumes at D3
    ]
    main_rows = [main(1, D0, 100.0), main(2, D1, 101.0), main(3, D2, 102.0), main(4, D3, 103.0)]

    periods = _build_periods(submeter_rows, main_rows)
    by_range = periods_by_range(periods)

    # Both households' gaps land on the same D1->D3 window, so they merge into one row
    # (mirroring how normal same-cadence households are aggregated), not two overlapping rows.
    assert len(periods) == 2
    gap_period = by_range[(D1.isoformat(), D3.isoformat())]
    assert gap_period["submeter_delta"] == 6.0  # A's 2.0 + B's 4.0
    assert gap_period["main_delta"] == 2.0

    total_submeter = sum(p["submeter_delta"] for p in periods)
    assert total_submeter == 9.0  # A's total 3.0 + B's total 6.0, nothing dropped or duplicated


def test_gap_at_start_of_data_has_no_prior_reading_and_is_simply_absent():
    submeter_rows = [submeter(1, "A", D0, 5.0)]  # only one reading, no pair possible yet
    main_rows = [main(1, D0, 100.0), main(2, D1, 101.0)]

    periods = _build_periods(submeter_rows, main_rows)

    assert periods == []


def test_gap_at_end_of_data_with_no_main_meter_coverage_yields_no_main_delta():
    submeter_rows = [submeter(1, "A", D0, 0.0), submeter(2, "A", D1, 1.0)]
    main_rows = []  # no main meter data at all

    periods = _build_periods(submeter_rows, main_rows)

    assert len(periods) == 1
    assert periods[0]["submeter_delta"] == 1.0
    assert periods[0]["main_delta"] is None
    assert periods[0]["difference"] is None
    assert periods[0]["is_leak"] is False
