import { useState } from "react";
import { toast } from "react-hot-toast";
import { api } from "../api";
import { Download } from "lucide-react";

function monthLabel(year, month) {
  return new Date(year, month - 1, 1).toLocaleDateString("en-AU", {
    month: "short",
    year: "numeric",
  });
}

function exportCSV(rows, filename) {
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

  async function handleUpload() {
    if (!pdfFile) return;
    if (!apiKey) {
      toast.error("No API key configured — add one in Settings.");
      return;
    }

    setUploading(true);
    const formData = new FormData();
    formData.append("file", pdfFile);

    try {
      const res = await api.post("/import-billing", formData, {
        headers: { "X-Api-Key": apiKey, "X-Api-Provider": apiProvider },
      });
      const d = res.data;
      toast.success(
        `Imported ${monthLabel(d.billing_year, d.billing_month)} — ${d.total_consumption_kl.toFixed(3)} kL, $${d.billing_cost_aud.toFixed(2)} AUD`
      );
      setPdfFile(null);
      onImportSuccess();
    } catch (err) {
      toast.error(err.response?.data?.detail ?? "Upload failed. Check the PDF format.");
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(id) {
    if (!window.confirm("Delete this billing statement?")) return;
    try {
      await api.delete(`/billing-statements/${id}`);
      onDelete(id);
      toast.success("Statement deleted.");
    } catch (err) {
      toast.error("Delete failed: " + (err.response?.data?.detail ?? err.message));
    }
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="px-5 py-3 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">Billing Statements</h3>
        <button
          onClick={() =>
            exportCSV(
              billingStatements.map((s) => ({
                period: (() => {
                  const sameMonth =
                    !s.period_end_month ||
                    (s.period_end_month === s.billing_month && s.period_end_year === s.billing_year);
                  return sameMonth
                    ? monthLabel(s.billing_year, s.billing_month)
                    : `${monthLabel(s.billing_year, s.billing_month)} - ${monthLabel(s.period_end_year, s.period_end_month)}`;
                })(),
                consumption_kl: s.total_consumption_kl,
                cost_aud: s.billing_cost_aud,
                file: s.source_filename ?? "",
              })),
              "billing-statements.csv"
            )
          }
          disabled={billingStatements.length === 0}
          className="flex items-center gap-1.5 text-xs font-medium text-gray-500 hover:text-gray-800 border border-gray-200 hover:border-gray-300 px-2.5 py-1.5 rounded-lg disabled:opacity-40 transition-colors"
        >
          <Download size={12} />
          Export CSV
        </button>
      </div>

      {/* Upload row */}
      <div className="px-5 py-4 flex flex-wrap gap-3 items-center border-b border-gray-100">
        <label className="flex items-center gap-2 cursor-pointer">
          <span className="text-xs font-medium text-gray-500">PDF Bill:</span>
          <input
            type="file"
            accept=".pdf,application/pdf"
            onChange={(e) => setPdfFile(e.target.files[0] ?? null)}
            className="text-sm text-gray-600 file:mr-2 file:py-1 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-medium file:bg-gray-100 file:text-gray-700 hover:file:bg-gray-200"
          />
        </label>
        <button
          onClick={handleUpload}
          disabled={!pdfFile || uploading}
          className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 text-sm font-medium rounded-lg disabled:opacity-50 transition-colors"
        >
          {uploading ? "Scanning…" : "Import PDF Bill"}
        </button>
      </div>

      {/* Statements table */}
      {billingStatements.length === 0 ? (
        <p className="px-5 py-8 text-sm text-gray-400 italic text-center">No billing statements imported yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-100 bg-gray-50">
                <th className="px-5 py-2.5 text-xs font-semibold uppercase tracking-wider">Period</th>
                <th className="px-5 py-2.5 text-xs font-semibold uppercase tracking-wider">Consumption (kL)</th>
                <th className="px-5 py-2.5 text-xs font-semibold uppercase tracking-wider">Cost (AUD)</th>
                <th className="px-5 py-2.5 text-xs font-semibold uppercase tracking-wider">Household Sum</th>
                <th className="px-5 py-2.5 text-xs font-semibold uppercase tracking-wider">Discrepancy</th>
                <th className="px-5 py-2.5 text-xs font-semibold uppercase tracking-wider">File</th>
                <th className="px-5 py-2.5" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
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
                  (s.period_end_month === s.billing_month && s.period_end_year === s.billing_year);
                const periodLabel = sameMonth
                  ? monthLabel(s.billing_year, s.billing_month)
                  : `${monthLabel(s.billing_year, s.billing_month)} – ${monthLabel(s.period_end_year, s.period_end_month)}`;

                return (
                  <tr key={s.id} className="hover:bg-blue-50 transition-colors">
                    <td className="px-5 py-3 font-medium text-gray-900">{periodLabel}</td>
                    <td className="px-5 py-3 font-mono text-gray-700">{s.total_consumption_kl.toFixed(3)}</td>
                    <td className="px-5 py-3 font-mono text-gray-700">${s.billing_cost_aud.toFixed(2)}</td>
                    <td className="px-5 py-3 font-mono text-gray-600">
                      {v?.has_sufficient_readings ? (
                        v.household_sum_kl
                      ) : (
                        <span className="text-gray-400 italic text-xs">n/a</span>
                      )}
                    </td>
                    <td className={`px-5 py-3 font-mono ${discrepancyClass}`}>
                      {v?.has_sufficient_readings
                        ? `${discrepancy > 0 ? "+" : ""}${discrepancy} kL`
                        : <span className="text-xs">no data</span>}
                    </td>
                    <td className="px-5 py-3 text-gray-400 text-xs truncate max-w-32">
                      {s.source_filename ?? "—"}
                    </td>
                    <td className="px-5 py-3 text-right">
                      <button
                        onClick={() => handleDelete(s.id)}
                        className="text-gray-300 hover:text-red-500 transition-colors text-lg leading-none font-bold"
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
