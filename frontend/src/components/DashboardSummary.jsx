function monthLabel(year, month) {
  return new Date(year, month - 1, 1).toLocaleDateString("en-AU", {
    month: "long",
    year: "numeric",
  });
}

export default function DashboardSummary({
  anomalies = [],
  billingStatements = [],
  verificationData = [],
}) {
  const latestBilling = billingStatements.length > 0 ? billingStatements[0] : null;
  const latestVerification = latestBilling
    ? verificationData.find((v) => v.billing_statement_id === latestBilling.id)
    : null;

  const billingPeriodLabel = latestBilling
    ? (() => {
        const start = monthLabel(latestBilling.billing_year, latestBilling.billing_month);
        const sameMonth =
          !latestBilling.period_end_month ||
          (latestBilling.period_end_month === latestBilling.billing_month &&
            latestBilling.period_end_year === latestBilling.billing_year);
        return sameMonth
          ? start
          : `${start} – ${monthLabel(latestBilling.period_end_year, latestBilling.period_end_month)}`;
      })()
    : null;

  const verifyColor =
    !latestVerification || !latestVerification.has_sufficient_readings
      ? "bg-gray-50 border-gray-200 text-gray-500"
      : Math.abs(latestVerification.discrepancy_kl) < 0.5
      ? "bg-green-50 border-green-200 text-green-800"
      : "bg-orange-50 border-orange-300 text-orange-800";

  return (
    <div className="p-4 bg-blue-50 rounded-md mb-4">
      <h2 className="text-xl font-bold mb-3">Summary</h2>

      {/* Primary: Billing Statement */}
      {latestBilling ? (
        <div className="mb-3">
          <p className="text-xs text-gray-500 uppercase tracking-wide font-semibold mb-1">
            Billing Statement — {billingPeriodLabel}
          </p>
          <p className="text-3xl font-mono font-bold text-blue-700">
            {latestBilling.total_consumption_kl.toFixed(3)} kL
          </p>
          <p className="text-sm text-gray-600 mt-0.5">
            Cost:{" "}
            <span className="font-mono font-semibold">
              ${latestBilling.billing_cost_aud.toFixed(2)} AUD
            </span>
            {latestBilling.source_filename && (
              <span className="text-gray-400 ml-2 text-xs">{latestBilling.source_filename}</span>
            )}
          </p>
        </div>
      ) : (
        <p className="text-gray-400 italic text-sm mb-3">No billing statement imported yet.</p>
      )}

      {/* Verification against main meter */}
      {latestVerification && (
        <div className={`mb-3 px-3 py-2 rounded border text-sm ${verifyColor}`}>
          <p className="font-semibold mb-0.5">Household Sum Verification</p>
          {latestVerification.has_sufficient_readings ? (
            <>
              <p>
                Household sum:{" "}
                <span className="font-mono">{latestVerification.household_sum_kl} kL</span>
              </p>
              <p>
                Discrepancy:{" "}
                <span className="font-mono font-semibold">
                  {latestVerification.discrepancy_kl > 0 ? "+" : ""}
                  {latestVerification.discrepancy_kl} kL
                </span>
                {" — "}
                {Math.abs(latestVerification.discrepancy_kl) < 0.5
                  ? "readings match statement"
                  : "readings differ from statement"}
              </p>
            </>
          ) : (
            <p className="italic text-sm">Insufficient household readings for this billing period.</p>
          )}
        </div>
      )}

      {/* Spikes */}
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
