from datetime import date, datetime, timedelta

from backend.leak_rules import (
    NIGHT_STANDARD_MULTIPLIER,
    RULE2_STANDARD_DURATION,
    DenseInterval,
    build_dense_intervals,
    compute_median_interval,
    compute_nightly_usage,
    detect_historical_deviation,
    detect_nighttime_ratio_anomalies,
    detect_sustained_rate_streaks,
    evaluate_meter_rules,
)

T0 = datetime(2024, 1, 1, 0, 0)


# --- build_dense_intervals ---------------------------------------------------

def test_build_dense_intervals_consecutive_readings_within_gap():
    readings = [
        (T0, 0.0),
        (T0 + timedelta(minutes=15), 1.0),
        (T0 + timedelta(minutes=30), 2.5),
    ]
    intervals = build_dense_intervals(readings)

    assert len(intervals) == 2
    assert intervals[0].delta == 1.0
    assert intervals[1].delta == 1.5


def test_build_dense_intervals_excludes_large_gap():
    readings = [(T0, 0.0), (T0 + timedelta(hours=3), 5.0)]

    assert build_dense_intervals(readings) == []


def test_build_dense_intervals_keeps_negative_delta():
    readings = [(T0, 10.0), (T0 + timedelta(minutes=15), 8.0)]
    intervals = build_dense_intervals(readings)

    assert len(intervals) == 1
    assert intervals[0].delta == -2.0


# --- detect_sustained_rate_streaks ------------------------------------------

def test_detect_sustained_rate_streaks_emits_ongoing_alert_for_sustained_streak():
    intervals = [
        DenseInterval(T0, T0 + timedelta(hours=1), 2.0),
        DenseInterval(T0 + timedelta(hours=1), T0 + timedelta(hours=2), 2.0),
        DenseInterval(T0 + timedelta(hours=2), T0 + timedelta(hours=3), 2.0),
    ]

    alerts = detect_sustained_rate_streaks(
        intervals,
        rate_threshold_per_hour=1.0,
        min_duration=timedelta(hours=2),
        rule_name="test_rule",
        strict=True,
    )

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert["rule"] == "test_rule"
    assert alert["ongoing"] is True
    assert alert["duration_hours"] == 3.0
    assert alert["window_start"] == T0.isoformat()
    assert alert["window_end"] == (T0 + timedelta(hours=3)).isoformat()


def test_detect_sustained_rate_streaks_below_min_duration_emits_nothing():
    intervals = [DenseInterval(T0, T0 + timedelta(hours=1), 2.0)]

    alerts = detect_sustained_rate_streaks(
        intervals,
        rate_threshold_per_hour=1.0,
        min_duration=timedelta(hours=2),
        rule_name="test_rule",
        strict=True,
    )

    assert alerts == []


def test_detect_sustained_rate_streaks_strict_vs_non_strict_boundary():
    intervals = [DenseInterval(T0, T0 + timedelta(hours=2), 2.0)]  # rate == 1.0/hr exactly

    strict_alerts = detect_sustained_rate_streaks(
        intervals, rate_threshold_per_hour=1.0, min_duration=timedelta(hours=1),
        rule_name="r", strict=True,
    )
    non_strict_alerts = detect_sustained_rate_streaks(
        intervals, rate_threshold_per_hour=1.0, min_duration=timedelta(hours=1),
        rule_name="r", strict=False,
    )

    assert strict_alerts == []
    assert len(non_strict_alerts) == 1


# --- compute_nightly_usage ---------------------------------------------------

def test_compute_nightly_usage_excludes_interval_crossing_outside_window():
    intervals = [
        DenseInterval(datetime(2024, 1, 2, 0, 0), datetime(2024, 1, 2, 1, 0), 1.0),  # inside window
        DenseInterval(datetime(2024, 1, 2, 4, 30), datetime(2024, 1, 2, 5, 30), 2.0),  # ends past window
    ]

    nights = compute_nightly_usage(intervals)

    assert len(nights) == 1
    assert nights[0]["night_date"] == "2024-01-02"
    assert nights[0]["usage_ccf"] == 1.0
    assert nights[0]["coverage_fraction"] == 0.2
    assert nights[0]["is_covered"] is False


def test_compute_nightly_usage_marks_high_coverage_night_as_covered():
    intervals = [DenseInterval(datetime(2024, 1, 3, 0, 0), datetime(2024, 1, 3, 4, 45), 3.0)]

    nights = compute_nightly_usage(intervals)

    assert nights[0]["coverage_fraction"] == 0.95
    assert nights[0]["is_covered"] is True


