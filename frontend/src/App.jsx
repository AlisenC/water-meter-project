import { useState, useEffect, useCallback } from "react";
import { Toaster } from "react-hot-toast";
import { api } from "./api";
import AIAssistant from "./components/AIAssistant";
import ReadingTable from "./components/ReadingTable";
import DashboardSummary from "./components/DashboardSummary";
import UsageCharts from "./components/UsageCharts";
import MoneyLostChart from "./components/MoneyLostChart";
import DataQuality from "./components/DataQuality";
import StatementUpload from "./components/StatementUpload";
import ApiKeySettings from "./components/ApiKeySettings";
import ImportWizard from "./components/ImportWizard";
import Sidebar from "./components/Sidebar";
import OracleSettings from "./components/OracleSettings";
import LeakDetectionTool from "./components/LeakDetectionTool";

const LS_KEY = "wm_api_key";
const LS_PROVIDER = "wm_api_provider";
const LS_ORACLE_PROFILE = "wm_oracle_profile_id";

const SECTIONS = {
  overview: {
    title: "Overview",
    description: "At-a-glance summary of your latest bill, verification status, and usage alerts.",
  },
  analysis: {
    title: "Analysis",
    description: "Interactive charts and spike detection across all meters.",
  },
  statements: {
    title: "Bill Statements",
    description: "Import and browse PDF billing statements.",
  },
  readings: {
    title: "Readings",
    description: "Import CSV meter readings, and search, filter, and manage individual readings.",
  },
  leak: {
    title: "Daily Leak Detection",
    description: "Track daily submeter and main meter readings to spot potential leaks, independent of monthly billing.",
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
  const [oracleProfileId, setOracleProfileId] = useState(
    () => Number(localStorage.getItem(LS_ORACLE_PROFILE)) || null
  );

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
    const profileId = Number(localStorage.getItem(LS_ORACLE_PROFILE)) || null;
    try {
      const res = await api.get("/oracle/status", {
        headers: {
          ...(profileId && { "X-Oracle-Profile-Id": String(profileId) }),
        },
      });
      setOracleStatus(res.data);
    } catch {
      setOracleStatus({ connected: false, error: "Backend unreachable" });
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- pre-existing, out of scope for this change
    checkOracleStatus();
    const id = setInterval(checkOracleStatus, 30_000);
    return () => clearInterval(id);
  }, [checkOracleStatus]);

  function handleProfileSelect(id) {
    setOracleProfileId(id);
    if (id) {
      localStorage.setItem(LS_ORACLE_PROFILE, String(id));
    } else {
      localStorage.removeItem(LS_ORACLE_PROFILE);
    }
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
              <MoneyLostChart verificationData={verificationData} />
              <DataQuality importReport={lastImportReport} anomalies={anomalies} />
            </div>
          )}

          {activeSection === "statements" && (
            <StatementUpload
              billingStatements={billingStatements}
              verificationData={verificationData}
              apiKey={apiKey}
              apiProvider={apiProvider}
              onImportSuccess={refreshBillingData}
              onDelete={handleBillingDelete}
              onUpdate={refreshBillingData}
            />
          )}

          {activeSection === "readings" && (
            <div className="space-y-4">
              <button
                onClick={() => setShowImportWizard(true)}
                className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg font-medium text-sm transition-colors"
              >
                Import CSV Data
              </button>
              <ReadingTable readings={readings} setReadings={setReadings} />
            </div>
          )}

          {activeSection === "leak" && <LeakDetectionTool />}

          {activeSection === "ai" && (
            <AIAssistant
              oracleStatus={oracleStatus}
              apiKey={apiKey}
              apiProvider={apiProvider}
              oracleProfileId={oracleProfileId}
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
                onProfileSelect={handleProfileSelect}
                oracleProfileId={oracleProfileId}
                apiKey={apiKey}
                apiProvider={apiProvider}
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
