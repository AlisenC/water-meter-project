import { useState, useEffect } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { api } from "../api";
import { AlertTriangle } from "lucide-react";

function dayLabel(isoString) {
  return new Date(isoString).toLocaleDateString("en-AU", { month: "short", day: "numeric" });
}

function LeakDot(props) {
  const { cx, cy, payload } = props;
  if (!payload.is_leak) return null;
  return <circle cx={cx} cy={cy} r={5} fill="#ef4444" stroke="white" strokeWidth={1.5} />;
}

export default function LeakSessionView({ sessionId }) {
  const [periods, setPeriods] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.get(`/leak/sessions/${sessionId}/analysis`)
      .then((res) => { if (!cancelled) { setPeriods(res.data); setError(null); } })
      .catch((err) => { if (!cancelled) setError(err.response?.data?.detail ?? "Failed to load analysis."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [sessionId]);

  if (loading) return <p className="text-sm text-gray-400 italic">Loading…</p>;
  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!periods || periods.length === 0) {
    return (
      <p className="text-sm text-gray-400 italic bg-white rounded-lg border border-gray-200 p-4">
        Import at least two daily main meter readings (and matching submeter readings) to see the comparison.
      </p>
    );
  }

  const chartData = periods.map((p) => ({
    date: dayLabel(p.period_end),
    "Main Meter Flow": p.main_flow,
    "Submeter Sum": p.submeter_sum,
    is_leak: p.is_leak,
  }));

  const leakCount = periods.filter((p) => p.is_leak).length;

  return (
    <div className="space-y-4">
      {leakCount > 0 && (
        <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-lg px-4 py-2.5 text-sm text-red-700">
          <AlertTriangle size={16} className="flex-shrink-0" />
          <span><strong>{leakCount}</strong> day{leakCount !== 1 ? "s" : ""} where submeter usage exceeded the main meter — potential leak.</span>
        </div>
      )}

      <div className="bg-white rounded-lg p-4 border border-gray-200">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Main Meter Flow vs Submeter Sum</h3>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} />
            <YAxis unit=" CCF" tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v) => (v == null ? "no data" : `${v} CCF`)} />
            <Legend />
            <Line type="monotone" dataKey="Main Meter Flow" stroke="#1d4ed8" strokeWidth={2} dot={false} connectNulls />
            <Line type="monotone" dataKey="Submeter Sum" stroke="#10b981" strokeWidth={2} dot={<LeakDot />} connectNulls />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b border-gray-100 bg-gray-50">
              <th className="px-4 py-2 text-xs font-semibold uppercase tracking-wider">Period</th>
              <th className="px-4 py-2 text-xs font-semibold uppercase tracking-wider">Main Flow</th>
              <th className="px-4 py-2 text-xs font-semibold uppercase tracking-wider">Submeter Sum</th>
              <th className="px-4 py-2 text-xs font-semibold uppercase tracking-wider">Difference</th>
              <th className="px-4 py-2 text-xs font-semibold uppercase tracking-wider" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {periods.map((p, i) => (
              <tr key={i} className={p.is_leak ? "bg-red-50" : ""}>
                <td className="px-4 py-2 text-gray-700">{dayLabel(p.period_start)} → {dayLabel(p.period_end)}</td>
                <td className="px-4 py-2 font-mono text-gray-700">{p.main_flow != null ? `${p.main_flow} CCF` : "—"}</td>
                <td className="px-4 py-2 font-mono text-gray-700">
                  {p.has_submeter_data ? `${p.submeter_sum} CCF` : <span className="text-gray-400 italic text-xs">no data</span>}
                </td>
                <td className={`px-4 py-2 font-mono ${p.difference > 0 ? "text-red-600 font-semibold" : "text-gray-600"}`}>
                  {p.difference != null ? `${p.difference > 0 ? "+" : ""}${p.difference} CCF` : "—"}
                </td>
                <td className="px-4 py-2">
                  {p.is_leak && (
                    <span className="text-xs font-medium text-red-700 bg-red-100 px-2 py-0.5 rounded-full">Potential Leak</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