def test_compute_nightly_usage_excludes_interval_spanning_midnight():
    intervals = [DenseInterval(datetime(2024, 1, 4, 23, 0), datetime(2024, 1, 5, 0, 30), 1.0)]

    assert compute_nightly_usage(intervals) == []


# --- detect_nighttime_ratio_anomalies ----------------------------------------

def _covered_night(night_date: str, usage: float) -> dict:
    return {"night_date": night_date, "usage_ccf": usage, "coverage_fraction": 1.0, "is_covered": True}


def test_detect_nighttime_ratio_anomalies_flags_spike_after_enough_prior_nights():
    nights = [
        _covered_night("2024-01-01", 1.0),
        _covered_night("2024-01-02", 1.2),
        _covered_night("2024-01-03", 0.9),
        _covered_night("2024-01-04", 5.0),
    ]

    alerts = detect_nighttime_ratio_anomalies(nights, multiplier=2.0, min_prior_nights=3)

    assert len(alerts) == 1
    assert alerts[0]["night_date"] == "2024-01-04"
    assert alerts[0]["baseline_ccf"] == 1.0
    assert alerts[0]["prior_night_count"] == 3


def test_detect_nighttime_ratio_anomalies_skips_spike_without_enough_prior_nights():
    nights = [
        _covered_night("2024-01-01", 1.0),
        _covered_night("2024-01-02", 1.2),
        _covered_night("2024-01-03", 5.0),
    ]

    alerts = detect_nighttime_ratio_anomalies(nights, multiplier=2.0, min_prior_nights=3)

    assert alerts == []


# --- compute_median_interval ---------------------------------------------------

def test_compute_median_interval_returns_median_gap_in_days():
    values = [(date(2024, 1, 1), 0.0), (date(2024, 1, 3), 0.0), (date(2024, 1, 6), 0.0)]

    assert compute_median_interval(values) == 2.5


def test_compute_median_interval_defaults_to_one_for_fewer_than_two_values():
    assert compute_median_interval([(date(2024, 1, 1), 0.0)]) == 1.0
    assert compute_median_interval([]) == 1.0


# --- detect_historical_deviation ---------------------------------------------

def test_detect_historical_deviation_flags_sharp_increase_over_baseline():
    readings = [
        (datetime(2024, 1, 1), 0.0),
        (datetime(2024, 1, 11), 10.0),  # rate 1.0/day
        (datetime(2024, 1, 21), 20.0),  # rate 1.0/day
        (datetime(2024, 1, 31), 50.0),  # rate 3.0/day -- spike vs 1.0/day baseline
    ]

    alerts = detect_historical_deviation(readings)

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert["current_period_start"] == datetime(2024, 1, 21).isoformat()
    assert alert["baseline_daily_rate_units"] == 1.0
    assert alert["percent_increase"] == 200.0
    assert alert["is_gap_induced"] is False


def test_detect_historical_deviation_does_not_flag_mild_increase():
    readings = [
        (datetime(2024, 1, 1), 0.0),
        (datetime(2024, 1, 11), 10.0),
        (datetime(2024, 1, 21), 20.0),
        (datetime(2024, 1, 31), 32.0),  # rate 1.2/day, below 1.5x baseline
    ]

    assert detect_historical_deviation(readings) == []


def test_detect_historical_deviation_handles_too_few_readings():
    assert detect_historical_deviation([]) == []
    assert detect_historical_deviation([(datetime(2024, 1, 1), 0.0)]) == []


# --- evaluate_meter_rules -----------------------------------------------------

def test_evaluate_meter_rules_response_shape_with_data():
    readings = [(T0 + timedelta(minutes=15 * i), float(i)) for i in range(5)]

    result = evaluate_meter_rules(
        readings,
        scope="main",
        mi=None,
        rule2_duration=RULE2_STANDARD_DURATION,
        nighttime_multiplier=NIGHT_STANDARD_MULTIPLIER,
    )

    assert result["has_data"] is True
    assert set(result["coverage"]) == {"dense_hours", "span_hours", "reading_count"}
    assert result["coverage"]["reading_count"] == 5
    assert set(result["rules"]) == {"continuous_flow_24h", "volume_threshold", "nighttime_ratio"}
    assert "alerts" in result["rules"]["continuous_flow_24h"]


def test_evaluate_meter_rules_no_data():
    result = evaluate_meter_rules(
        [],
        scope="submeter",
        mi="H1",
        rule2_duration=RULE2_STANDARD_DURATION,
        nighttime_multiplier=NIGHT_STANDARD_MULTIPLIER,
    )

    assert result["has_data"] is False
    assert result["coverage"]["reading_count"] == 0
