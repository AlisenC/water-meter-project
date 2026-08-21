import { TrendingUp, DollarSign, Zap, Receipt } from "lucide-react";
import { DISCREPANCY_TOLERANCE_UNITS } from "../utils/billing";

function monthLabel(year, month) {
  return new Date(year, month - 1, 1).toLocaleDateString("en-AU", {
    month: "long",
    year: "numeric",
  });
}

function StatCard({ icon: Icon, iconColor, label, value, sub, accent }) {
  const accents = {
    blue:   "border-t-blue-500",
    indigo: "border-t-indigo-500",
    green:  "border-t-green-500",
    orange: "border-t-orange-500",
  };
  return (
    <div className={`bg-white rounded-xl border border-gray-200 shadow-sm pt-0 overflow-hidden border-t-4 ${accents[accent] ?? accents.blue}`}>
      <div className="px-5 py-4">
        <div className="flex items-center justify-between mb-3">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">{label}</p>
          <div className={`p-2 rounded-lg ${iconColor}`}>
            <Icon size={15} />
          </div>
        </div>
        <p className="text-2xl font-bold text-gray-900 font-mono">{value}</p>
        {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
      </div>
    </div>
  );
}

export default function DashboardSummary({
  anomalies = [],
  billingStatements = [],
  verificationData = [],
}) {
  // Skip needs-review stubs (no known billing period yet) rather than relying on
  // the backend's NULLS-last ordering to keep them out of the "latest" slot.
  const latestBilling =
    billingStatements.find((s) => s.billing_month != null && s.billing_year != null) ?? null;
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

  const spikeCount = anomalies.length;
  const spikeAccent = spikeCount === 0 ? "green" : "orange";

  const verifyOk =
    latestVerification?.has_sufficient_readings &&
    Math.abs(latestVerification.discrepancy_units) < DISCREPANCY_TOLERANCE_UNITS;
  const verifyStyles = !latestVerification || !latestVerification.has_sufficient_readings
    ? "bg-gray-50 border-gray-200 text-gray-500"
    : verifyOk
    ? "bg-green-50 border-green-200 text-green-800"
    : "bg-orange-50 border-orange-300 text-orange-800";

  return (
    <div className="space-y-6">
      {/* Stat card grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={TrendingUp}
          iconColor="bg-blue-100 text-blue-600"
          label="Latest Consumption"
          value={latestBilling?.total_units_consumed != null ? `${latestBilling.total_units_consumed.toFixed(2)} units` : "—"}
          sub={billingPeriodLabel ?? "No statement imported"}
          accent="blue"
        />
        <StatCard
          icon={DollarSign}
          iconColor="bg-indigo-100 text-indigo-600"
          label="Billing Cost"
          value={latestBilling?.total_cost != null ? `$${latestBilling.total_cost.toFixed(2)}` : "—"}
          sub={latestBilling ? "USD" : "No statement imported"}
          accent="indigo"
        />
        <StatCard
          icon={Receipt}
          iconColor="bg-green-100 text-green-600"
          label="Cost per Unit"
          value={latestBilling?.cost_per_unit != null ? `$${latestBilling.cost_per_unit.toFixed(2)}` : "—"}
          sub={latestBilling ? "per unit of water (748 gal)" : "No statement imported"}
          accent="green"
        />
        <StatCard
          icon={Zap}
          iconColor={spikeCount === 0 ? "bg-green-100 text-green-600" : "bg-orange-100 text-orange-600"}
          label="Usage Spikes"
          value={spikeCount === 0 ? "None" : String(spikeCount)}
          sub={spikeCount === 0 ? "No anomalies detected" : `${spikeCount} anomal${spikeCount === 1 ? "y" : "ies"} detected`}
          accent={spikeAccent}
        />
      </div>

      {/* Verification strip */}
      {latestVerification && (
        <div className={`rounded-lg border px-5 py-4 text-sm ${verifyStyles}`}>
          <p className="font-semibold mb-1">Household Sum Verification</p>
          {latestVerification.has_sufficient_readings ? (
            <div className="flex flex-wrap gap-6">
              <span>
                Household sum:{" "}
                <span className="font-mono font-semibold">{latestVerification.household_sum_units} units</span>
              </span>
              <span>
                Discrepancy:{" "}
                <span className="font-mono font-semibold">
                  {latestVerification.discrepancy_units > 0 ? "+" : ""}
                  {latestVerification.discrepancy_units} units
                </span>
                {" · "}
                {verifyOk ? "readings match statement" : "readings differ from statement"}
              </span>
              {latestVerification.money_lost != null && (
                <span>
                  Money lost:{" "}
                  <span className="font-mono font-semibold">
                    {latestVerification.money_lost > 0 ? "+" : ""}
                    ${latestVerification.money_lost.toFixed(2)}
                  </span>
                </span>
              )}
            </div>
          ) : (
            <p className="italic text-sm">Insufficient household readings for this billing period.</p>
          )}
        </div>
      )}

      {/* Spike detail cards */}
      {anomalies.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-5 py-3 bg-gray-50 border-b border-gray-200">
            <h3 className="text-sm font-semibold text-gray-700">Spike Details</h3>
          </div>
          <ul className="divide-y divide-gray-100">
            {anomalies.map((a, i) => (
              <li key={i} className="px-5 py-3 flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold text-gray-900">{a.mi}</p>
                  {a.is_gap_induced && (
                    <p className="text-xs text-gray-400 mt-0.5">
                      Gap-induced: {a.gap_days}d gap vs {a.median_interval_days}d median
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-3 flex-shrink-0">
                  <span className="text-xs text-gray-500">
                    {new Date(a.current_period_end).toLocaleDateString("en-AU", { month: "short", year: "numeric" })}
                  </span>
                  <span
                    className={`text-xs font-semibold px-2.5 py-1 rounded-full ${
                      a.is_gap_induced
                        ? "bg-yellow-100 text-yellow-700"
                        : "bg-orange-100 text-orange-700"
                    }`}
                  >
                    +{a.percent_increase}%
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
