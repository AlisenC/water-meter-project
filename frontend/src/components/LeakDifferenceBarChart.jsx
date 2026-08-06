import {
  BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, LabelList,
} from "recharts";

const LEAK_COLOR = "#d03b3b";
const NORMAL_COLOR = "#9ca3af";

function dayLabel(isoString) {
  return new Date(isoString).toLocaleDateString("en-AU", { month: "short", day: "numeric" });
}

function ChartTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm px-3 py-2 text-xs space-y-1">
      <p className="font-semibold text-gray-700">{d.period}</p>
      <p className="text-gray-600">Submeter Δ: {d.submeter_delta} CCF</p>
      <p className="text-gray-600">Main Δ (closest): {d.main_delta} CCF</p>
      <p className={d.is_leak ? "text-red-600 font-semibold" : "text-gray-600"}>
        Difference: {d.difference > 0 ? "+" : ""}{d.difference} CCF
      </p>
      {d.is_leak && <p className="text-red-600 font-semibold">Potential leak</p>}
    </div>
  );
}

export default function LeakDifferenceBarChart({ periods }) {
  const data = (periods ?? [])
    .filter((p) => p.difference != null)
    .map((p) => ({
      period: dayLabel(p.period_end),
      difference: p.difference,
      submeter_delta: p.submeter_delta,
      main_delta: p.main_delta,
      is_leak: p.is_leak,
    }));

  return (
    <div className="bg-white rounded-lg p-4 border border-gray-200">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">Main Meter vs Submeter Difference by Period</h3>
      {data.length > 0 ? (
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={data} margin={{ top: 20 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="period" tick={{ fontSize: 11 }} />
            <YAxis unit=" CCF" tick={{ fontSize: 11 }} />
            <Tooltip content={<ChartTooltip />} />
            <ReferenceLine y={0} stroke={NORMAL_COLOR} />
            <Bar dataKey="difference">
              {data.map((d, i) => (
                <Cell key={i} fill={d.is_leak ? LEAK_COLOR : NORMAL_COLOR} />
              ))}
              <LabelList
                dataKey="difference"
                position="top"
                formatter={(v) => `${v > 0 ? "+" : ""}${v}`}
                style={{ fontSize: 10, fill: "#374151" }}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      ) : (
        <p className="text-gray-400 text-sm italic">
          Import overlapping main meter and submeter data to see period-by-period differences.
        </p>
      )}
    </div>
  );
}
