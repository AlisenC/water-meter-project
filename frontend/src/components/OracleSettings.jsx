import { useState } from "react";
import { api } from "../api";
import { Database, CheckCircle2, XCircle, Loader2, ChevronDown, ChevronUp } from "lucide-react";

const LS_DSN = "wm_oracle_dsn";
const LS_USER = "wm_oracle_user";
const LS_PASSWORD = "wm_oracle_password";

export default function OracleSettings({
  oracleStatus,
  onStatusRefresh,
  onCredentialsChange,
  apiKey,
  apiProvider,
  oracleDsn,
  oracleUser,
  oraclePassword,
}) {
  const [draftDsn, setDraftDsn] = useState(oracleDsn || "");
  const [draftUser, setDraftUser] = useState(oracleUser || "");
  const [draftPassword, setDraftPassword] = useState(oraclePassword || "");
  const [serverHelpOpen, setServerHelpOpen] = useState(false);

  const [initLoading, setInitLoading] = useState(false);
  const [initResult, setInitResult] = useState(null);
  const [syncLoading, setSyncLoading] = useState(false);
  const [syncResult, setSyncResult] = useState(null);
  const [embedLoading, setEmbedLoading] = useState(false);
  const [embedResult, setEmbedResult] = useState(null);

  const connected = oracleStatus?.connected;

  function oracleHeaders() {
    return {
      ...(oracleDsn && { "X-Oracle-Dsn": oracleDsn }),
      ...(oracleUser && { "X-Oracle-User": oracleUser }),
      ...(oraclePassword && { "X-Oracle-Password": oraclePassword }),
    };
  }

  function handleSave() {
    localStorage.setItem(LS_DSN, draftDsn.trim());
    localStorage.setItem(LS_USER, draftUser.trim());
    localStorage.setItem(LS_PASSWORD, draftPassword);
    onCredentialsChange(draftDsn.trim(), draftUser.trim(), draftPassword);
    onStatusRefresh();
  }

  function handleClear() {
    localStorage.removeItem(LS_DSN);
    localStorage.removeItem(LS_USER);
    localStorage.removeItem(LS_PASSWORD);
    setDraftDsn("");
    setDraftUser("");
    setDraftPassword("");
    onCredentialsChange("", "", "");
    onStatusRefresh();
  }

  async function handleInit() {
    setInitLoading(true);
    setInitResult(null);
    try {
      const res = await api.post("/oracle/init", null, { headers: oracleHeaders() });
      setInitResult({ ok: true, message: res.data.message });
    } catch (err) {
      setInitResult({ ok: false, message: err.response?.data?.detail ?? "Failed." });
    } finally {
      setInitLoading(false);
    }
  }

  async function handleSync() {
    setSyncLoading(true);
    setSyncResult(null);
    try {
      const res = await api.post("/oracle/sync", null, { headers: oracleHeaders() });
      setSyncResult({
        ok: true,
        message: `Synced ${res.data.synced_readings} readings and ${res.data.synced_bills} bills.`,
      });
    } catch (err) {
      setSyncResult({ ok: false, message: err.response?.data?.detail ?? "Sync failed." });
    } finally {
      setSyncLoading(false);
    }
  }

  async function handleEmbedSync() {
    if (!apiKey) {
      setEmbedResult({ ok: false, message: "No AI API key configured. Add one in AI Provider Settings." });
      return;
    }
    setEmbedLoading(true);
    setEmbedResult(null);
    try {
      const res = await api.post("/oracle/embed-sync", null, {
        headers: {
          "X-Api-Key": apiKey,
          "X-Api-Provider": apiProvider,
          ...oracleHeaders(),
        },
      });
      setEmbedResult({
        ok: true,
        message: `Generated embeddings for ${res.data.embedded} readings using ${res.data.provider} (${res.data.dims} dims).`,
      });
    } catch (err) {
      setEmbedResult({ ok: false, message: err.response?.data?.detail ?? "Embedding failed." });
    } finally {
      setEmbedLoading(false);
    }
  }

  function ResultPill({ result }) {
    if (!result) return null;
    return (
      <span
        className={`inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full ${
          result.ok
            ? "bg-green-50 text-green-700 border border-green-200"
            : "bg-red-50 text-red-700 border border-red-200"
        }`}
      >
        {result.ok ? <CheckCircle2 size={11} /> : <XCircle size={11} />}
        {result.message}
      </span>
    );
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-5 py-3 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Database size={16} className="text-indigo-600" />
          <h3 className="font-semibold text-gray-800 text-sm">Oracle 26ai Connection</h3>
        </div>
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${connected ? "bg-green-400" : "bg-gray-300"}`} />
          <span className={`text-xs font-medium ${connected ? "text-green-700" : "text-gray-500"}`}>
            {connected ? "Connected" : "Not connected"}
          </span>
          <button
            onClick={onStatusRefresh}
            className="text-xs text-blue-600 hover:text-blue-800 underline ml-2"
          >
            Refresh
          </button>
        </div>
      </div>

      <div className="p-5 space-y-5">
        {/* Credential input fields */}
        <div className="space-y-3">
          <p className="text-xs text-gray-500 leading-relaxed">
            Enter your Oracle connection details. Credentials are stored in this browser only and sent
            directly to the backend — never persisted on the server.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-600">DSN</label>
              <input
                className="border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                value={draftDsn}
                onChange={(e) => setDraftDsn(e.target.value)}
                placeholder="host:1521/service"
                autoComplete="off"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-600">Username</label>
              <input
                className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                value={draftUser}
                onChange={(e) => setDraftUser(e.target.value)}
                placeholder="wm_user"
                autoComplete="off"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-600">Password</label>
              <input
                type="password"
                className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                value={draftPassword}
                onChange={(e) => setDraftPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete="new-password"
              />
            </div>
          </div>

          <div className="flex gap-2 items-center">
            <button
              onClick={handleSave}
              disabled={!draftDsn.trim() || !draftUser.trim() || !draftPassword}
              className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-1.5 rounded-lg text-xs font-medium disabled:opacity-50 transition-colors"
            >
              Save & Test Connection
            </button>
            {(oracleDsn || oracleUser) && (
              <button
                onClick={handleClear}
                className="text-red-500 hover:text-red-700 text-xs underline"
              >
                Clear
              </button>
            )}
          </div>

          {oracleStatus?.error && !connected && (
            <p className="text-red-600 text-xs font-mono">{oracleStatus.error}</p>
          )}
        </div>

        {/* Server-side env vars accordion */}
        <div className="border border-gray-100 rounded-lg overflow-hidden">
          <button
            onClick={() => setServerHelpOpen((v) => !v)}
            className="w-full flex items-center justify-between px-4 py-2.5 bg-gray-50 text-xs font-medium text-gray-600 hover:bg-gray-100 transition-colors"
          >
            <span>Using server-side env vars instead?</span>
            {serverHelpOpen ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          </button>
          {serverHelpOpen && (
            <div className="px-4 py-3 text-xs text-gray-600 space-y-2 bg-white">
              <p>
                Set these on the host running the FastAPI backend before starting the server. When env vars are
                present, the UI credentials above are not required.
              </p>
              <pre className="bg-gray-50 border border-gray-200 rounded px-3 py-2 font-mono text-gray-700 overflow-x-auto">
{`ORACLE_DSN=hostname:1521/service_name
ORACLE_USER=wm_user
ORACLE_PASSWORD=your_password`}
              </pre>
            </div>
          )}
        </div>

        {/* Action buttons */}
        <div className="space-y-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-gray-800">Initialize Tables</p>
              <p className="text-xs text-gray-500 mt-0.5">
                Create Oracle tables (wm_readings, wm_billing_statements, wm_readings_vectors). Safe to run multiple times.
              </p>
            </div>
            <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
              <button
                onClick={handleInit}
                disabled={!connected || initLoading}
                className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white px-3 py-1.5 rounded-lg text-xs font-medium disabled:opacity-50 transition-colors"
              >
                {initLoading && <Loader2 size={12} className="animate-spin" />}
                Initialize
              </button>
              <ResultPill result={initResult} />
            </div>
          </div>

          <div className="border-t border-gray-100" />

          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-gray-800">Sync Data</p>
              <p className="text-xs text-gray-500 mt-0.5">
                Mirror all SQLite readings and billing statements to Oracle tables using MERGE (upsert).
              </p>
            </div>
            <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
              <button
                onClick={handleSync}
                disabled={!connected || syncLoading}
                className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded-lg text-xs font-medium disabled:opacity-50 transition-colors"
              >
                {syncLoading && <Loader2 size={12} className="animate-spin" />}
                Sync Now
              </button>
              <ResultPill result={syncResult} />
            </div>
          </div>

          <div className="border-t border-gray-100" />

          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-gray-800">Generate Embeddings</p>
              <p className="text-xs text-gray-500 mt-0.5">
                Embed all readings using your configured AI provider and store in Oracle VECTOR columns.
                Required for Semantic Search.{" "}
                <span className="font-medium">
                  {apiProvider === "openai" ? "Uses OpenAI text-embedding-3-small (1536d)." : "Uses Voyage voyage-3 (1024d)."}
                </span>
              </p>
            </div>
            <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
              <button
                onClick={handleEmbedSync}
                disabled={!connected || !apiKey || embedLoading}
                className="flex items-center gap-2 bg-purple-600 hover:bg-purple-700 text-white px-3 py-1.5 rounded-lg text-xs font-medium disabled:opacity-50 transition-colors"
              >
                {embedLoading && <Loader2 size={12} className="animate-spin" />}
                Embed & Sync
              </button>
              <ResultPill result={embedResult} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
