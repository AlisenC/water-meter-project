const CUBIC_FEET_TO_GALLONS = 7.48052;

function toGallons(reading, unit) {
  return unit === 1 ? reading * CUBIC_FEET_TO_GALLONS : reading;
}

export default function DashboardSummary({ readings, anomalies = [] }) {
  const groups = {};
  for (const r of readings) {
    if (!groups[r.mi]) groups[r.mi] = [];
    groups[r.mi].push(r);
  }
  for (const mi of Object.keys(groups)) {
    groups[mi].sort((a, b) => new Date(a.record_date) - new Date(b.record_date));
  }

  let householdTotal = 0;
  let mainTotal = 0;
  for (const mi of Object.keys(groups)) {
    const group = groups[mi];
    for (let i = 1; i < group.length; i++) {
      const prev = toGallons(group[i - 1].reading, group[i - 1].unit);
      const curr = toGallons(group[i].reading, group[i].unit);
      const delta = Math.max(0, curr - prev);
      if (mi === "MAIN") mainTotal += delta;
      else householdTotal += delta;
    }
  }
  householdTotal = parseFloat(householdTotal.toFixed(2));
  mainTotal = parseFloat(mainTotal.toFixed(2));

  return (
    <div className="p-4 bg-blue-50 rounded-md mb-4">
      <h2 className="text-xl font-bold mb-2">Summary</h2>
      <div className="flex gap-6 mb-2">
        <p>
          Household Consumption:{" "}
          <span className="font-mono font-semibold">{householdTotal} gal</span>
        </p>
        <p>
          Main Meter:{" "}
          <span className="font-mono font-semibold">{mainTotal} gal</span>
        </p>
      </div>
      <div>
        <p className="font-semibold mb-1">
          Spikes:{" "}
          {anomalies.length === 0 && (
            <span className="text-green-600 font-normal">None detected</span>
          )}
        </p>
        {anomalies.length > 0 && (
          <ul className="space-y-1">
            {anomalies.map((a, i) => (
              <li
                key={i}
                className={`text-sm px-2 py-1 rounded border ${
                  a.is_gap_induced
                    ? "bg-yellow-50 text-yellow-800 border-yellow-300"
                    : "bg-orange-50 text-orange-800 border-orange-300"
                }`}
              >
                <span className="font-semibold">{a.household}</span>
                {" — "}
                {a.increase_percent}% spike on{" "}
                {new Date(a.reading_date).toLocaleDateString("en-AU", {
                  month: "short",
                  day: "numeric",
                  year: "numeric",
                })}
                {a.is_gap_induced && (
                  <span className="ml-2 text-xs italic">
                    (gap-induced: {a.gap_days}d gap vs {a.median_interval_days}d median)
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
