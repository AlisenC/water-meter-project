import { useState, useEffect, useCallback } from "react";
import { Toaster } from "react-hot-toast";
import { api } from "./api";
import AIAssistant from "./components/AIAssistant";
import ReadingTable from "./components/ReadingTable";
import DashboardSummary from "./components/DashboardSummary";
import UsageCharts from "./components/UsageCharts";
import DataQuality from "./components/DataQuality";
import BillingImport from "./components/BillingImport";
import ApiKeySettings from "./components/ApiKeySettings";
import ImportWizard from "./components/ImportWizard";
import Sidebar from "./components/Sidebar";
import OracleSettings from "./components/OracleSettings";

const LS_KEY = "wm_api_key";
const LS_PROVIDER = "wm_api_provider";
const LS_ORACLE_DSN = "wm_oracle_dsn";
const LS_ORACLE_USER = "wm_oracle_user";
const LS_ORACLE_PASSWORD = "wm_oracle_password";

const SECTIONS = {
  overview: {
    title: "Overview",
    description: "At-a-glance summary of your latest bill, verification status, and usage alerts.",
  },
  analysis: {
    title: "Analysis",
    description: "Interactive charts and spike detection across all meters.",
  },
  bills: {
    title: "Bills & Imports",
    description: "Import and manage PDF bills and CSV meter readings.",
  },
  readings: {
    title: "Readings",
    description: "Search, filter, and manage individual meter readings.",
  },
  ai: {
    title: "AI Assistant",
    description: "Chat with AI, query Oracle with natural language, or run semantic vector search.",
  },
  settings: {
    title: "Settings",
    description: "Configure your AI provider and Oracle 26ai connection.",
  },
};

function App() {
  const [readings, setReadings] = useState([]);
  const [anomalies, setAnomalies] = useState([]);
  const [billingStatements, setBillingStatements] = useState([]);
  const [verificationData, setVerificationData] = useState([]);
  const [showImportWizard, setShowImportWizard] = useState(false);
  const [lastImportReport, setLastImportReport] = useState(null);
  const [apiKey, setApiKey] = useState(() => localStorage.getItem(LS_KEY) || "");
  const [apiProvider, setApiProvider] = useState(
    () => localStorage.getItem(LS_PROVIDER) || "anthropic"
  );
  const [activeSection, setActiveSection] = useState("overview");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [oracleStatus, setOracleStatus] = useState(null);
  const [oracleDsn, setOracleDsn] = useState(() => localStorage.getItem(LS_ORACLE_DSN) || "");
  const [oracleUser, setOracleUser] = useState(() => localStorage.getItem(LS_ORACLE_USER) || "");
  const [oraclePassword, setOraclePassword] = useState(() => localStorage.getItem(LS_ORACLE_PASSWORD) || "");

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

  const checkOracleStatus = useCallback(async () => {
    const dsn = localStorage.getItem(LS_ORACLE_DSN) || "";
    const user = localStorage.getItem(LS_ORACLE_USER) || "";
    const password = localStorage.getItem(LS_ORACLE_PASSWORD) || "";
    try {
      const res = await api.get("/oracle/status", {
        headers: {
          ...(dsn && { "X-Oracle-Dsn": dsn }),
          ...(user && { "X-Oracle-User": user }),
          ...(password && { "X-Oracle-Password": password }),
        },
      });
      setOracleStatus(res.data);
    } catch {
      setOracleStatus({ connected: false, error: "Backend unreachable" });
    }
  }, []);

  useEffect(() => {
    checkOracleStatus();
    const id = setInterval(checkOracleStatus, 30_000);
    return () => clearInterval(id);
  }, [checkOracleStatus]);

  function handleCredentialsChange(dsn, user, password) {
    setOracleDsn(dsn);
    setOracleUser(user);
    setOraclePassword(password);
  }

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
    setVerificationData((prev) =>
      prev.filter((v) => v.billing_statement_id !== deletedId)
    );
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

  const section = SECTIONS[activeSection];

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      <Toaster
        position="top-right"
        toastOptions={{
          duration: 4000,
          style: { fontSize: "0.875rem", maxWidth: "380px" },
        }}
      />

      <Sidebar
        activeSection={activeSection}
        onNavigate={setActiveSection}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((v) => !v)}
        anomalyCount={anomalies.length}
        billingCount={billingStatements.length}
        apiKeySet={!!apiKey}
        oracleConnected={oracleStatus?.connected ?? false}
      />

      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Topbar */}
        <header className="bg-white border-b border-gray-200 px-6 py-4 flex-shrink-0">
          <h1 className="text-xl font-bold text-gray-900 truncate">{section.title}</h1>
          <p className="text-sm text-gray-500 mt-0.5 truncate">{section.description}</p>
        </header>

        {/* Scrollable content */}
        <main className="flex-1 overflow-y-auto p-6">
          {activeSection === "overview" && (
            <DashboardSummary
              anomalies={anomalies}
              billingStatements={billingStatements}
              verificationData={verificationData}
            />
          )}

          {activeSection === "analysis" && (
            <div className="space-y-6">
              <UsageCharts readings={readings} />
              <DataQuality importReport={lastImportReport} anomalies={anomalies} />
            </div>
          )}

          {activeSection === "bills" && (
            <div className="space-y-4">
              <BillingImport
                billingStatements={billingStatements}
                verificationData={verificationData}
                apiKey={apiKey}
                apiProvider={apiProvider}
                onImportSuccess={refreshBillingData}
                onDelete={handleBillingDelete}
              />
              <button
                onClick={() => setShowImportWizard(true)}
                className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg font-medium text-sm transition-colors"
              >
                Import CSV Data
              </button>
            </div>
          )}

          {activeSection === "readings" && (
            <ReadingTable readings={readings} setReadings={setReadings} />
          )}

          {activeSection === "ai" && (
            <AIAssistant
              oracleStatus={oracleStatus}
              apiKey={apiKey}
              apiProvider={apiProvider}
              oracleDsn={oracleDsn}
              oracleUser={oracleUser}
              oraclePassword={oraclePassword}
              onNavigateSettings={() => setActiveSection("settings")}
            />
          )}

          {activeSection === "settings" && (
            <div className="space-y-6">
              <ApiKeySettings
                apiKey={apiKey}
                apiProvider={apiProvider}
                onSave={(key, provider) => {
                  setApiKey(key);
                  setApiProvider(provider);
                }}
                onClear={() => {
                  setApiKey("");
                  setApiProvider("anthropic");
                }}
              />
              <OracleSettings
                oracleStatus={oracleStatus}
                onStatusRefresh={checkOracleStatus}
                onCredentialsChange={handleCredentialsChange}
                apiKey={apiKey}
                apiProvider={apiProvider}
                oracleDsn={oracleDsn}
                oracleUser={oracleUser}
                oraclePassword={oraclePassword}
              />
            </div>
          )}
        </main>
      </div>

      {showImportWizard && (
        <ImportWizard
          onImportSuccess={handleImportSuccess}
          onClose={() => setShowImportWizard(false)}
        />
      )}
    </div>
  );
}

export default App;
