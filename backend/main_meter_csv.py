import csv
from datetime import datetime
from io import StringIO

REQUIRED_COLS = {
    "account_id", "meter_id", "meter_sn", "read_time", "timezone", "read",
    "read_unit", "read_method", "flow_time", "flow_unit", "flow", "register",
}


def parse_main_meter_csv_bytes(file_bytes: bytes, filename: str) -> tuple[list[dict], list[dict]]:
    """Parses an AMI 'range export' main-meter CSV (Account_ID, Meter_ID, Meter_SN,
    Read_Time, Timezone, Read, Read_Unit, Read_Method, Flow_Time, Flow_Unit, Flow, Register).
    Returns (valid_rows, error_rows).
    """
    text = file_bytes.decode("utf-8-sig")
    reader = csv.DictReader(StringIO(text), delimiter=",")

    headers = {h.strip().lower() for h in (reader.fieldnames or [])}
    if not REQUIRED_COLS.issubset(headers):
        raise ValueError(
            f"Could not detect main-meter CSV format for '{filename}'. "
            f"Expected columns: {sorted(REQUIRED_COLS)}"
        )

    valid_rows: list[dict] = []
    error_rows: list[dict] = []

    for row_num, raw_row in enumerate(reader, start=1):
        row = {k.strip().lower(): (v or "").strip() for k, v in raw_row.items()}

        try:
            read_time = datetime.strptime(row["read_time"], "%Y-%m-%d %H:%M")
        except ValueError:
            error_rows.append({"row_num": row_num, "reason": "invalid_read_time", "raw_value": row["read_time"], "filename": filename})
            continue

        if row["read_unit"].upper() != "CCF":
            error_rows.append({"row_num": row_num, "reason": "unsupported_read_unit", "raw_value": row["read_unit"], "filename": filename})
            continue

        try:
            read_value = float(row["read"])
        except ValueError:
            error_rows.append({"row_num": row_num, "reason": "invalid_read", "raw_value": row["read"], "filename": filename})
            continue

        flow_time = None
        if row["flow_time"]:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    flow_time = datetime.strptime(row["flow_time"], fmt)
                    break
                except ValueError:
                    continue
            if flow_time is None:
                error_rows.append({"row_num": row_num, "reason": "invalid_flow_time", "raw_value": row["flow_time"], "filename": filename})
                continue

        flow_value = None
        if row["flow"]:
            if row["flow_unit"].upper() != "CCF":
                error_rows.append({"row_num": row_num, "reason": "unsupported_flow_unit", "raw_value": row["flow_unit"], "filename": filename})
                continue
            try:
                flow_value = float(row["flow"])
            except ValueError:
                error_rows.append({"row_num": row_num, "reason": "invalid_flow", "raw_value": row["flow"], "filename": filename})
                continue

        valid_rows.append({
            "account_id": row["account_id"] or None,
            "meter_id": row["meter_id"] or None,
            "meter_sn": row["meter_sn"] or None,
            "read_time": read_time,
            "read_value": read_value,
            "flow_time": flow_time,
            "flow_value": flow_value,
            "register": row["register"] or None,
        })

    return valid_rows, error_rows
