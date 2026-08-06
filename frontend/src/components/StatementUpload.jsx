import { useState } from "react";
import { toast } from "react-hot-toast";
import { api } from "../api";
import { monthLabel } from "../utils/billing";
import StatementsModal from "./StatementsModal";

export default function StatementUpload({
  billingStatements,
  verificationData,
  apiKey,
  apiProvider,
  onImportSuccess,
  onDelete,
}) {
  const [pdfFile, setPdfFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [showModal, setShowModal] = useState(false);

  async function handleUpload() {
    if (!pdfFile) return;

    setUploading(true);
    const formData = new FormData();
    formData.append("file", pdfFile);
    const headers = apiKey ? { "X-Api-Key": apiKey, "X-Api-Provider": apiProvider } : {};

    try {
      const res = await api.post("/import-billing", formData, { headers });
      const d = res.data;
      const perUnit = d.cost_per_unit != null ? `$${d.cost_per_unit.toFixed(2)}/unit` : "";
      toast.success(
        `Imported ${monthLabel(d.billing_year, d.billing_month)} — ${d.total_units_consumed.toFixed(2)} units, $${d.total_cost.toFixed(2)} ${perUnit}`
      );
      setPdfFile(null);
      onImportSuccess();
    } catch (err) {
      toast.error(err.response?.data?.detail ?? "Upload failed. Check the PDF format.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="px-5 py-3 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">Import a Bill Statement</h3>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-1.5 text-xs font-medium text-gray-600 hover:text-gray-900 border border-gray-200 hover:border-gray-300 px-3 py-1.5 rounded-lg transition-colors"
        >
          View All Statements ({billingStatements.length})
        </button>
      </div>

      <div className="px-5 py-4 flex flex-wrap gap-3 items-center">
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

      {billingStatements.length === 0 && (
        <p className="px-5 pb-5 text-sm text-gray-400 italic">No billing statements imported yet.</p>
      )}

      {showModal && (
        <StatementsModal
          billingStatements={billingStatements}
          verificationData={verificationData}
          onDelete={onDelete}
          onClose={() => setShowModal(false)}
        />
      )}
    </div>
  );
}
