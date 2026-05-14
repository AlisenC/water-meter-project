import { useState, useEffect } from "react";
import { api } from "./api";
import AIChat from "./components/AIChat";
import ReadingTable from "./components/ReadingTable";
import DashboardSummary from "./components/DashboardSummary";
import UsageCharts from "./components/UsageCharts";
import DataQuality from "./components/DataQuality";
import BillingImport from "./components/BillingImport";
import ApiKeySettings from "./components/ApiKeySettings";
import ImportWizard from "./components/ImportWizard";

const LS_KEY = "wm_api_key";
const LS_PROVIDER = "wm_api_provider";

function App() {
  const [readings, setReadings] = useState([]);
  const [anomalies, setAnomalies] = useState([]);
  const [billingStatements, setBillingStatements] = useState([]);
  const [verificationData, setVerificationData] = useState([]);
  const [showImportWizard, setShowImportWizard] = useState(false);
  const [lastImportReport, setLastImportReport] = useState(null);
  const [apiKey, setApiKey] = useState(() => localStorage.getItem(LS_KEY) || "");
  const [apiProvider, setApiProvider] = useState(() => localStorage.getItem(LS_PROVIDER) || "anthropic");

  useEffect(() => {
    Promise.all([
      api.get("/readings"),
      api.get("/anomalies"),
      api.get("/billing-statements"),
      api.get("/billing-verify"),
    ]).then(([readingsRes, anomaliesRes, billingsRes, verifyRes]) => {
      setReadings(readingsRes.data);
      setAnomalies(anomaliesRes.data);
      setBillingStatements(billingsRes.data);
      setVerificationData(verifyRes.data);
    });
  }, []);

  async function refreshBillingData() {
    const [billingsRes, verifyRes] = await Promise.all([
      api.get("/billing-statements"),
      api.get("/billing-verify"),
    ]);
    setBillingStatements(billingsRes.data);
    setVerificationData(verifyRes.data);
  }

  function handleBillingDelete(deletedId) {
    setBillingStatements((prev) => prev.filter((s) => s.id !== deletedId));
    setVerificationData((prev) => prev.filter((v) => v.billing_statement_id !== deletedId));
  }

  async function handleImportSuccess(resultData) {
    setLastImportReport(resultData);
    const [updatedReadings, updatedAnomalies] = await Promise.all([
      api.get("/readings"),
      api.get("/anomalies"),
    ]);
    setReadings(updatedReadings.data);
    setAnomalies(updatedAnomalies.data);
    setShowImportWizard(false);
  }

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">Water Meter Dashboard</h1>

      <ApiKeySettings
        apiKey={apiKey}
        apiProvider={apiProvider}
        onSave={(key, provider) => { setApiKey(key); setApiProvider(provider); }}
        onClear={() => { setApiKey(""); setApiProvider("anthropic"); }}
      />

      <DashboardSummary
        anomalies={anomalies}
        billingStatements={billingStatements}
        verificationData={verificationData}
      />

      <UsageCharts readings={readings} />

      <BillingImport
        billingStatements={billingStatements}
        verificationData={verificationData}
        apiKey={apiKey}
        apiProvider={apiProvider}
        onImportSuccess={refreshBillingData}
        onDelete={handleBillingDelete}
      />

      <AIChat apiKey={apiKey} apiProvider={apiProvider} />

      <button
        onClick={() => setShowImportWizard(true)}
        className="mb-4 bg-green-500 hover:bg-green-600 text-white px-4 py-2 rounded"
      >
        Import CSV Data
      </button>

      {showImportWizard && (
        <ImportWizard
          onImportSuccess={handleImportSuccess}
          onClose={() => setShowImportWizard(false)}
        />
      )}

      <DataQuality importReport={lastImportReport} anomalies={anomalies} />

      <ReadingTable readings={readings} setReadings={setReadings} />
    </div>
  );
}

export default App;
