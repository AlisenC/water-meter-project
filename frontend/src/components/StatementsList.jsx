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

function storedFilename(s) {
  // Stored under the period's END month/year — see backend/main.py's _statement_pdf_path_if_exists.
  return `${s.period_end_year}_${String(s.period_end_month).padStart(2, "0")}.pdf`;
}

export default function StatementsList({ billingStatements, verificationData, onDelete, onUpdate }) {
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

  async function handleFieldBlur(id, field, rawValue, currentValue) {
    const num = parseFloat(rawValue);
    if (Number.isNaN(num) || num < 0 || num === currentValue) return;
    try {
      await api.patch(`/billing-statements/${id}`, { [field]: num });
      toast.success("Statement updated.");
      onUpdate();
    } catch (err) {
      toast.error("Update failed: " + (err.response?.data?.detail ?? err.message));
    }
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3 bg-gray-50 border-b border-gray-200">
        <h3 className="text-sm font-semibold text-gray-700">Bill Statements ({sorted.length})</h3>
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
      </div>

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
                  !v || !v.has_sufficient_readings || discrepancy == null
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
                    <td className="px-3 py-3">
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        key={`${s.id}-units-${s.total_units_consumed}`}
                        defaultValue={s.total_units_consumed}
                        onBlur={(e) =>
                          handleFieldBlur(s.id, "total_units_consumed", e.target.value, s.total_units_consumed)
                        }
                        className="w-24 font-mono text-gray-700 bg-transparent border border-transparent hover:border-gray-300 focus:border-blue-400 focus:bg-white rounded px-1.5 py-1 focus:outline-none focus:ring-1 focus:ring-blue-400"
                      />
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-1">
                        <span className="text-gray-400">$</span>
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          key={`${s.id}-cost-${s.total_cost}`}
                          defaultValue={s.total_cost}
                          onBlur={(e) => handleFieldBlur(s.id, "total_cost", e.target.value, s.total_cost)}
                          className="w-24 font-mono text-gray-700 bg-transparent border border-transparent hover:border-gray-300 focus:border-blue-400 focus:bg-white rounded px-1.5 py-1 focus:outline-none focus:ring-1 focus:ring-blue-400"
                        />
                      </div>
                    </td>
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
                      {v?.has_sufficient_readings && discrepancy != null ? (
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
                    <td className="px-3 py-3 text-xs truncate max-w-32">
                      {s.has_pdf ? (
                        <a
                          href={`/api/billing-statements/${s.id}/pdf`}
                          target="_blank"
                          rel="noopener noreferrer"
                          title={s.source_filename ?? undefined}
                          className="text-blue-600 hover:text-blue-800 hover:underline"
                        >
                          {storedFilename(s)}
                        </a>
                      ) : (
                        <span className="text-gray-400">{s.source_filename ?? "—"}</span>
                      )}
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
  );
}
