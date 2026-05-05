const SPIKE_THRESHOLD = 1.5;
const CUBIC_FEET_TO_GALLONS = 7.48052;

function toGallons(reading, unit) {
  return unit === 1 ? reading * CUBIC_FEET_TO_GALLONS : reading;
}

export default function DashboardSummary({ readings }) {
  const groups = {};
  for (const r of readings) {
    if (!groups[r.mi]) groups[r.mi] = [];
    groups[r.mi].push(r);
  }
  for (const mi of Object.keys(groups)) {
    groups[mi].sort((a, b) => new Date(a.record_date) - new Date(b.record_date));
  }

  let grandTotal = 0;
  let spikeCount = 0;

  for (const mi of Object.keys(groups)) {
    const group = groups[mi];
    const deltas = [];
    for (let i = 1; i < group.length; i++) {
      const prev = toGallons(group[i - 1].reading, group[i - 1].unit);
      const curr = toGallons(group[i].reading, group[i].unit);
      deltas.push(Math.max(0, curr - prev));
    }
    grandTotal += deltas.reduce((s, d) => s + d, 0);

    if (deltas.length >= 2) {
      const prev = deltas[deltas.length - 2];
      const curr = deltas[deltas.length - 1];
      if (prev > 0 && curr / prev > 1 + SPIKE_THRESHOLD) spikeCount++;
    }
  }

  grandTotal = parseFloat(grandTotal.toFixed(2));

  return (
    <div className="p-4 bg-blue-50 rounded-md mb-4">
      <h2 className="text-xl font-bold mb-2">Summary</h2>
      <p>
        Total Consumption:{" "}
        <span className="font-mono">{grandTotal} gal</span>
      </p>
      <p>
        Spikes:{" "}
        <span className={spikeCount > 0 ? "text-orange-500 font-semibold" : "text-green-600"}>
          {spikeCount > 0
            ? `${spikeCount} household${spikeCount > 1 ? "s" : ""} flagged`
            : "None detected"}
        </span>
      </p>
    </div>
  );
}
