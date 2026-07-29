import { useState } from "react";
import { toast } from "react-hot-toast";
import { api } from "../api";
import { Search, Download } from "lucide-react";
import { toUnits, unitsToCubicFeet } from "../utils/units";
import { exportCSV } from "../utils/billing";

export default function ReadingTable({ readings, setReadings }) {
  const [mi, setMi] = useState("");
  const [reading, setReading] = useState("");
  const [filterText, setFilterText] = useState("");

  const sorted = [...readings].sort(
    (a, b) => new Date(b.record_date) - new Date(a.record_date)
  );
  const filtered = filterText
    ? sorted.filter((r) => r.mi.toLowerCase().includes(filterText.toLowerCase()))
    : sorted;

  async function handleSubmit(e) {
    e.preventDefault();
    if (!mi || !reading) return;
    try {
      // Manual entries are stored as cubic feet (unit=1) server-side — convert
      // the user's "units of water" input on the way in so it stays on the
      // same normalized footing as CSV/statement data.
      const res = await api.post("/readings", { mi, reading: unitsToCubicFeet(parseFloat(reading)) });
      setReadings([...readings, res.data]);
      setMi("");
      setReading("");
    } catch (err) {
      toast.error(err.response?.data?.detail ?? "Failed to add reading.");
    }
  }

  async function handleDelete(id) {
    try {
      await api.delete(`/readings/${id}`);
      setReadings(readings.filter((r) => r.id !== id));
    } catch (err) {
      toast.error(err.response?.data?.detail ?? "Failed to delete reading.");
    }
  }

  return (
    <div className="space-y-4">
      {/* Add Reading form */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Add Reading</h3>
        <form onSubmit={handleSubmit} className="flex flex-wrap gap-2 items-end">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-gray-500">Household</label>
            <input
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent w-44"
              value={mi}
              onChange={(e) => setMi(e.target.value)}
              placeholder="e.g. Unit 1"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-gray-500">Reading (units of water)</label>
            <input
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent w-32"
              type="number"
              step="any"
              value={reading}
              onChange={(e) => setReading(e.target.value)}
              placeholder="0.000"
            />
          </div>
          <button
            type="submit"
            disabled={!mi || !reading}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50 transition-colors"
          >
            Add
          </button>
        </form>
      </div>

      {/* Table card */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        {/* Toolbar */}
        <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between gap-3">
          <div className="relative flex-1 max-w-xs">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              className="w-full pl-8 pr-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
              placeholder="Filter by household…"
            />
          </div>
          <button
            onClick={() =>
              exportCSV(
                filtered.map((r) => ({
                  household: r.mi,
                  reading_units: toUnits(r.reading, r.unit).toFixed(3),
                  date: new Date(r.record_date).toLocaleDateString("en-AU"),
                })),
                "readings.csv"
              )
            }
            disabled={filtered.length === 0}
            className="flex items-center gap-1.5 text-xs font-medium text-gray-600 hover:text-gray-900 border border-gray-200 hover:border-gray-300 px-3 py-2 rounded-lg disabled:opacity-40 transition-colors"
          >
            <Download size={13} />
            Export CSV
          </button>
        </div>

        {filtered.length === 0 ? (
          <p className="px-5 py-8 text-sm text-gray-400 italic text-center">
            {filterText ? "No readings match your filter." : "No readings yet."}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b border-gray-100 bg-gray-50">
                  <th className="px-5 py-2.5 text-xs font-semibold uppercase tracking-wider">Household</th>
                  <th className="px-5 py-2.5 text-xs font-semibold uppercase tracking-wider">Reading (units)</th>
                  <th className="px-5 py-2.5 text-xs font-semibold uppercase tracking-wider">Date</th>
                  <th className="px-5 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {filtered.map((r) => (
                  <tr key={r.id} className="hover:bg-blue-50 transition-colors">
                    <td className="px-5 py-3 font-medium text-gray-900">{r.mi}</td>
                    <td className="px-5 py-3 font-mono text-gray-700">{toUnits(r.reading, r.unit).toFixed(3)}</td>
                    <td className="px-5 py-3 text-gray-500">
                      {new Date(r.record_date).toLocaleDateString("en-AU", {
                        month: "short",
                        year: "numeric",
                      })}
                    </td>
                    <td className="px-5 py-3 text-right">
                      <button
                        onClick={() => handleDelete(r.id)}
                        className="text-gray-300 hover:text-red-500 transition-colors text-lg leading-none font-bold"
                        title="Delete reading"
                      >
                        ×
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {filtered.length > 0 && (
          <div className="px-5 py-2 border-t border-gray-100 bg-gray-50 text-xs text-gray-400">
            {filtered.length} reading{filtered.length !== 1 ? "s" : ""}
            {filterText && readings.length !== filtered.length && ` (filtered from ${readings.length})`}
          </div>
        )}
      </div>
    </div>
  );
}
