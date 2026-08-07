// A statement/household-sum pair within this many units of water is considered "matching".
// ~748 gallons — recalibrated from the old kL-scale tolerance to the units-of-water scale.
export const DISCREPANCY_TOLERANCE_UNITS = 1.0;

export function monthLabel(year, month) {
  return new Date(year, month - 1, 1).toLocaleDateString("en-AU", {
    month: "short",
    year: "numeric",
  });
}

export function exportCSV(rows, filename) {
  if (!rows.length) return;
  const headers = Object.keys(rows[0]).join(",");
  const lines = rows.map((r) =>
    Object.values(r)
      .map((v) => (typeof v === "string" && v.includes(",") ? `"${v}"` : v ?? ""))
      .join(",")
  );
  const blob = new Blob([[headers, ...lines].join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
