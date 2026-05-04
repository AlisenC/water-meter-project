export default function DashboardSummary({ readings }) {
  const sorted = [...readings].sort(
    (a, b) => new Date(a.record_date) - new Date(b.record_date)
  );

  let total = 0;

  for (let i = 1; i < sorted.length; i++) {
    total += sorted[i].reading - sorted[i - 1].reading;
  }

  return (
    <div className="p-4 bg-blue-50 rounded-md mb-4">
      <h2 className="text-xl font-bold mb-2">Monthly Summary</h2>
      <p>
        Total Consumption: <span className="font-mono">{total} m³</span>
      </p>
      <p>
        Spikes/Leaks: <span className="text-red-500">TBD</span>
      </p>
    </div>
  );
}