import { useState, useRef } from "react";
import { api } from "../api";

export default function LeakCsvImport({ title, hint, previewUrl, confirmUrl, onImported }) {
  const fileInputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [previewData, setPreviewData] = useState(null);
  const [previewing, setPreviewing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState(null);

  function reset() {
    setFile(null);
    setPreviewData(null);
    setError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function handlePreview() {
    if (!file) return;
    setPreviewing(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await api.post(previewUrl, fd);
      setPreviewData(res.data);
    } catch (err) {
      setError(err.response?.data?.detail ?? "Preview failed. Check the file format.");
      setPreviewData(null);
    } finally {
      setPreviewing(false);
    }
  }

  async function handleConfirm() {
    setConfirming(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await api.post(confirmUrl, fd);
      reset();
      onImported(res.data);
    } catch (err) {
      setError(err.response?.data?.detail ?? "Import failed.");
    } finally {
      setConfirming(false);
    }
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4 space-y-3">
      <div>
        <h3 className="text-sm font-semibold text-gray-700">{title}</h3>
        {hint && <p className="text-xs text-gray-400 mt-0.5">{hint}</p>}
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept=".csv"
        className="block w-full text-sm text-gray-600 file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
        onChange={(e) => { setFile(e.target.files[0] ?? null); setPreviewData(null); setError(null); }}
      />

      {error && <p className="text-red-600 text-sm">{error}</p>}

      {previewData && (
        <div className="bg-gray-50 rounded-lg px-3 py-2 text-sm space-y-1">
          <div className="flex flex-wrap gap-3">
            <span className="text-green-700"><strong>{previewData.valid_rows}</strong> valid row{previewData.valid_rows !== 1 ? "s" : ""}</span>
            {previewData.error_rows > 0 && (
              <span className="text-red-600"><strong>{previewData.error_rows}</strong> error{previewData.error_rows !== 1 ? "s" : ""}</span>
            )}
            {previewData.date_min && (
              <span className="text-gray-500">{previewData.date_min} → {previewData.date_max}</span>
            )}
          </div>
          {previewData.errors?.length > 0 && (
            <ul className="text-xs text-red-600 list-disc list-inside">
              {previewData.errors.slice(0, 5).map((e, i) => (
                <li key={i}>Row {e.row_num}: {e.reason} ({e.raw_value})</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="flex gap-2">
        {!previewData ? (
          <button
            onClick={handlePreview}
            disabled={!file || previewing}
            className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            {previewing ? "Previewing…" : "Preview"}
          </button>
        ) : (
          <>
            <button
              onClick={reset}
              className="border border-gray-300 hover:bg-gray-50 text-gray-700 px-4 py-2 rounded-lg text-sm"
            >
              Cancel
            </button>
            <button
              onClick={handleConfirm}
              disabled={previewData.valid_rows === 0 || confirming}
              className="bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              {confirming ? "Importing…" : "Confirm Import"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
