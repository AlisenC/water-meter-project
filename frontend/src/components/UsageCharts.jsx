import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from "recharts";

const COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899"];
const CUBIC_FEET_TO_GALLONS = 7.48052;

function toGallons(reading, unit) {
  const val = Number(reading) || 0;
  return unit === 1 ? val * CUBIC_FEET_TO_GALLONS : val;
}

function formatDate(dateStr) {
  return new Date(dateStr).toLocaleDateString("en-AU", { month: "short", day: "numeric" });
}

function groupByMi(readings) {
  const groups = {};
  for (const r of readings) {
    if (!groups[r.mi]) groups[r.mi] = [];
    groups[r.mi].push(r);
  }
  for (const mi of Object.keys(groups)) {
    groups[mi].sort((a, b) => new Date(a.record_date) - new Date(b.record_date));
  }
  return groups;
}

export default function UsageCharts({ readings }) {
  if (!readings || readings.length === 0) {
    return <div className="p-4 text-gray-400 text-sm italic">No readings to display.</div>;
  }

  const allGroups = groupByMi(readings);
  // Separate MAIN from household meters
  const households = Object.keys(allGroups).filter((mi) => mi !== "MAIN");
  const groups = Object.fromEntries(households.map((mi) => [mi, allGroups[mi]]));
  const mainReadings = allGroups["MAIN"] ?? [];

  // --- Existing charts (households only) ---

  const barData = households.flatMap((mi) => {
    const group = groups[mi];
    if (group.length < 2) return [];
    const prev = group[group.length - 2];
    const curr = group[group.length - 1];
    const consumption = Math.max(
      0,
      toGallons(curr.reading, curr.unit) - toGallons(prev.reading, prev.unit)
    );
    return [{ household: mi, total: parseFloat(consumption.toFixed(2)) }];
  });

  const pieData = barData
    .filter((d) => d.total > 0)
    .map((d) => ({ name: d.household, value: d.total }));

  const hasConsumptionData = barData.some((d) => d.total > 0);

  const dateMap = {};
  for (const mi of households) {
    const group = groups[mi];
    for (let i = 1; i < group.length; i++) {
      const prev = toGallons(group[i - 1].reading, group[i - 1].unit);
      const curr = toGallons(group[i].reading, group[i].unit);
      const delta = parseFloat(Math.max(0, curr - prev).toFixed(2));
      const date = formatDate(group[i].record_date);
      if (!dateMap[date]) dateMap[date] = { date };
      dateMap[date][mi] = delta;
    }
  }
  const lineData = Object.values(dateMap).sort(
    (a, b) => new Date(a.date) - new Date(b.date)
  );

  // --- MAIN vs household sum comparison ---

  // For each consecutive pair of MAIN readings, sum household deltas for the same period
  const comparisonData = [];
  for (let i = 1; i < mainReadings.length; i++) {
    const mainPrev = mainReadings[i - 1];
    const mainCurr = mainReadings[i];
    const mainDelta = parseFloat(
      Math.max(0, toGallons(mainCurr.reading, mainCurr.unit) - toGallons(mainPrev.reading, mainPrev.unit)).toFixed(2)
    );

    // Sum household consumption for readings that fall in this same period
    const periodStart = new Date(mainPrev.record_date);
    const periodEnd = new Date(mainCurr.record_date);

    let householdSum = 0;
    for (const mi of households) {
      const group = groups[mi];
      // Find the reading closest to periodStart and periodEnd within this household
      const prevR = group.filter((r) => new Date(r.record_date) <= periodEnd && new Date(r.record_date) >= periodStart)
        .sort((a, b) => new Date(a.record_date) - new Date(b.record_date));
      // Use readings that bracket this same period
      const before = group.filter((r) => new Date(r.record_date) <= periodStart).pop();
      const after = group.filter((r) => new Date(r.record_date) <= periodEnd).pop();
      if (before && after && before !== after) {
        householdSum += Math.max(0, toGallons(after.reading, after.unit) - toGallons(before.reading, before.unit));
      }
    }
    householdSum = parseFloat(householdSum.toFixed(2));
    const difference = parseFloat((mainDelta - householdSum).toFixed(2));

    comparisonData.push({
      date: formatDate(mainCurr.record_date),
      "Main Meter": mainDelta,
      "Household Sum": householdSum,
      "Unaccounted": difference,
    });
  }

  // Latest period summary stats
  const latest = comparisonData[comparisonData.length - 1];

  return (
    <div className="mb-6 space-y-6">
      {/* Main vs Household Sum comparison */}
      {mainReadings.length >= 2 && (
        <div className="bg-white rounded-md p-4 border border-gray-200">
          <h3 className="text-lg font-semibold mb-1">Main Meter vs Household Sum</h3>
          {latest && (
            <div className="flex gap-6 text-sm mb-3">
              <span>
                Main: <span className="font-mono font-semibold">{latest["Main Meter"]} gal</span>
              </span>
              <span>
                Households: <span className="font-mono font-semibold">{latest["Household Sum"]} gal</span>
              </span>
              <span>
                Unaccounted:{" "}
                <span className={`font-mono font-semibold ${latest["Unaccounted"] > 0 ? "text-orange-600" : "text-green-600"}`}>
                  {latest["Unaccounted"] > 0 ? "+" : ""}{latest["Unaccounted"]} gal
                </span>
              </span>
            </div>
          )}
          {comparisonData.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={comparisonData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis unit=" gal" tick={{ fontSize: 11 }} />
                <Tooltip formatter={(v) => `${v} gal`} />
                <Legend />
                <Line type="monotone" dataKey="Main Meter" stroke="#1d4ed8" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="Household Sum" stroke="#10b981" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="Unaccounted" stroke="#f59e0b" strokeWidth={1.5} strokeDasharray="4 2" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-gray-400 text-sm italic">Add at least 2 MAIN meter readings to see comparison.</p>
          )}
        </div>
      )}

      {/* Line chart — households only */}
      {lineData.length > 0 && (
        <div className="bg-white rounded-md p-4 border border-gray-200">
          <h3 className="text-lg font-semibold mb-3">Household Consumption Over Time</h3>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={lineData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis unit=" gal" tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => `${v} gal`} />
              <Legend />
              {households.map((mi, i) => (
                <Line
                  key={mi}
                  type="monotone"
                  dataKey={mi}
                  stroke={COLORS[i % COLORS.length]}
                  dot={false}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Bar chart — households only */}
      {hasConsumptionData ? (
        <div className="bg-white rounded-md p-4 border border-gray-200">
          <h3 className="text-lg font-semibold mb-3">Latest Consumption by Household</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={barData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="household" tick={{ fontSize: 11 }} />
              <YAxis unit=" gal" tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => `${v} gal`} />
              <Bar dataKey="total" fill="#3b82f6" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="p-4 text-gray-400 text-sm italic bg-white rounded-md border border-gray-200">
          Add at least 2 readings per household to see consumption charts.
        </div>
      )}

      {/* Pie chart — households only */}
      {hasConsumptionData && (
        <div className="bg-white rounded-md p-4 border border-gray-200">
          <h3 className="text-lg font-semibold mb-3">Consumption Share by Household</h3>
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie
                data={pieData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={90}
                label={({ name, percent }) =>
                  percent > 0 ? `${name} (${(percent * 100).toFixed(1)}%)` : ""
                }
              >
                {pieData.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(v) => `${v} gal`} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
