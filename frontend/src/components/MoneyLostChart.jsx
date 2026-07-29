import {
  BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, LabelList,
} from "recharts";
import { monthLabel } from "../utils/billing";

const POSITIVE_COLOR = "#f59e0b"; // amber — unaccounted-for cost (billed water not attributed to any household)
const NEGATIVE_COLOR = "#3b82f6"; // blue — household sum exceeds the billed amount

export default function MoneyLostChart({ verificationData }) {
  const data = (verificationData ?? [])
    .filter((v) => v.has_sufficient_readings && v.money_lost != null)
    .map((v) => ({
      period: monthLabel(v.billing_year, v.billing_month),
      moneyLost: v.money_lost,
    }));

  return (
    <div className="bg-white rounded-md p-4 border border-gray-200">
      <h3 className="text-lg font-semibold mb-1">Money Lost to Unaccounted Water</h3>
      <p className="text-xs text-gray-500 mb-3">
        Estimated $ value of the gap between each statement's billed consumption and the summed
        household meter deltas for that period.
      </p>
      {data.length > 0 ? (
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={data} margin={{ top: 20 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="period" tick={{ fontSize: 11 }} />
            <YAxis unit="$" tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v) => `$${v}`} />
            <ReferenceLine y={0} stroke="#9ca3af" />
            <Bar dataKey="moneyLost">
              {data.map((d, i) => (
                <Cell key={i} fill={d.moneyLost >= 0 ? POSITIVE_COLOR : NEGATIVE_COLOR} />
              ))}
              <LabelList
                dataKey="moneyLost"
                position="top"
                formatter={(v) => `$${v.toFixed(0)}`}
                style={{ fontSize: 10, fill: "#374151" }}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      ) : (
        <p className="text-gray-400 text-sm italic">
          Import a bill statement and add household readings for the same period to see this chart.
        </p>
      )}
    </div>
  );
}
