from datetime import date, datetime

from backend.csv_parser import apply_filters, detect_format, parse_csv_bytes


def test_detect_format_a():
    assert detect_format({"mi", "reading", "record_date", "unit"}) == "A"


def test_detect_format_b():
    assert detect_format({"household", "meter_value", "date"}) == "B"


def test_detect_format_c():
    assert detect_format({"name", "val", "dt"}) == "C"


def test_detect_format_unrecognized_returns_none():
    assert detect_format({"foo", "bar"}) is None


def test_detect_format_is_case_and_whitespace_insensitive():
    assert detect_format({" MI", "Reading", "RECORD_DATE", "unit "}) == "A"


def test_parse_csv_bytes_format_a_valid_rows():
    csv_text = (
        "mi,reading,record_date,unit\n"
        "H1,100.5,2024-01-01,1\n"
        "H2,50,2024-01-02,0\n"
    )
    fmt_key, valid_rows, error_rows = parse_csv_bytes(csv_text.encode(), "a.csv", {})

    assert fmt_key == "A"
    assert error_rows == []
    assert len(valid_rows) == 2
    assert valid_rows[0] == {
        "row_num": 1,
        "mi": "H1",
        "reading": 100.5,
        "record_date": date(2024, 1, 1),
        "unit": 1,
    }
    assert valid_rows[1]["unit"] == 0


def test_parse_csv_bytes_format_a_error_rows():
    csv_text = (
        "mi,reading,record_date,unit\n"
        "H1,,2024-01-01,1\n"
        "H2,abc,2024-01-02,1\n"
        "H3,10,2024-01-03,1\n"
        ",10,2024-01-04,1\n"
        "H5,10,not-a-date,1\n"
        "H6,10,2024-01-05,notanint\n"
    )
    fmt_key, valid_rows, error_rows = parse_csv_bytes(csv_text.encode(), "a.csv", {})

    assert fmt_key == "A"
    assert len(valid_rows) == 1
    assert valid_rows[0]["mi"] == "H3"

    reasons_by_row = {row["row_num"]: row["reason"] for row in error_rows}
    assert reasons_by_row == {
        1: "missing_reading",
        2: "invalid_reading",
        4: "missing_household",
        5: "invalid_date",
        6: "invalid_unit",
    }


def test_parse_csv_bytes_format_b_resolves_unit_from_existing_data():
    csv_text = "household,meter_value,date\nH1,100,2024-01-01\nH2,50,2024-01-02\n"

    fmt_key, valid_rows, error_rows = parse_csv_bytes(
        csv_text.encode(), "b.csv", existing_units={"H1": 1}
    )

    assert fmt_key == "B"
    assert len(valid_rows) == 1
    assert valid_rows[0] == {
        "row_num": 1,
        "mi": "H1",
        "reading": 100.0,
        "record_date": date(2024, 1, 1),
        "unit": 1,
    }
    assert len(error_rows) == 1
    assert error_rows[0]["reason"] == "unknown_unit"
    assert error_rows[0]["raw_value"] == "H2"


def test_parse_csv_bytes_format_c_tab_delimited_with_dmy_dates():
    csv_text = "name\tval\tdt\nH1\t100\t31/01/2024\n"

    fmt_key, valid_rows, error_rows = parse_csv_bytes(
        csv_text.encode(), "c.csv", existing_units={"H1": 0}
    )

    assert fmt_key == "C"
    assert error_rows == []
    assert valid_rows[0]["record_date"] == date(2024, 1, 31)
    assert valid_rows[0]["unit"] == 0


def test_parse_csv_bytes_parse_datetime_requires_explicit_timestamp():
    csv_text = (
        "mi,reading,record_date,unit\n"
        "H1,100,2024-01-01,1\n"
        "H2,100,2024-01-01 08:30:00,1\n"
    )

    fmt_key, valid_rows, error_rows = parse_csv_bytes(
        csv_text.encode(), "a.csv", {}, parse_datetime=True
    )

    assert fmt_key == "A"
    assert len(error_rows) == 1
    assert error_rows[0] == {
        "row_num": 1,
        "reason": "missing_timestamp",
        "raw_value": "2024-01-01",
        "filename": "a.csv",
    }
    assert len(valid_rows) == 1
    assert valid_rows[0]["record_date"] == datetime(2024, 1, 1, 8, 30, 0)


def test_apply_filters_date_range_and_excluded_households():
    rows = [
        {"mi": "H1", "record_date": date(2024, 1, 1)},
        {"mi": "H2", "record_date": date(2024, 1, 10)},
        {"mi": "H3", "record_date": date(2024, 1, 12)},
        {"mi": "H4", "record_date": date(2024, 1, 25)},
    ]

    included, excluded = apply_filters(
        rows,
        date_start=date(2024, 1, 5),
        date_end=date(2024, 1, 20),
        exclude_households=["H3"],
    )

    assert [row["mi"] for row in included] == ["H2"]
    excluded_by_mi = {row["mi"]: row["filter_reason"] for row in excluded}
    assert excluded_by_mi == {
        "H1": "date_range",
        "H3": "excluded_household",
        "H4": "date_range",
    }


def test_apply_filters_no_filters_includes_everything():
    rows = [{"mi": "H1", "record_date": date(2024, 1, 1)}]

    included, excluded = apply_filters(rows, date_start=None, date_end=None, exclude_households=[])

    assert included == rows
    assert excluded == []
