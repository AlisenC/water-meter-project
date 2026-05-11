import { useState } from "react";

const REASON_LABELS = {
  missing_reading: { label: "Missing", style: "bg-gray-100 text-gray-700" },
  invalid_reading: { label: "Invalid", style: "bg-red-100 text-red-700" },
};

export default function DataQuality({ importReport, anomalies = [] }) {
  const [errorsOpen, setErrorsOpen] = useState(true);
  const [spikesOpen, setSpikesOpen] = useState(true);
  const [expandedSpikes, setExpandedSpikes] = useState(new Set());

  function toggleSpike(i) {
    setExpandedSpikes((prev) => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });
  }

  return (
    <div className="mb-4 space-y-3">
      {/* Import Errors */}
      {importReport && (
        <div className="border rounded-md overflow-hidden">
          <button
            onClick={() => setErrorsOpen((v) => !v)}
            className="w-full flex justify-between items-center px-4 py-2 bg-gray-50 text-sm font-semibold text-gray-700 hover:bg-gray-100"
          >
            <span>Import Errors ({importReport.errors.length})</span>
            <span>{errorsOpen ? "▲" : "▼"}</span>
          </button>
          {errorsOpen && (
            <div className="p-3">
              {importReport.errors.length === 0 ? (
                <p className="text-green-600 text-sm">No errors — all rows imported cleanly.</p>
              ) : (
                <table className="w-full text-sm border-collapse">
                  <thead>
                    <tr className="text-left text-gray-500 border-b">
                      <th className="pb-1 pr-4">Row #</th>
                      <th className="pb-1 pr-4">Reason</th>
                      <th className="pb-1">Raw Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {importReport.errors.map((err, i) => {
                      const badge = REASON_LABELS[err.reason] ?? {
                        label: err.reason,
                        style: "bg-gray-100 text-gray-700",
                      };
                      return (
                        <tr key={i} className="border-b last:border-0">
                          <td className="py-1 pr-4 font-mono">{err.row_num}</td>
                          <td className="py-1 pr-4">
                            <span className={`px-2 py-0.5 rounded text-xs font-medium ${badge.style}`}>
                              {badge.label}
                            </span>
                          </td>
                          <td className="py-1 font-mono text-gray-500">
                            {err.raw_value === "" ? <em>empty</em> : err.raw_value}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </div>
      )}

      {/* Spike Analysis */}
      <div className="border rounded-md overflow-hidden">
        <button
          onClick={() => setSpikesOpen((v) => !v)}
          className="w-full flex justify-between items-center px-4 py-2 bg-gray-50 text-sm font-semibold text-gray-700 hover:bg-gray-100"
        >
          <span>Spike Analysis ({anomalies.length})</span>
          <span>{spikesOpen ? "▲" : "▼"}</span>
        </button>
        {spikesOpen && (
          <div className="p-3">
            {anomalies.length === 0 ? (
              <p className="text-green-600 text-sm">No spikes detected.</p>
            ) : (
              <ul className="space-y-2">
                {anomalies.map((a, i) => {
                  const isExpanded = expandedSpikes.has(i);
                  const gapInduced = a.is_gap_induced;
                  return (
                    <li
                      key={i}
                      className={`rounded border text-sm ${
                        gapInduced
                          ? "border-yellow-300 bg-yellow-50"
                          : "border-orange-300 bg-orange-50"
                      }`}
                    >
                      <button
                        onClick={() => toggleSpike(i)}
                        className="w-full flex justify-between items-center px-3 py-2 text-left"
                      >
                        <span>
                          <span className="font-semibold">{a.household}</span>
                          {" — "}
                          {a.increase_percent}% spike on{" "}
                          {new Date(a.reading_date).toLocaleDateString("en-AU", {
                            month: "short",
                            year: "numeric",
                          })}
                          {" "}
                          <span
                            className={`text-xs font-medium px-1.5 py-0.5 rounded ${
                              gapInduced
                                ? "bg-yellow-200 text-yellow-800"
                                : "bg-orange-200 text-orange-800"
                            }`}
                          >
                            {gapInduced ? "Gap-induced" : "True spike"}
                          </span>
                        </span>
                        <span className="text-gray-400 ml-2">{isExpanded ? "▲" : "▼"}</span>
                      </button>
                      {isExpanded && (
                        <div className="px-3 pb-2 text-xs space-y-0.5 text-gray-700">
                          <p>Previous usage: <span className="font-mono">{a.previous_usage}</span></p>
                          <p>Current usage: <span className="font-mono">{a.current_usage}</span></p>
                          <p>
                            Gap before reading: <span className="font-mono">{a.gap_days}d</span>
                            {" vs median "}
                            <span className="font-mono">{a.median_interval_days}d</span>
                            {gapInduced
                              ? " — spike likely reflects accumulated usage over a data gap"
                              : " — gap is normal; spike appears genuine"}
                          </p>
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
