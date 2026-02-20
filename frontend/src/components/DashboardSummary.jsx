export default function DashboardSummary({ readings }) {
  const total = readings.reduce((sum, r) => sum + r.amount, 0);

  return (
    <div className="p-4 bg-blue-50 rounded-md mb-4">
      <h2 className="text-xl font-bold mb-2">Monthly Summary</h2>
      <p>Total Consumption: <span className="font-mono">{total} m³</span></p>
      <p>Spikes/Leaks: <span className="text-red-500">TBD</span></p>
    </div>
  );
}
