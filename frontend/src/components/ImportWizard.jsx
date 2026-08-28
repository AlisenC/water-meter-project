import { useState, useRef } from "react";
import { api } from "../api";

const FORMAT_OPTIONS = [
  { value: "", label: "Auto-detect" },
  { value: "A", label: "Format A — mi, reading, record_date, unit (comma, YYYY-MM-DD)" },
  { value: "B", label: "Format B — household, meter_value, date (comma, YYYY-MM-DD)" },
  { value: "C", label: "Format C — name, val, dt (tab-delimited, DD/MM/YYYY)" },
];

const REASON_LABELS = {
  missing_reading: "Missing reading",
  invalid_reading: "Invalid reading",
  invalid_date: "Invalid date",
  missing_household: "Missing household",
  invalid_unit: "Invalid unit",
  unknown_unit: "Unknown unit (no existing data for this household)",
  format_error: "Format error",
};

function ErrorTable({ errors }) {
  if (!errors.length) return <p className="text-green-600 text-sm">No errors.</p>;
  return (
    <table className="w-full text-xs border-collapse mt-1">
      <thead>
        <tr className="text-left text-gray-500 border-b">
          <th className="pr-3 py-1">Row</th>
          <th className="pr-3 py-1">Reason</th>
          <th className="py-1">Raw value</th>
        </tr>
      </thead>
      <tbody>
        {errors.map((e, i) => (
          <tr key={i} className="border-b last:border-0">
            <td className="pr-3 py-1 text-gray-500">{e.row_num || "—"}</td>
            <td className="pr-3 py-1 text-red-600">{REASON_LABELS[e.reason] || e.reason}</td>
            <td className="py-1 font-mono text-gray-700 break-all">{e.raw_value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ConflictTable({ conflicts, selected, onToggle, onToggleAll }) {
  if (!conflicts.length) return <p className="text-green-600 text-sm">No conflicts.</p>;
  const resolvable = conflicts.filter((c) => c.existing_id != null);
  const allResolvableSelected = resolvable.length > 0 && resolvable.every((c) => selected?.has(c.existing_id));

  return (
    <table className="w-full text-xs border-collapse mt-1">
      <thead>
        <tr className="text-left text-gray-500 border-b">
          {onToggle && (
            <th className="pr-2 py-1">
              <input
                type="checkbox"
                checked={allResolvableSelected}
                onChange={(e) => onToggleAll?.(e.target.checked)}
                disabled={resolvable.length === 0}
              />
            </th>
          )}
          <th className="pr-3 py-1">Meter</th>
          <th className="pr-3 py-1">Date</th>
          <th className="pr-3 py-1">Existing</th>
          <th className="py-1">Imported</th>
        </tr>
      </thead>
      <tbody>
        {conflicts.map((c, i) => (
          <tr key={i} className="border-b last:border-0">
            {onToggle && (
              <td className="pr-2 py-1">
                <input
                  type="checkbox"
                  checked={c.existing_id != null && !!selected?.has(c.existing_id)}
                  onChange={() => onToggle(c)}
                  disabled={c.existing_id == null}
                  title={c.existing_id == null ? "Both values came from this same import batch — fix the source CSV instead" : undefined}
                />
              </td>
            )}
            <td className="pr-3 py-1 text-gray-700">{c.mi}</td>
            <td className="pr-3 py-1 text-gray-500">{c.record_date}</td>
            <td className="pr-3 py-1 font-mono text-gray-700">{c.existing_reading} (unit {c.existing_unit})</td>
            <td className="py-1 font-mono text-amber-700">{c.new_reading} (unit {c.new_unit})</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function FileCard({ fp }) {
  const [open, setOpen] = useState(false);
  const [conflictsOpen, setConflictsOpen] = useState(false);
  const formatBadge = fp.detected_format === "unknown" ? "Unknown" : `Format ${fp.detected_format}`;

  return (
    <div className="border rounded-lg p-4 bg-white">
      <div className="flex items-start justify-between gap-2 mb-2">
        <span className="font-medium text-sm break-all">{fp.filename}</span>
        <span className="shrink-0 text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">
          {formatBadge}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm text-gray-600 mb-2">
        <span>Total rows: <strong>{fp.total_rows}</strong></span>
        <span>After filters: <strong className="text-green-700">{fp.rows_after_filter}</strong></span>
        <span>Valid: <strong>{fp.valid_rows}</strong></span>
        <span>Errors: <strong className={fp.error_rows ? "text-red-600" : ""}>{fp.error_rows}</strong></span>
        <span>Duplicates: <strong>{fp.duplicate_rows}</strong></span>
        <span>Conflicts: <strong className={fp.conflict_rows ? "text-amber-600" : ""}>{fp.conflict_rows}</strong></span>
        {fp.date_min && (
          <span className="col-span-2 text-xs text-gray-500">
            Date range: {fp.date_min} → {fp.date_max}
          </span>
        )}
      </div>
      {fp.households_after_filter.length > 0 && (
        <p className="text-xs text-gray-500 mb-2">
          Households: {fp.households_after_filter.slice(0, 8).join(", ")}
          {fp.households_after_filter.length > 8 && ` +${fp.households_after_filter.length - 8} more`}
        </p>
      )}
      {fp.errors.length > 0 && (
        <div>
          <button
            onClick={() => setOpen((v) => !v)}
            className="text-xs text-red-600 underline"
          >
            {open ? "Hide" : "Show"} {fp.errors.length} error{fp.errors.length !== 1 ? "s" : ""}
          </button>
          {open && <div className="mt-2"><ErrorTable errors={fp.errors} /></div>}
        </div>
      )}
      {fp.conflicts.length > 0 && (
        <div className="mt-1">
          <button
            onClick={() => setConflictsOpen((v) => !v)}
            className="text-xs text-amber-600 underline"
          >
            {conflictsOpen ? "Hide" : "Show"} {fp.conflicts.length} conflict{fp.conflicts.length !== 1 ? "s" : ""}
          </button>
          {conflictsOpen && <div className="mt-2"><ConflictTable conflicts={fp.conflicts} /></div>}
        </div>
      )}
    </div>
  );
}

export default function ImportWizard({ onImportSuccess, onClose }) {
  const [step, setStep] = useState(0);
  const fileInputRef = useRef(null);
  const [files, setFiles] = useState([]);
  const [dateStart, setDateStart] = useState("");
  const [dateEnd, setDateEnd] = useState("");
  const [excludeInput, setExcludeInput] = useState("");
  const [fmtOverride, setFmtOverride] = useState("");
  const [previewData, setPreviewData] = useState(null);
  const [previewing, setPreviewing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [previewError, setPreviewError] = useState(null);
  const [resultData, setResultData] = useState(null);
  const [showAllErrors, setShowAllErrors] = useState(false);
  const [selectedConflicts, setSelectedConflicts] = useState(new Set());
  const [resolving, setResolving] = useState(false);
  const [resolveError, setResolveError] = useState(null);
  const [resolveResult, setResolveResult] = useState(null);

  function buildFormData() {
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    if (dateStart) fd.append("date_start", dateStart);
    if (dateEnd) fd.append("date_end", dateEnd);
    fd.append("exclude_households", excludeInput);
    if (fmtOverride) fd.append("fmt_override", fmtOverride);
    return fd;
  }

  async function handlePreview() {
    if (!files.length) return;
    setPreviewing(true);
    setPreviewError(null);
    try {
      const res = await api.post("/import-csv/preview", buildFormData());
      setPreviewData(res.data);
      setStep(1);
    } catch (err) {
      setPreviewError(err.response?.data?.detail ?? "Preview failed. Check file format.");
    } finally {
      setPreviewing(false);
    }
  }

  async function handleConfirm() {
    setConfirming(true);
    try {
      const res = await api.post("/import-csv/confirm", buildFormData());
      setResultData(res.data);
      setStep(2);
    } catch (err) {
      setPreviewError(err.response?.data?.detail ?? "Import failed.");
      setConfirming(false);
    }
  }

  function handleImportAnother() {
    setStep(0);
    setFiles([]);
    setDateStart("");
    setDateEnd("");
    setExcludeInput("");
    setFmtOverride("");
    setPreviewData(null);
    setPreviewError(null);
    setResultData(null);
    setShowAllErrors(false);
    setSelectedConflicts(new Set());
    setResolving(false);
    setResolveError(null);
    setResolveResult(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function toggleConflict(conflict) {
    if (conflict.existing_id == null) return;
    setSelectedConflicts((prev) => {
      const next = new Set(prev);
      if (next.has(conflict.existing_id)) next.delete(conflict.existing_id);
      else next.add(conflict.existing_id);
      return next;
    });
  }

  function toggleAllConflicts(checked) {
    const resolvableIds = (resultData?.conflict_rows ?? [])
      .filter((c) => c.existing_id != null)
      .map((c) => c.existing_id);
    setSelectedConflicts(checked ? new Set(resolvableIds) : new Set());
  }

  async function handleResolveConflicts(idsToResolve) {
    const conflictsById = new Map(
      (resultData?.conflict_rows ?? [])
        .filter((c) => c.existing_id != null)
        .map((c) => [c.existing_id, c])
    );
    const resolutions = idsToResolve
      .map((id) => conflictsById.get(id))
      .filter(Boolean)
      .map((c) => ({ id: c.existing_id, reading: c.new_reading, unit: c.new_unit }));
    if (!resolutions.length) return;

    setResolving(true);
    setResolveError(null);
    try {
      const res = await api.post("/readings/resolve-conflicts", { resolutions });
      setResolveResult(res.data);
      const resolvedIds = new Set(resolutions.map((r) => r.id));
      setResultData((prev) => {
        const remaining = prev.conflict_rows.filter((c) => !resolvedIds.has(c.existing_id));
        return { ...prev, conflict_rows: remaining, conflicts: remaining.length };
      });
      setSelectedConflicts(new Set());
    } catch (err) {
      setResolveError(err.response?.data?.detail ?? "Resolving conflicts failed.");
    } finally {
      setResolving(false);
    }
  }

  const activeFilters = [];
  if (dateStart || dateEnd) {
    activeFilters.push(`Date: ${dateStart || "any"} → ${dateEnd || "any"}`);
  }
  const exclusions = excludeInput.split(",").map((h) => h.trim()).filter(Boolean);
  if (exclusions.length) {
    activeFilters.push(`Excluding: ${exclusions.join(", ")}`);
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto m-4">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <div>
            <h2 className="text-lg font-semibold">Import CSV Data</h2>
            <div className="flex gap-2 mt-1">
              {["Configure", "Preview", "Result"].map((label, i) => (
                <span
                  key={i}
                  className={`text-xs px-2 py-0.5 rounded-full ${
                    step === i
                      ? "bg-green-500 text-white"
                      : step > i
                      ? "bg-green-100 text-green-700"
                      : "bg-gray-100 text-gray-400"
                  }`}
                >
                  {label}
                </span>
              ))}
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
        </div>

        <div className="px-6 py-5">
          {/* Step 0: Configure */}
          {step === 0 && (
            <div className="space-y-5">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  CSV files <span className="text-gray-400 font-normal">(select one or more)</span>
                </label>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv"
                  multiple
                  className="block w-full text-sm text-gray-600 file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:bg-green-50 file:text-green-700 hover:file:bg-green-100"
                  onChange={(e) => setFiles(Array.from(e.target.files))}
                />
                {files.length > 0 && (
                  <p className="text-xs text-gray-500 mt-1">{files.length} file{files.length !== 1 ? "s" : ""} selected</p>
                )}
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Start date (inclusive)</label>
                  <input
                    type="date"
                    value={dateStart}
                    onChange={(e) => setDateStart(e.target.value)}
                    className="w-full border rounded px-3 py-1.5 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">End date (inclusive)</label>
                  <input
                    type="date"
                    value={dateEnd}
                    onChange={(e) => setDateEnd(e.target.value)}
                    className="w-full border rounded px-3 py-1.5 text-sm"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Exclude households <span className="text-gray-400 font-normal">(comma-separated)</span>
                </label>
                <input
                  type="text"
                  value={excludeInput}
                  onChange={(e) => setExcludeInput(e.target.value)}
                  placeholder="Unit 3A, Unit 5B"
                  className="w-full border rounded px-3 py-1.5 text-sm"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Format</label>
                <select
                  value={fmtOverride}
                  onChange={(e) => setFmtOverride(e.target.value)}
                  className="w-full border rounded px-3 py-1.5 text-sm"
                >
                  {FORMAT_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>

              {previewError && (
                <p className="text-red-600 text-sm">{previewError}</p>
              )}

              <div className="flex justify-end">
                <button
                  onClick={handlePreview}
                  disabled={!files.length || previewing}
                  className="bg-green-500 hover:bg-green-600 disabled:opacity-50 text-white px-5 py-2 rounded text-sm font-medium"
                >
                  {previewing ? "Previewing…" : "Preview Import"}
                </button>
              </div>
            </div>
          )}

          {/* Step 1: Preview */}
          {step === 1 && previewData && (
            <div className="space-y-4">
              {/* Summary bar */}
              <div className="flex flex-wrap gap-4 bg-gray-50 rounded-lg px-4 py-3 text-sm">
                <span><strong>{previewData.files.length}</strong> file{previewData.files.length !== 1 ? "s" : ""}</span>
                <span className="text-green-700"><strong>{previewData.total_rows_to_import}</strong> rows to import</span>
                {previewData.total_errors > 0 && (
                  <span className="text-red-600"><strong>{previewData.total_errors}</strong> error{previewData.total_errors !== 1 ? "s" : ""}</span>
                )}
                {previewData.total_duplicates > 0 && (
                  <span className="text-gray-500"><strong>{previewData.total_duplicates}</strong> duplicate{previewData.total_duplicates !== 1 ? "s" : ""}</span>
                )}
                {previewData.total_conflicts > 0 && (
                  <span className="text-amber-600"><strong>{previewData.total_conflicts}</strong> conflict{previewData.total_conflicts !== 1 ? "s" : ""}</span>
                )}
              </div>

              {/* Active filters */}
              {activeFilters.length > 0 && (
                <div className="text-xs text-gray-500 bg-blue-50 rounded px-3 py-2">
                  Filters applied: {activeFilters.join(" · ")}
                </div>
              )}

              {/* Format error banner */}
              {previewData.files.some((fp) => fp.detected_format === "unknown") && (
                <div className="bg-red-50 border border-red-200 rounded px-3 py-2 text-sm text-red-700">
                  <strong>Format not recognised</strong> for{" "}
                  {previewData.files.filter((fp) => fp.detected_format === "unknown").map((fp) => fp.filename).join(", ")}.
                  {" "}Expected columns: <span className="font-mono">mi, reading, record_date, unit</span> (Format A) or{" "}
                  <span className="font-mono">household, meter_value, date</span> (Format B) or{" "}
                  tab-delimited <span className="font-mono">name, val, dt</span> (Format C).
                  Go back and select the correct format.
                </div>
              )}

              {/* Per-file cards */}
              <div className="space-y-3">
                {previewData.files.map((fp, i) => <FileCard key={i} fp={fp} />)}
              </div>

              {previewData.total_rows_to_import === 0 && previewData.files.every((fp) => fp.detected_format !== "unknown") && (
                <p className="text-amber-600 text-sm bg-amber-50 rounded px-3 py-2">
                  No rows would be imported with the current filters. Go back and adjust your settings.
                </p>
              )}

              {previewError && (
                <p className="text-red-600 text-sm">{previewError}</p>
              )}

              <div className="flex justify-between pt-2">
                <button
                  onClick={() => { setStep(0); setPreviewError(null); }}
                  className="border border-gray-300 hover:bg-gray-50 text-gray-700 px-4 py-2 rounded text-sm"
                >
                  Back
                </button>
                <button
                  onClick={handleConfirm}
                  disabled={previewData.total_rows_to_import === 0 || confirming}
                  className="bg-green-500 hover:bg-green-600 disabled:opacity-50 text-white px-5 py-2 rounded text-sm font-medium"
                >
                  {confirming ? "Importing…" : "Confirm Import"}
                </button>
              </div>
            </div>
          )}

          {/* Step 2: Result */}
          {step === 2 && resultData && (
            <div className="space-y-4">
              <div className="bg-green-50 border border-green-200 rounded-lg px-4 py-3">
                <p className="text-green-800 font-medium">Import complete</p>
                <p className="text-green-700 text-sm mt-0.5">
                  {resultData.inserted} row{resultData.inserted !== 1 ? "s" : ""} inserted
                  {resultData.skipped > 0 && `, ${resultData.skipped} skipped`}
                  {resultData.duplicates > 0 && ` (${resultData.duplicates} duplicate${resultData.duplicates !== 1 ? "s" : ""})`}
                  {resultData.conflicts > 0 && `, ${resultData.conflicts} conflict${resultData.conflicts !== 1 ? "s" : ""}`}
                </p>
              </div>

              {/* Per-file breakdown */}
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="text-left text-gray-500 border-b text-xs">
                    <th className="py-1.5 pr-4">File</th>
                    <th className="py-1.5 pr-4">Inserted</th>
                    <th className="py-1.5 pr-4">Skipped</th>
                    <th className="py-1.5 pr-4">Duplicates</th>
                    <th className="py-1.5">Conflicts</th>
                  </tr>
                </thead>
                <tbody>
                  {resultData.per_file.map((pf, i) => (
                    <tr key={i} className="border-b last:border-0">
                      <td className="py-1.5 pr-4 text-gray-700 break-all">{pf.filename}</td>
                      <td className="py-1.5 pr-4 text-green-700 font-medium">{pf.inserted}</td>
                      <td className="py-1.5 pr-4 text-gray-500">{pf.skipped}</td>
                      <td className="py-1.5 pr-4 text-gray-500">{pf.duplicates}</td>
                      <td className="py-1.5 text-amber-600">{pf.conflicts}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {resultData.errors.length > 0 && (
                <div>
                  <button
                    onClick={() => setShowAllErrors((v) => !v)}
                    className="text-xs text-red-600 underline"
                  >
                    {showAllErrors ? "Hide" : "Show"} {resultData.errors.length} error{resultData.errors.length !== 1 ? "s" : ""}
                  </button>
                  {showAllErrors && <div className="mt-2"><ErrorTable errors={resultData.errors} /></div>}
                </div>
              )}

              {resultData.conflict_rows?.length > 0 && (
                <div className="border border-amber-200 bg-amber-50 rounded-lg p-3">
                  <p className="text-amber-800 font-medium text-sm mb-1">
                    {resultData.conflict_rows.length} conflict{resultData.conflict_rows.length !== 1 ? "s" : ""} need review
                  </p>
                  <p className="text-amber-700 text-xs mb-2">
                    These rows weren't imported because a reading already exists for the same meter and date with a
                    different value. Select the ones where the imported value should replace what's stored, then apply.
                  </p>
                  <ConflictTable
                    conflicts={resultData.conflict_rows}
                    selected={selectedConflicts}
                    onToggle={toggleConflict}
                    onToggleAll={toggleAllConflicts}
                  />
                  {resolveError && <p className="text-red-600 text-xs mt-2">{resolveError}</p>}
                  {resolveResult && (
                    <p className="text-green-700 text-xs mt-2">{resolveResult.updated} conflict{resolveResult.updated !== 1 ? "s" : ""} resolved.</p>
                  )}
                  <div className="flex gap-2 mt-2">
                    <button
                      onClick={() => handleResolveConflicts(
                        resultData.conflict_rows.filter((c) => c.existing_id != null).map((c) => c.existing_id)
                      )}
                      disabled={resolving || !resultData.conflict_rows.some((c) => c.existing_id != null)}
                      className="border border-amber-400 text-amber-700 hover:bg-amber-100 disabled:opacity-50 px-3 py-1.5 rounded text-xs font-medium"
                    >
                      {resolving ? "Replacing…" : "Replace all with imported value"}
                    </button>
                    <button
                      onClick={() => handleResolveConflicts([...selectedConflicts])}
                      disabled={resolving || selectedConflicts.size === 0}
                      className="bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white px-3 py-1.5 rounded text-xs font-medium"
                    >
                      {resolving ? "Replacing…" : `Replace selected (${selectedConflicts.size})`}
                    </button>
                  </div>
                </div>
              )}

              <div className="flex justify-between pt-2">
                <button
                  onClick={handleImportAnother}
                  className="border border-gray-300 hover:bg-gray-50 text-gray-700 px-4 py-2 rounded text-sm"
                >
                  Import Another
                </button>
                <button
                  onClick={() => { onImportSuccess(resultData); }}
                  className="bg-green-500 hover:bg-green-600 text-white px-5 py-2 rounded text-sm font-medium"
                >
                  Done
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
