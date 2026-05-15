import { useState } from "react";
import { api } from "../api";
import { Database, CheckCircle2, XCircle, Loader2 } from "lucide-react";

export default function OracleSettings({ oracleStatus, onStatusRefresh, apiKey, apiProvider }) {
  const [initLoading, setInitLoading] = useState(false);
  const [initResult, setInitResult] = useState(null);
  const [syncLoading, setSyncLoading] = useState(false);
  const [syncResult, setSyncResult] = useState(null);
  const [embedLoading, setEmbedLoading] = useState(false);
  const [embedResult, setEmbedResult] = useState(null);

  const connected = oracleStatus?.connected;

  async function handleInit() {
    setInitLoading(true);
    setInitResult(null);
    try {
      const res = await api.post("/oracle/init");
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
      const res = await api.post("/oracle/sync");
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
        headers: { "X-Api-Key": apiKey, "X-Api-Provider": apiProvider },
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
          <span
            className={`w-2 h-2 rounded-full ${
              connected ? "bg-green-400" : "bg-gray-300"
            }`}
          />
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
        {/* Not-connected instructions */}
        {!connected && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-sm">
            <p className="font-semibold text-amber-800 mb-1">How to connect Oracle 26ai</p>
            <p className="text-amber-700 text-xs leading-relaxed mb-3">
              Oracle integration is configured via server-side environment variables. Set the following
              on the host running the FastAPI backend before starting the server:
            </p>
            <pre className="bg-white border border-amber-200 rounded px-3 py-2 text-xs font-mono text-gray-700 overflow-x-auto">
{`ORACLE_DSN=hostname:1521/service_name
ORACLE_USER=wm_user
ORACLE_PASSWORD=your_password`}
            </pre>
            {oracleStatus?.error && (
              <p className="text-red-600 text-xs mt-2 font-mono">{oracleStatus.error}</p>
            )}
          </div>
        )}

        {/* Actions (enabled when connected) */}
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
