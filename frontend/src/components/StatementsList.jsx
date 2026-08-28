import { useState } from "react";
import { toast } from "react-hot-toast";
import { api } from "../api";
import { Download, Plus } from "lucide-react";
import { monthLabel, exportCSV, DISCREPANCY_TOLERANCE_UNITS } from "../utils/billing";

function periodLabel(s) {
  if (s.billing_month == null || s.billing_year == null) return "Needs review";
  const sameMonth =
    !s.period_end_month ||
    (s.period_end_month === s.billing_month && s.period_end_year === s.billing_year);
  return sameMonth
    ? monthLabel(s.billing_year, s.billing_month)
    : `${monthLabel(s.billing_year, s.billing_month)} – ${monthLabel(s.period_end_year, s.period_end_month)}`;
}

function DateEdit({ id, month, year, monthField, yearField, onCommit, autoFocus }) {
  return (
    <span className="inline-flex items-center gap-0.5 font-mono text-xs">
      <input
        type="number"
        min="1"
        max="12"
        autoFocus={autoFocus}
        key={`${id}-${monthField}-${month}`}
        defaultValue={month ?? ""}
        onBlur={(e) => onCommit(monthField, e.target.value, month)}
        title="Month"
        className="w-9 bg-transparent border border-transparent hover:border-gray-300 focus:border-blue-400 focus:bg-white rounded px-1 py-0.5 focus:outline-none focus:ring-1 focus:ring-blue-400"
      />
      /
      <input
        type="number"
        min="2000"
        key={`${id}-${yearField}-${year}`}
        defaultValue={year ?? ""}
        onBlur={(e) => onCommit(yearField, e.target.value, year)}
        title="Year"
        className="w-14 bg-transparent border border-transparent hover:border-gray-300 focus:border-blue-400 focus:bg-white rounded px-1 py-0.5 focus:outline-none focus:ring-1 focus:ring-blue-400"
      />
    </span>
  );
}

// Reads as plain text (like the read-only label it replaces) until clicked, then swaps
// in editable month/year fields; loses focus on the group -> reverts to the text label.
function PeriodCell({ s, editing, onStartEdit, onStopEdit, onDateFieldBlur }) {
  if (!editing) {
    return (
      <span className="inline-flex items-center gap-1.5">
        <button
          type="button"
          onClick={onStartEdit}
          title="Click to edit"
          className="text-left font-medium text-gray-900 hover:bg-gray-100 rounded px-1 py-0.5 -mx-1 transition-colors"
        >
          {periodLabel(s)}
        </button>
        {s.needs_review && (
          <span
            title="This statement's fields are blank and need to be filled in manually — either automatic extraction failed for the imported PDF, or the row was added blank."
            className="text-[10px] font-semibold uppercase tracking-wide text-amber-700 bg-amber-100 px-1.5 py-0.5 rounded"
          >
            Needs Review
          </span>
        )}
      </span>
    );
  }
  return (
    <div
      className="flex items-center gap-1"
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) onStopEdit();
      }}
    >
      <DateEdit
        id={s.id}
        month={s.billing_month}
        year={s.billing_year}
        monthField="billing_month"
        yearField="billing_year"
        onCommit={onDateFieldBlur}
        autoFocus
      />
      <span className="text-gray-300">–</span>
      <DateEdit
        id={s.id}
        month={s.period_end_month}
        year={s.period_end_year}
        monthField="period_end_month"
        yearField="period_end_year"
        onCommit={onDateFieldBlur}
      />
    </div>
  );
}

export default function StatementsList({ billingStatements, verificationData, onDelete, onUpdate }) {
  const [editingPeriodId, setEditingPeriodId] = useState(null);
  const [creatingBlank, setCreatingBlank] = useState(false);

  // Chronological order, oldest → newest. Needs-review stubs have no known period yet,
  // so they sort last rather than producing NaN comparisons.
  const sorted = [...billingStatements].sort((a, b) => {
    const aYear = a.billing_year ?? Infinity;
    const bYear = b.billing_year ?? Infinity;
    if (aYear !== bYear) return aYear - bYear;
    return (a.billing_month ?? Infinity) - (b.billing_month ?? Infinity);
  });

  async function handleCreateBlank() {
    setCreatingBlank(true);
    try {
      await api.post("/billing-statements");
      toast.success("Blank statement added — fill in the fields below.");
      onUpdate();
    } catch (err) {
      toast.error("Couldn't add statement: " + (err.response?.data?.detail ?? err.message));
    } finally {
      setCreatingBlank(false);
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

  async function handleDateFieldBlur(id, field, rawValue, currentValue) {
    const num = parseInt(rawValue, 10);
    const isMonth = field.endsWith("_month");
    if (Number.isNaN(num) || num === currentValue) return;
    if (isMonth ? num < 1 || num > 12 : num < 2000) return;
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
        <div className="flex items-center gap-2">
          <button
            onClick={handleCreateBlank}
            disabled={creatingBlank}
            className="flex items-center gap-1.5 text-xs font-medium text-gray-500 hover:text-gray-800 border border-gray-200 hover:border-gray-300 px-2.5 py-1.5 rounded-lg disabled:opacity-40 transition-colors"
          >
            <Plus size={12} />
            New Statement
          </button>
          <button
            onClick={() =>
              exportCSV(
                sorted.map((s) => ({
                  period: periodLabel(s),
                  units_consumed: s.total_units_consumed,
                  total_cost: s.total_cost,
                  cost_per_unit: s.cost_per_unit ?? "",
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
                  <tr
                    key={s.id}
                    className={`hover:bg-blue-50 transition-colors ${s.needs_review ? "bg-amber-50/60" : ""}`}
                  >
                    <td className="px-3 py-3">
                      <PeriodCell
                        s={s}
                        editing={editingPeriodId === s.id}
                        onStartEdit={() => setEditingPeriodId(s.id)}
                        onStopEdit={() => setEditingPeriodId(null)}
                        onDateFieldBlur={(field, raw, cur) => handleDateFieldBlur(s.id, field, raw, cur)}
                      />
                    </td>
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
