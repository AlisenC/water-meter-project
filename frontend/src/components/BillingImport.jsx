import { useState } from "react";
import { api } from "../api";

function monthLabel(year, month) {
  return new Date(year, month - 1, 1).toLocaleDateString("en-AU", {
    month: "short",
    year: "numeric",
  });
}

export default function BillingImport({
  billingStatements,
  verificationData,
  apiKey,
  apiProvider,
  onImportSuccess,
  onDelete,
}) {
  const [pdfFile, setPdfFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [uploadError, setUploadError] = useState(null);

  async function handleUpload() {
    if (!pdfFile) return;
    if (!apiKey) {
      setUploadError("No API key configured. Add your key in the API Settings panel above.");
      return;
    }

    setUploading(true);
    setUploadResult(null);
    setUploadError(null);

    const formData = new FormData();
    formData.append("file", pdfFile);

    try {
      const res = await api.post("/import-billing", formData, {
        headers: {
          "X-Api-Key": apiKey,
          "X-Api-Provider": apiProvider,
        },
      });
      setUploadResult(res.data);
      setPdfFile(null);
      onImportSuccess();
    } catch (err) {
      setUploadError(err.response?.data?.detail ?? "Upload failed. Check the PDF format.");
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(id) {
    if (!window.confirm("Delete this billing statement?")) return;
    try {
      await api.delete(`/billing-statements/${id}`);
      onDelete(id);
    } catch (err) {
      alert("Delete failed: " + (err.response?.data?.detail ?? err.message));
    }
  }

  return (
    <div className="mb-6 border rounded-md overflow-hidden">
      <div className="px-4 py-2 bg-indigo-50 border-b">
        <h2 className="text-base font-semibold text-indigo-800">Billing Statements</h2>
      </div>

      {/* Upload row */}
      <div className="p-4 flex flex-wrap gap-2 items-center border-b bg-white">
        <input
          type="file"
          accept=".pdf,application/pdf"
          onChange={(e) => {
            setPdfFile(e.target.files[0]);
            setUploadResult(null);
            setUploadError(null);
          }}
          className="text-sm"
        />
        <button
          onClick={handleUpload}
          disabled={!pdfFile || uploading}
          className="bg-indigo-600 text-white px-4 py-1.5 text-sm rounded disabled:opacity-50"
        >
          {uploading ? "Scanning…" : "Import PDF Bill"}
        </button>
        {uploadResult && (
          <span className="text-green-700 text-sm">
            Imported: {monthLabel(uploadResult.billing_year, uploadResult.billing_month)}
            {" — "}
            {uploadResult.total_consumption_kl.toFixed(3)} kL, ${uploadResult.billing_cost_aud.toFixed(2)} AUD
          </span>
        )}
        {uploadError && (
          <span className="text-red-600 text-sm">{uploadError}</span>
        )}
      </div>

      {/* Statements table */}
      {billingStatements.length === 0 ? (
        <p className="p-4 text-gray-400 text-sm italic">No billing statements imported yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="text-left text-gray-500 border-b bg-gray-50 text-xs uppercase tracking-wide">
                <th className="px-3 py-2">Period</th>
                <th className="px-3 py-2">Consumption (kL)</th>
                <th className="px-3 py-2">Cost (AUD)</th>
                <th className="px-3 py-2">Household Sum (kL)</th>
                <th className="px-3 py-2">Discrepancy</th>
                <th className="px-3 py-2">File</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {billingStatements.map((s) => {
                const v = verificationData.find((vd) => vd.billing_statement_id === s.id);
                const discrepancy = v?.discrepancy_kl;
                const discrepancyClass =
                  !v || !v.has_sufficient_readings
                    ? "text-gray-400 italic"
                    : Math.abs(discrepancy) < 0.5
                    ? "text-green-700"
                    : "text-orange-700 font-semibold";

                const sameMonth =
                  !s.period_end_month ||
                  (s.period_end_month === s.billing_month &&
                    s.period_end_year === s.billing_year);

                const periodLabel = sameMonth
                  ? monthLabel(s.billing_year, s.billing_month)
                  : `${monthLabel(s.billing_year, s.billing_month)} – ${monthLabel(s.period_end_year, s.period_end_month)}`;

                return (
                  <tr key={s.id} className="border-b last:border-0 hover:bg-gray-50">
                    <td className="px-3 py-2 font-medium">{periodLabel}</td>
                    <td className="px-3 py-2 font-mono">{s.total_consumption_kl.toFixed(3)}</td>
                    <td className="px-3 py-2 font-mono">${s.billing_cost_aud.toFixed(2)}</td>
                    <td className="px-3 py-2 font-mono text-gray-600">
                      {v?.has_sufficient_readings
                        ? v.household_sum_kl
                        : <span className="text-gray-400 italic">n/a</span>}
                    </td>
                    <td className={`px-3 py-2 font-mono ${discrepancyClass}`}>
                      {v?.has_sufficient_readings
                        ? `${discrepancy > 0 ? "+" : ""}${discrepancy} kL`
                        : <span>no data</span>}
                    </td>
                    <td className="px-3 py-2 text-gray-400 text-xs truncate max-w-32">
                      {s.source_filename ?? "—"}
                    </td>
                    <td className="px-3 py-2 text-center">
                      <button
                        onClick={() => handleDelete(s.id)}
                        className="text-red-400 hover:text-red-700 font-bold leading-none text-base"
                        title="Delete statement"
                      >
                        ×
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
