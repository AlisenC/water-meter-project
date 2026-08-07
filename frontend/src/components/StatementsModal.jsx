import { toast } from "react-hot-toast";
import { api } from "../api";
import { Download } from "lucide-react";
import { monthLabel, exportCSV, DISCREPANCY_TOLERANCE_UNITS } from "../utils/billing";

function periodLabel(s) {
  const sameMonth =
    !s.period_end_month ||
    (s.period_end_month === s.billing_month && s.period_end_year === s.billing_year);
  return sameMonth
    ? monthLabel(s.billing_year, s.billing_month)
    : `${monthLabel(s.billing_year, s.billing_month)} – ${monthLabel(s.period_end_year, s.period_end_month)}`;
}

export default function StatementsModal({ billingStatements, verificationData, onDelete, onClose }) {
  // Chronological order, oldest → newest.
  const sorted = [...billingStatements].sort((a, b) =>
    a.billing_year !== b.billing_year ? a.billing_year - b.billing_year : a.billing_month - b.billing_month
  );

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
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-white rounded-xl shadow-xl w-full max-w-4xl max-h-[90vh] overflow-y-auto m-4">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <h2 className="text-lg font-semibold">Bill Statements</h2>
          <div className="flex items-center gap-3">
            <button
              onClick={() =>
                exportCSV(
                  sorted.map((s) => ({
                    period: periodLabel(s),
                    units_consumed: s.total_units_consumed,
                    total_cost: s.total_cost,
                    cost_per_unit: s.cost_per_unit ?? "",
                    file: s.source_filename ?? "",
                  })),
                  "billing-statements.csv"
                )
              }
              disabled={sorted.length === 0}
              className="flex items-center gap-1.5 text-xs font-medium text-gray-500 hover:text-gray-800 border border-gray-200 hover:border-gray-300 px-2.5 py-1.5 rounded-lg disabled:opacity-40 transition-colors"
            >
              <Download size={12} />
              Export CSV
            </button>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
          </div>
        </div>

        <div className="px-6 py-5">
          {sorted.length === 0 ? (
            <p className="py-8 text-sm text-gray-400 italic text-center">No billing statements imported yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-gray-500 border-b border-gray-100 bg-gray-50">
                    <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider">Period</th>
                    <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider">Units Consumed</th>
                    <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider">Total Cost</th>
                    <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider">Cost/Unit</th>
                    <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider">Household Sum</th>
                    <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider">Discrepancy</th>
                    <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider">Money Lost</th>
                    <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider">File</th>
                    <th className="px-3 py-2.5" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {sorted.map((s) => {
                    const v = verificationData.find((vd) => vd.billing_statement_id === s.id);
                    const discrepancy = v?.discrepancy_units;
                    const discrepancyClass =
                      !v || !v.has_sufficient_readings
                        ? "text-gray-400 italic"
                        : Math.abs(discrepancy) < DISCREPANCY_TOLERANCE_UNITS
                        ? "text-green-700"
                        : "text-orange-700 font-semibold";
                    const moneyLostClass =
                      !v || v.money_lost == null
                        ? "text-gray-400 italic"
                        : v.money_lost > 0
                        ? "text-orange-700 font-semibold"
                        : "text-blue-700";

                    return (
                      <tr key={s.id} className="hover:bg-blue-50 transition-colors">
                        <td className="px-3 py-3 font-medium text-gray-900">{periodLabel(s)}</td>
                        <td className="px-3 py-3 font-mono text-gray-700">{s.total_units_consumed.toFixed(2)}</td>
                        <td className="px-3 py-3 font-mono text-gray-700">${s.total_cost.toFixed(2)}</td>
                        <td className="px-3 py-3 font-mono text-gray-700">
                          {s.cost_per_unit != null ? `$${s.cost_per_unit.toFixed(2)}` : "—"}
                        </td>
                        <td className="px-3 py-3 font-mono text-gray-600">
                          {v?.has_sufficient_readings ? (
                            v.household_sum_units
                          ) : (
                            <span className="text-gray-400 italic text-xs">n/a</span>
                          )}
                        </td>
                        <td className={`px-3 py-3 font-mono ${discrepancyClass}`}>
                          {v?.has_sufficient_readings ? (
                            `${discrepancy > 0 ? "+" : ""}${discrepancy} units`
                          ) : (
                            <span className="text-xs">no data</span>
                          )}
                        </td>
                        <td className={`px-3 py-3 font-mono ${moneyLostClass}`}>
                          {v?.money_lost != null ? (
                            `${v.money_lost > 0 ? "+" : ""}$${v.money_lost.toFixed(2)}`
                          ) : (
                            <span className="text-xs">no data</span>
                          )}
                        </td>
                        <td className="px-3 py-3 text-gray-400 text-xs truncate max-w-32">
                          {s.source_filename ?? "—"}
                        </td>
                        <td className="px-3 py-3 text-right">
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
      </div>
    </div>
  );
}
