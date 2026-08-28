import csv
from datetime import date, datetime
from io import StringIO

FORMATS = {
    "A": {
        "required_cols": {"mi", "reading", "record_date", "unit"},
        "delimiter": ",",
        "col_map": {"mi": "mi", "reading": "reading", "record_date": "record_date", "unit": "unit"},
        "date_fmt": "%Y-%m-%d",
        "has_unit_col": True,
    },
    "B": {
        "required_cols": {"household", "meter_value", "date"},
        "delimiter": ",",
        "col_map": {"household": "mi", "meter_value": "reading", "date": "record_date"},
        "date_fmt": "%Y-%m-%d",
        "has_unit_col": False,
    },
    "C": {
        "required_cols": {"name", "val", "dt"},
        "delimiter": "\t",
        "col_map": {"name": "mi", "val": "reading", "dt": "record_date"},
        "date_fmt": "%d/%m/%Y",
        "has_unit_col": False,
    },
}


def detect_format(headers: set[str]) -> str | None:
    """Matches a CSV's header row against the known FORMATS signatures.

    Args:
        headers: Raw header strings from the CSV's first row.

    Returns:
        The matching format key ("A", "B", or "C"), or None if no format's
        required_cols is a subset of the (case/whitespace-normalised) headers.
    """
    normalised = {h.strip().lower() for h in headers}
    for key, fmt in FORMATS.items():
        if fmt["required_cols"].issubset(normalised):
            return key
    return None


def parse_csv_bytes(
    file_bytes: bytes,
    filename: str,
    existing_units: dict[str, int],
    fmt_override: str | None = None,
    parse_datetime: bool = False,
) -> tuple[str, list[dict], list[dict]]:
    """Parses a reading CSV into valid and error rows, auto-detecting its format.

    Args:
        file_bytes: Raw uploaded file content.
        filename: Original filename, used only to label error rows.
        existing_units: mi -> unit, used to resolve unit for formats (B, C) that
            don't carry their own unit column.
        fmt_override: Force a specific format ("A", "B", "C") instead of sniffing
            headers against FORMATS.
        parse_datetime: If True, record_date must carry an explicit "YYYY-MM-DD
            HH:MM:SS" timestamp rather than a bare date, which is rejected as
            "missing_timestamp" instead of being silently defaulted to midnight.
            Used by leak detection's submeter imports, which need sub-day
            granularity to line up submeter readings against each other.

    Returns:
        A (fmt_key, valid_rows, error_rows) tuple. Each valid row is
        {"row_num", "mi", "reading", "record_date", "unit"}; each error row is
        {"row_num", "reason", "raw_value", "filename"}.

    Raises:
        ValueError: No format's required_cols matched the CSV's header row.
    """
    text = file_bytes.decode("utf-8-sig")

    # Detect format by sniffing headers with each delimiter
    fmt_key = None
    if fmt_override and fmt_override in FORMATS:
        fmt_key = fmt_override
    else:
        for key, fmt in FORMATS.items():
            reader = csv.DictReader(StringIO(text), delimiter=fmt["delimiter"])
            headers = {h.strip().lower() for h in (reader.fieldnames or [])}
            if fmt["required_cols"].issubset(headers):
                fmt_key = key
                break

    if fmt_key is None:
        signatures = ", ".join(
            f"Format {k}: {sorted(v['required_cols'])}" for k, v in FORMATS.items()
        )
        raise ValueError(
            f"Could not detect CSV format for '{filename}'. "
            f"Expected one of: {signatures}"
        )

    fmt = FORMATS[fmt_key]
    reader = csv.DictReader(StringIO(text), delimiter=fmt["delimiter"])

    # Build a normalised column name → original header map
    header_map = {}
    for h in (reader.fieldnames or []):
        header_map[h.strip().lower()] = h

    valid_rows: list[dict] = []
    error_rows: list[dict] = []

    for row_num, raw_row in enumerate(reader, start=1):
        # Normalise keys
        row = {k.strip().lower(): v for k, v in raw_row.items()}

        # Map columns to canonical names
        mapped: dict = {}
        for src_col, dst_col in fmt["col_map"].items():
            mapped[dst_col] = row.get(src_col, "").strip()

        # Validate reading
        raw_reading = mapped.get("reading", "")
        if not raw_reading:
            error_rows.append({"row_num": row_num, "reason": "missing_reading", "raw_value": raw_reading, "filename": filename})
            continue
        try:
            reading_val = float(raw_reading)
        except ValueError:
            error_rows.append({"row_num": row_num, "reason": "invalid_reading", "raw_value": raw_reading, "filename": filename})
            continue

        raw_date = mapped.get("record_date", "")
        if parse_datetime and fmt["date_fmt"] == "%Y-%m-%d":
            if len(raw_date.strip()) <= 10:
                error_rows.append({"row_num": row_num, "reason": "missing_timestamp", "raw_value": raw_date, "filename": filename})
                continue
            try:
                parsed_date = datetime.fromisoformat(raw_date)
            except (ValueError, AttributeError):
                error_rows.append({"row_num": row_num, "reason": "invalid_date", "raw_value": raw_date, "filename": filename})
                continue
        else:
            try:
                parsed_date = date.fromisoformat(raw_date) if fmt["date_fmt"] == "%Y-%m-%d" else _strpdate(raw_date, fmt["date_fmt"])
            except (ValueError, AttributeError):
                error_rows.append({"row_num": row_num, "reason": "invalid_date", "raw_value": raw_date, "filename": filename})
                continue

        mi = mapped.get("mi", "")
        if not mi:
            error_rows.append({"row_num": row_num, "reason": "missing_household", "raw_value": "", "filename": filename})
            continue

        # Resolve unit
        if fmt["has_unit_col"]:
            raw_unit = row.get("unit", "").strip()
            try:
                unit_val = int(raw_unit)
            except (ValueError, TypeError):
                error_rows.append({"row_num": row_num, "reason": "invalid_unit", "raw_value": raw_unit, "filename": filename})
                continue
        else:
            # Look up unit from existing data for this household
            if mi in existing_units:
                unit_val = existing_units[mi]
            else:
                error_rows.append({"row_num": row_num, "reason": "unknown_unit", "raw_value": mi, "filename": filename})
                continue

        valid_rows.append({
            "row_num": row_num,
            "mi": mi,
            "reading": reading_val,
            "record_date": parsed_date,
            "unit": unit_val,
        })

    return fmt_key, valid_rows, error_rows


