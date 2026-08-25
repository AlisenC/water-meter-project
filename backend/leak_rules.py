"""Pure, DB-agnostic implementation of the SFPUC/EyeOnWater leak-detection rules
(source: "SFPUC & EyeOnWater Leak Detection Technical Rules").

Every function here takes plain (timestamp, cumulative_value) reading sequences
already normalized to CCF by the caller, so this module has no SQLAlchemy/session
dependency and can be exercised directly against fixture CSVs for verification.

Rules 1-3 (continuous flow, volume threshold, nighttime ratio) run in
leak_detection.session_analysis against the leak-detection tool's main-meter
import only, as an addition alongside that tool's original main-vs-submeter
comparison rather than a replacement of it -- submeter data is manually read
and too sparse for rules 1-3 to ever apply. Rule 4 (historical deviation)'s
baseline/rate methodology is reused by main.py's /anomalies with a stricter
trigger multiplier than RULE4_TRIGGER_MULTIPLIER below (see main.py for why);
this module keeps the SFPUC doc's own default so it stays an accurate,
reusable implementation of the doc itself.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from statistics import median

from .units import to_units

# --- Constants -------------------------------------------------------------
# "SFPUC doc" = stated directly in the source rules. "judgment call" = fills a gap
# the source doc leaves open.

# Max gap between two readings to still count as continuous coverage. Judgment
# call: comfortably covers the 15-min AMI fixture, excludes the daily-only one.
MAX_READING_GAP_FOR_CONTINUITY = timedelta(minutes=70)

# Rule 1: 24h continuous flow (SFPUC doc) -- resets on any hour at/below threshold.
#
# The doc states this threshold in raw "gallons" (1.0), but real AMI export data
# (test_data/leak_test_data/range-export-full2aug6.csv) never has a quiet interval
# anywhere near that low -- a literal 1 gal/hr floor is essentially always
# exceeded, turning normal baseline flow into a permanent "leak". Same failure
# mode as the historical GALLONS_PER_UNIT bug (units.py): a "gallons" figure
# that's actually kgal-scaled. Judgment call: treat the doc's stated thresholds
# (here and in rule 2) the same way, via the same to_units() conversion, rather
# than trusting the doc's units literally.
RULE1_THRESHOLD_CCF_PER_HOUR = to_units(1.0, unit=0)  # 1.0 "gallon" treated as kgal
RULE1_MIN_DURATION = timedelta(hours=24)

# Rule 2: 48h volume threshold (SFPUC doc); 72h for commercial/multi-family
# (6+ units, main-meter only).
RULE2_THRESHOLD_CCF_PER_HOUR = to_units(7.5, unit=0)  # 7.5 "gallons" treated as kgal, see rule 1
RULE2_STANDARD_DURATION = timedelta(hours=48)
RULE2_MULTI_FAMILY_DURATION = timedelta(hours=72)
MULTI_FAMILY_UNIT_THRESHOLD = 6  # SFPUC doc

# Rule 3: nighttime ratio (SFPUC doc: 2x baseline). Night window is a judgment call.
NIGHT_WINDOW_START = time(0, 0)
NIGHT_WINDOW_END = time(5, 0)
NIGHT_MIN_COVERAGE_FRACTION = 0.9  # judgment call
NIGHT_MIN_PRIOR_NIGHTS = 3  # judgment call
NIGHT_STANDARD_MULTIPLIER = 2.0  # SFPUC doc

# Rule 4: historical deviation (SFPUC doc: 90-day baseline, >=50% increase).
RULE4_BASELINE_WINDOW = timedelta(days=90)
RULE4_TRIGGER_MULTIPLIER = 1.5

# Gap-vs-median-interval multiplier for flagging a spike as gap-induced.
GAP_MULTIPLIER = 1.5


@dataclass(frozen=True)
class DenseInterval:
    """One consecutive-reading interval trusted as continuous coverage."""

    start: datetime
    end: datetime
    delta: float

    @property
    def duration(self) -> timedelta:
        return self.end - self.start

    @property
    def duration_hours(self) -> float:
        return self.duration.total_seconds() / 3600

    @property
    def rate_per_hour(self) -> float:
        hours = self.duration_hours
        return self.delta / hours if hours > 0 else 0.0


def build_dense_intervals(
    readings: list[tuple[datetime, float]],
    max_gap: timedelta = MAX_READING_GAP_FOR_CONTINUITY,
) -> list[DenseInterval]:
    """Builds consecutive-pair intervals dense enough to trust as continuous coverage.

    Excludes pairs with a larger gap rather than interpolating across it. Does not
    clamp negative deltas -- a meter rollback must break a streak, not be absorbed
    as "0 flow, still fine" (that clamping only belongs in
    detect_historical_deviation's baseline averaging).

    Args:
        readings: Sorted (timestamp, cumulative_value) pairs, already normalized to CCF.
        max_gap: Max gap between readings to still count as continuous.

    Returns:
        Dense intervals in chronological order; empty if none qualify.
    """
    intervals = []
    for (t_prev, v_prev), (t_curr, v_curr) in zip(readings, readings[1:]):
        gap = t_curr - t_prev
        if gap <= timedelta(0) or gap > max_gap:
            continue
        intervals.append(DenseInterval(start=t_prev, end=t_curr, delta=v_curr - v_prev))
    return intervals


def detect_sustained_rate_streaks(
    intervals: list[DenseInterval],
    rate_threshold_per_hour: float,
    min_duration: timedelta,
    rule_name: str,
    strict: bool,
) -> list[dict]:
    """Shared streak engine for rules 1 (continuous flow) and 2 (volume threshold) --
    same reset/streak state machine, differing only in threshold, duration, and
    comparison operator.

    A streak breaks not just on a sub-threshold reading but also across any coverage
    gap between intervals (interval[i+1].start must equal interval[i].end). Emits one
    alert per streak crossing the duration threshold (not repeated every hour); the
    window spans the full streak, not just the crossing point.

    Args:
        intervals: Dense intervals from `build_dense_intervals`, in chronological order.
        rate_threshold_per_hour: Flow-rate threshold in CCF/hour.
        min_duration: Minimum sustained duration above threshold required to alert.
        rule_name: Rule identifier stamped onto each alert.
        strict: True for `>` (rule 1), False for `>=` (rule 2).

    Returns:
        One alert dict per qualifying streak, including whether it's `ongoing`.
    """
    alerts: list[dict] = []
    streak_start: datetime | None = None
    streak_end: datetime | None = None
    streak_min_rate: float | None = None

    def close_streak(ongoing: bool) -> None:
        if streak_start is not None and streak_end is not None and streak_end - streak_start >= min_duration:
            alerts.append({
                "rule": rule_name,
                "window_start": streak_start.isoformat(),
                "window_end": streak_end.isoformat(),
                "duration_hours": round((streak_end - streak_start).total_seconds() / 3600, 3),
                "threshold_rate_ccf_per_hr": round(rate_threshold_per_hour, 6),
                "min_observed_rate_ccf_per_hr": round(streak_min_rate, 6) if streak_min_rate is not None else None,
                "ongoing": ongoing,
            })

    prev_end: datetime | None = None
    for interval in intervals:
        contiguous = prev_end is not None and interval.start == prev_end
        if not contiguous and streak_start is not None:
            close_streak(ongoing=False)
            streak_start = streak_end = streak_min_rate = None

        rate = interval.rate_per_hour
        meets = rate > rate_threshold_per_hour if strict else rate >= rate_threshold_per_hour
        if meets:
            if streak_start is None:
                streak_start = interval.start
                streak_min_rate = rate
            streak_end = interval.end
            streak_min_rate = min(streak_min_rate, rate)
        else:
            close_streak(ongoing=False)
            streak_start = streak_end = streak_min_rate = None

        prev_end = interval.end

    if streak_start is not None:
        close_streak(ongoing=True)

    return alerts


def compute_nightly_usage(
    intervals: list[DenseInterval],
    window_start: time = NIGHT_WINDOW_START,
    window_end: time = NIGHT_WINDOW_END,
    min_coverage_fraction: float = NIGHT_MIN_COVERAGE_FRACTION,
) -> list[dict]:
    """Sums flow per calendar night from intervals falling entirely inside the window.

    A night counts as covered only if its dense coverage spans at least
    `min_coverage_fraction` of the window, so a partial night isn't compared
    against a full-window baseline.

    Args:
        intervals: Dense intervals from `build_dense_intervals`.
        window_start: Start of the nightly window (local wall-clock time).
        window_end: End of the nightly window (local wall-clock time).
        min_coverage_fraction: Minimum fraction of the window that must have dense
            coverage for that night to be usable.

    Returns:
        One dict per calendar night present in the data: `{night_date, usage_ccf,
        coverage_fraction, is_covered}`, sorted chronologically.
    """
    window_hours = (datetime.combine(date.min, window_end) - datetime.combine(date.min, window_start)).total_seconds() / 3600

    by_night: dict[date, dict] = defaultdict(lambda: {"usage": 0.0, "covered_hours": 0.0})
    for interval in intervals:
        if interval.start.date() != interval.end.date():
            continue  # window doesn't cross midnight -- a same-night interval must not either
        if interval.start.time() < window_start or interval.end.time() > window_end:
            continue
        bucket = by_night[interval.start.date()]
        bucket["usage"] += interval.delta
        bucket["covered_hours"] += interval.duration_hours

    nights = []
    for night_date in sorted(by_night):
        bucket = by_night[night_date]
        coverage_fraction = min(bucket["covered_hours"] / window_hours, 1.0) if window_hours > 0 else 0.0
        nights.append({
            "night_date": night_date.isoformat(),
            "usage_ccf": round(bucket["usage"], 4),
            "coverage_fraction": round(coverage_fraction, 4),
            "is_covered": coverage_fraction >= min_coverage_fraction,
        })
    return nights


def detect_nighttime_ratio_anomalies(
    nights: list[dict],
    multiplier: float,
    min_prior_nights: int = NIGHT_MIN_PRIOR_NIGHTS,
) -> list[dict]:
    """Flags nights whose usage exceeds `multiplier` times the established baseline.

    Baseline is the median of prior covered nights, excluding the night being
    evaluated; a night is skipped until at least `min_prior_nights` prior covered
    nights are available to establish a baseline.

    Args:
        nights: Output of `compute_nightly_usage`, in chronological order.
        multiplier: Threshold multiplier over baseline (2.0 per the SFPUC doc).
        min_prior_nights: Minimum prior covered nights required before evaluating.

    Returns:
        One alert dict per night whose usage exceeded `multiplier * baseline`.
    """
    alerts = []
    covered = [n for n in nights if n["is_covered"]]
    for i, night in enumerate(covered):
        prior = covered[:i]
        if len(prior) < min_prior_nights:
            continue
        baseline = median(p["usage_ccf"] for p in prior)
        if night["usage_ccf"] > multiplier * baseline:
            alerts.append({
                "rule": "nighttime_ratio",
                "night_date": night["night_date"],
                "usage_ccf": night["usage_ccf"],
                "baseline_ccf": round(baseline, 4),
                "multiplier": multiplier,
                "prior_night_count": len(prior),
            })
    return alerts


def compute_median_interval(values: list[tuple[datetime, float]]) -> float:
    """Computes the typical gap between consecutive readings, used by rule 4 to
    tell an anomalous spike apart from one that's just a wide reading gap.

    Args:
        values: Sorted (date, reading) pairs.

    Returns:
        Median gap in days between consecutive readings; 1.0 if fewer than two values.
    """
    if len(values) < 2:
        return 1.0
    gaps = [(values[i][0] - values[i - 1][0]).days for i in range(1, len(values))]
    return median(gaps) if gaps else 1.0


def detect_historical_deviation(
    readings: list[tuple[datetime, float]],
    baseline_window: timedelta = RULE4_BASELINE_WINDOW,
    trigger_multiplier: float = RULE4_TRIGGER_MULTIPLIER,
    gap_multiplier: float = GAP_MULTIPLIER,
) -> list[dict]:
    """Flags a household whose current average daily use has risen sharply against
    its own rolling baseline.

    Daily rate per period is delta/days, clamped >= 0 so a meter reset doesn't drag
    down other periods' baseline (a non-positive current period still emits no
    alert). Baseline is the average daily rate of prior periods overlapping the
    trailing `baseline_window`; periods with no overlapping history are skipped.

    Args:
        readings: Sorted (timestamp, cumulative_value) pairs for one household `mi`,
            already normalized to CCF-equivalent units by the caller.
        baseline_window: Lookback window for baseline periods (90 days per SFPUC rule).
        trigger_multiplier: Multiplier over baseline that triggers an alert (1.5x).
        gap_multiplier: Multiplier used to annotate `is_gap_induced` on each alert.

    Returns:
        One alert dict per current period whose daily rate reached
        `trigger_multiplier * baseline_rate`, with baseline_rate > 0.
    """
    if len(readings) < 2:
        return []

    med_interval = compute_median_interval(readings)

    periods = []
    for i in range(1, len(readings)):
        t_prev, v_prev = readings[i - 1]
        t_curr, v_curr = readings[i]
        days = (t_curr - t_prev).days
        if days <= 0:
            continue
        periods.append({
            "start": t_prev,
            "end": t_curr,
            "days": days,
            "rate": max(0.0, v_curr - v_prev) / days,
        })

    alerts = []
    for i, period in enumerate(periods):
        window_start = period["start"] - baseline_window
        prior = [p for p in periods[:i] if p["end"] > window_start]
        if not prior:
            continue
        baseline_rate = sum(p["rate"] for p in prior) / len(prior)
        if baseline_rate <= 0 or period["rate"] <= 0:
            continue
        if period["rate"] >= trigger_multiplier * baseline_rate:
            gap_days = (period["end"] - period["start"]).days
            alerts.append({
                "rule": "historical_deviation",
                "current_period_start": period["start"].isoformat(),
                "current_period_end": period["end"].isoformat(),
                "current_daily_rate_units": round(period["rate"], 4),
                "baseline_daily_rate_units": round(baseline_rate, 4),
                "baseline_period_count": len(prior),
                "percent_increase": round((period["rate"] / baseline_rate - 1) * 100, 2),
                "gap_days": gap_days,
                "median_interval_days": round(med_interval, 1),
                "is_gap_induced": gap_days > gap_multiplier * med_interval,
            })
    return alerts


def evaluate_meter_rules(
    readings: list[tuple[datetime, float]],
    *,
    scope: str,
    mi: str | None,
    rule2_duration: timedelta,
    nighttime_multiplier: float,
    break_keys: list | None = None,
) -> dict:
    """Runs rules 1-3 for one normalized meter series and assembles its response block.

    Args:
        readings: Sorted (timestamp, cumulative_value) pairs, already normalized to CCF.
        scope: "main" or "submeter", stamped onto each alert.
        mi: Household/submeter id, or None for the main meter.
        rule2_duration: Volume-threshold duration to use (48h standard, 72h main-meter
            multi-family).
        nighttime_multiplier: Nighttime-ratio multiplier to use (NIGHT_STANDARD_MULTIPLIER).
        break_keys: Optional, one per reading -- e.g. (meter_sn, register). A change
            between consecutive readings breaks continuity like a timing gap would
            (a meter swap). None (default) means no such concept applies.

    Returns:
        `{"has_data", "coverage", "rules": {...}}` block for this meter series.
    """
    span_hours = 0.0
    if len(readings) >= 2:
        span_hours = (readings[-1][0] - readings[0][0]).total_seconds() / 3600

    if break_keys is None:
        intervals = build_dense_intervals(readings)
    else:
        intervals = []
        segment: list[tuple[datetime, float]] = []
        segment_key = None
        for (t, v), key in zip(readings, break_keys):
            if segment and key != segment_key:
                intervals.extend(build_dense_intervals(segment))
                segment = []
            segment.append((t, v))
            segment_key = key
        if segment:
            intervals.extend(build_dense_intervals(segment))

    dense_hours = sum(iv.duration_hours for iv in intervals)

    continuous_flow_alerts = detect_sustained_rate_streaks(
        intervals, RULE1_THRESHOLD_CCF_PER_HOUR, RULE1_MIN_DURATION, "continuous_flow_24h", strict=True,
    )
    volume_threshold_alerts = detect_sustained_rate_streaks(
        intervals, RULE2_THRESHOLD_CCF_PER_HOUR, rule2_duration, "volume_threshold", strict=False,
    )
    nights = compute_nightly_usage(intervals)
    nighttime_alerts = detect_nighttime_ratio_anomalies(nights, nighttime_multiplier)

    for alert in (*continuous_flow_alerts, *volume_threshold_alerts, *nighttime_alerts):
        alert["scope"] = scope
        alert["mi"] = mi

    return {
        "has_data": len(readings) > 0,
        "coverage": {
            "dense_hours": round(dense_hours, 2),
            "span_hours": round(span_hours, 2),
            "reading_count": len(readings),
        },
        "rules": {
            "continuous_flow_24h": {
                "duration_threshold_hours": RULE1_MIN_DURATION.total_seconds() / 3600,
                "alerts": continuous_flow_alerts,
            },
            "volume_threshold": {
                "duration_threshold_hours": rule2_duration.total_seconds() / 3600,
                "alerts": volume_threshold_alerts,
            },
            "nighttime_ratio": {
                "multiplier": nighttime_multiplier,
                "alerts": nighttime_alerts,
            },
        },
    }
