import { useState, useEffect, useCallback } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { api } from "../api";
import { AlertTriangle, ChevronDown, ChevronRight } from "lucide-react";
import LeakDifferenceBarChart from "./LeakDifferenceBarChart";
import LeakRawDataTable from "./LeakRawDataTable";

function dayLabel(isoString) {
  return new Date(isoString).toLocaleDateString("en-AU", { month: "short", day: "numeric" });
}

function timeLabel(isoString) {
  return new Date(isoString).toLocaleString("en-AU", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function differencePerDay(period) {
  if (period.difference == null) return null;
  const days = (new Date(period.period_end) - new Date(period.period_start)) / (1000 * 60 * 60 * 24);
  return days > 0 ? period.difference / days : null;
}

export default function LeakSessionView({ sessionId }) {
  const [mainFlowSeries, setMainFlowSeries] = useState(null);
  const [periods, setPeriods] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [rawDataOpen, setRawDataOpen] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get(`/leak/sessions/${sessionId}/analysis`);
      setMainFlowSeries(res.data.main_flow_series);
      setPeriods(res.data.periods);
      setError(null);
    } catch (err) {
      setError(err.response?.data?.detail ?? "Failed to load analysis.");
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => { refresh(); }, [refresh]);

  if (loading) return <p className="text-sm text-gray-400 italic">Loading…</p>;
  if (error) return <p className="text-sm text-red-600">{error}</p>;

  const hasMainFlow = mainFlowSeries && mainFlowSeries.length > 0;
  const hasPeriods = periods && periods.length > 0;

  if (!hasMainFlow && !hasPeriods) {
    return (
      <div className="space-y-4">
        <p className="text-sm text-gray-400 italic bg-white rounded-lg border border-gray-200 p-4">
          Import at least two main meter readings and two submeter readings (on distinct dates) to see the comparison.
        </p>
        <RawDataSection sessionId={sessionId} open={rawDataOpen} setOpen={setRawDataOpen} onChanged={refresh} />
      </div>
    );
  }

  const lineChartData = (mainFlowSeries ?? []).map((p) => ({
    date: timeLabel(p.period_end),
    "Main Meter Flow": p.flow,
  }));

  const leakCount = (periods ?? []).filter((p) => p.is_leak).length;

  return (
    <div className="space-y-4">
      {leakCount > 0 && (
        <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-lg px-4 py-2.5 text-sm text-red-700">
          <AlertTriangle size={16} className="flex-shrink-0" />
          <span><strong>{leakCount}</strong> period{leakCount !== 1 ? "s" : ""} where the main meter's flow exceeded what submeters accounted for — potential leak.</span>
        </div>
      )}

      <div className="bg-white rounded-lg p-4 border border-gray-200">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Main Meter Flow</h3>
        {hasMainFlow ? (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={lineChartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis unit=" CCF" tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => `${v} CCF`} />
              <Legend />
              <Line type="monotone" dataKey="Main Meter Flow" stroke="#1d4ed8" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-sm text-gray-400 italic">Import at least two main meter readings to see this chart.</p>
        )}
      </div>

      {hasPeriods ? (
        <LeakDifferenceBarChart periods={periods} />
      ) : (
        <div className="bg-white rounded-lg p-4 border border-gray-200">
          <p className="text-sm text-gray-400 italic">Import at least two submeter readings (on distinct dates) to see the difference chart.</p>
        </div>
      )}

      {hasPeriods && (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-100 bg-gray-50">
                <th className="px-4 py-2 text-xs font-semibold uppercase tracking-wider">Period</th>
                <th className="px-4 py-2 text-xs font-semibold uppercase tracking-wider">Submeter Δ</th>
                <th className="px-4 py-2 text-xs font-semibold uppercase tracking-wider">Main Δ (closest)</th>
                <th className="px-4 py-2 text-xs font-semibold uppercase tracking-wider">Difference</th>
                <th className="px-4 py-2 text-xs font-semibold uppercase tracking-wider">Difference / Day</th>
                <th className="px-4 py-2 text-xs font-semibold uppercase tracking-wider" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {periods.map((p, i) => {
                const perDay = differencePerDay(p);
                return (
                  <tr key={i} className={p.is_leak ? "bg-red-50" : ""}>
                    <td className="px-4 py-2 text-gray-700">{dayLabel(p.period_start)} → {dayLabel(p.period_end)}</td>
                    <td className="px-4 py-2 font-mono text-gray-700">{p.submeter_delta} CCF</td>
                    <td className="px-4 py-2 font-mono text-gray-700">
                      {p.main_delta != null ? `${p.main_delta} CCF` : <span className="text-gray-400 italic text-xs">no data</span>}
                    </td>
                    <td className={`px-4 py-2 font-mono ${p.difference > 0 ? "text-red-600 font-semibold" : "text-gray-600"}`}>
                      {p.difference != null ? `${p.difference > 0 ? "+" : ""}${p.difference} CCF` : "—"}
                    </td>
                    <td className={`px-4 py-2 font-mono ${perDay > 0 ? "text-red-600 font-semibold" : "text-gray-600"}`}>
                      {perDay != null ? `${perDay > 0 ? "+" : ""}${perDay.toFixed(3)} CCF/day` : "—"}
                    </td>
                    <td className="px-4 py-2">
                      {p.is_leak && (
                        <span className="text-xs font-medium text-red-700 bg-red-100 px-2 py-0.5 rounded-full">Potential Leak</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <RawDataSection sessionId={sessionId} open={rawDataOpen} setOpen={setRawDataOpen} onChanged={refresh} />
    </div>
  );
}

function RawDataSection({ sessionId, open, setOpen, onChanged }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-1.5 px-4 py-2.5 text-xs font-semibold text-gray-600 hover:text-gray-800"
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        Raw Data
      </button>
      {open && (
        <div className="border-t border-gray-100 px-4 py-4 space-y-3">
          <LeakRawDataTable sessionId={sessionId} kind="submeter" onChanged={onChanged} />
          <LeakRawDataTable sessionId={sessionId} kind="main-meter" onChanged={onChanged} />
        </div>
      )}
    </div>
  );
}