def apply_filters(
    rows: list[dict],
    date_start: date | None,
    date_end: date | None,
    exclude_households: list[str],
    existing_keys: dict[tuple[str, date], dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Filters rows by date range and excluded households, then classifies the rest
    as duplicate/conflict against existing_keys.

    Args:
        rows: Parsed CSV rows to filter.
        date_start: Earliest record_date to include, or None for no lower bound.
        date_end: Latest record_date to include, or None for no upper bound.
        exclude_households: mi values to exclude regardless of date.
        existing_keys: Maps (mi, record_date) -> {"id", "reading", "unit"} for rows
            already known, whether from the DB or accepted earlier in this call. If
            passed, it is mutated in place as rows are accepted — reuse the same
            dict across multiple calls (e.g. one per file in a batch) to also catch
            cross-file duplicates. Rows added mid-batch carry "id": None.

    Returns:
        A (included, excluded) tuple. Excluded rows carry a "filter_reason" of
        "date_range", "excluded_household", "duplicate", or "conflict"; conflict
        rows additionally carry "existing_id"/"existing_reading"/"existing_unit".
    """
    included = []
    excluded = []
    exclude_set = {h.strip() for h in exclude_households if h.strip()}
    keys = existing_keys if existing_keys is not None else {}

    for row in rows:
        rd = row["record_date"]
        if date_start and rd < date_start:
            excluded.append({**row, "filter_reason": "date_range"})
            continue
        if date_end and rd > date_end:
            excluded.append({**row, "filter_reason": "date_range"})
            continue
        if row["mi"] in exclude_set:
            excluded.append({**row, "filter_reason": "excluded_household"})
            continue

        key = (row["mi"], rd)
        existing = keys.get(key)
        if existing is not None:
            if existing["reading"] == row["reading"] and existing["unit"] == row["unit"]:
                excluded.append({**row, "filter_reason": "duplicate"})
            else:
                excluded.append({
                    **row,
                    "filter_reason": "conflict",
                    "existing_id": existing["id"],
                    "existing_reading": existing["reading"],
                    "existing_unit": existing["unit"],
                })
            continue

        included.append(row)
        keys[key] = {"id": None, "reading": row["reading"], "unit": row["unit"]}

    return included, excluded


def _strpdate(value: str, fmt: str) -> date:
    from datetime import datetime
    return datetime.strptime(value, fmt).date()
