import { useState, useEffect } from "react";
import { api } from "../api";
import {
  Database, CheckCircle2, XCircle, Loader2,
  Plus, Trash2, Upload,
} from "lucide-react";

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

// ─── New profile form (2-step wallet upload) ──────────────────────────────── //

function NewProfileForm({ onSaved, onCancel }) {
  const [walletFile, setWalletFile] = useState(null);
  const [parsing, setParsing] = useState(false);
  const [parseError, setParseError] = useState(null);
  const [services, setServices] = useState([]);
  const [tempId, setTempId] = useState(null);

  const [name, setName] = useState("");
  const [serviceName, setServiceName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [walletPassword, setWalletPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);

  async function handleParse() {
    if (!walletFile) return;
    setParsing(true);
    setParseError(null);
    try {
      const form = new FormData();
      form.append("file", walletFile);
      const res = await api.post("/oracle/wallet/parse", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setServices(res.data.services);
      setTempId(res.data.temp_id);
      if (res.data.services.length > 0) setServiceName(res.data.services[0]);
    } catch (err) {
      setParseError(err.response?.data?.detail ?? "Failed to parse wallet.");
    } finally {
      setParsing(false);
    }
  }

  async function handleSave() {
    if (!name.trim() || !serviceName || !username.trim() || !password || !tempId) return;
    setSaving(true);
    setSaveError(null);
    try {
      const form = new FormData();
      form.append("name", name.trim());
      form.append("service_name", serviceName);
      form.append("username", username.trim());
      form.append("password", password);
      form.append("temp_id", tempId);
      if (walletPassword) form.append("wallet_password", walletPassword);
      await api.post("/oracle/profiles", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      onSaved();
    } catch (err) {
      setSaveError(err.response?.data?.detail ?? "Failed to save profile.");
    } finally {
      setSaving(false);
    }
  }

  const step2Ready = services.length > 0 && tempId;

  return (
    <div className="space-y-5">
      {/* Step 1 */}
      <div className="space-y-3">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Step 1 — Upload wallet ZIP</p>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 cursor-pointer border border-gray-300 rounded-lg px-4 py-2 text-sm text-gray-600 hover:bg-gray-50 transition-colors">
            <Upload size={14} />
            {walletFile ? walletFile.name : "Choose wallet .zip"}
            <input
              type="file"
              accept=".zip"
              className="hidden"
              onChange={(e) => {
                setWalletFile(e.target.files[0] || null);
                setServices([]);
                setTempId(null);
                setParseError(null);
              }}
            />
          </label>
          <button
            onClick={handleParse}
            disabled={!walletFile || parsing}
            className="flex items-center gap-2 bg-gray-800 hover:bg-gray-900 text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50 transition-colors"
          >
            {parsing && <Loader2 size={13} className="animate-spin" />}
            {parsing ? "Parsing…" : "Parse Wallet"}
          </button>
        </div>
        {parseError && (
          <p className="text-xs text-red-600">{parseError}</p>
        )}
        {step2Ready && (
          <p className="text-xs text-green-700">
            Found {services.length} service{services.length !== 1 ? "s" : ""} in tnsnames.ora.
          </p>
        )}
      </div>

      {/* Step 2 */}
      {step2Ready && (
        <div className="space-y-3 border-t border-gray-100 pt-4">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Step 2 — Connection details</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-600">Profile name</label>
              <input
                className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Production DB"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-600">Service name</label>
              <select
                className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                value={serviceName}
                onChange={(e) => setServiceName(e.target.value)}
              >
                {services.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-600">Username</label>
              <input
                className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="wm_user"
                autoComplete="off"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-600">Password</label>
              <input
                type="password"
                className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete="new-password"
              />
            </div>
            <div className="flex flex-col gap-1 sm:col-span-2">
              <label className="text-xs font-medium text-gray-600">
                Wallet password <span className="text-gray-400 font-normal">(optional — only if wallet is password-protected)</span>
              </label>
              <input
                type="password"
                className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                value={walletPassword}
                onChange={(e) => setWalletPassword(e.target.value)}
                placeholder="Leave blank if not required"
                autoComplete="new-password"
              />
            </div>
          </div>

          {saveError && <p className="text-xs text-red-600">{saveError}</p>}

          <div className="flex gap-2 pt-1">
            <button
              onClick={handleSave}
              disabled={saving || !name.trim() || !serviceName || !username.trim() || !password}
              className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50 transition-colors"
            >
              {saving && <Loader2 size={13} className="animate-spin" />}
              {saving ? "Saving…" : "Save Profile"}
            </button>
            <button
              onClick={onCancel}
              className="px-4 py-2 rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-100 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Profile list view ────────────────────────────────────────────────────── //

function ProfileList({ profiles, activeProfileId, onSelect, onDelete, onAdd }) {
  const [deletingId, setDeletingId] = useState(null);

  async function handleDelete(id) {
    setDeletingId(id);
    try {
      await api.delete(`/oracle/profiles/${id}`);
      onDelete(id);
    } finally {
      setDeletingId(null);
    }
  }

  if (profiles.length === 0) {
    return (
      <div className="text-center py-10 text-gray-400">
        <Database size={32} className="mx-auto mb-2 opacity-30" />
        <p className="text-sm">No connection profiles yet</p>
        <button
          onClick={onAdd}
          className="mt-3 inline-flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          <Plus size={14} />
          Add Connection
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {profiles.map((p) => {
        const isActive = p.id === activeProfileId;
        return (
          <div
            key={p.id}
            onClick={() => onSelect(p.id)}
            className={`flex items-start justify-between gap-3 rounded-lg border p-4 cursor-pointer transition-colors ${
              isActive
                ? "border-indigo-400 bg-indigo-50"
                : "border-gray-200 bg-white hover:border-gray-300"
            }`}
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <p className="font-semibold text-gray-900 text-sm truncate">{p.name}</p>
                {isActive && (
                  <span className="flex-shrink-0 text-xs bg-indigo-600 text-white px-2 py-0.5 rounded-full">
                    Active
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-500 mt-0.5 font-mono truncate">{p.service_name}</p>
              <p className="text-xs text-gray-400 mt-0.5">{p.username}</p>
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleDelete(p.id);
              }}
              disabled={deletingId === p.id}
              className="flex-shrink-0 text-gray-300 hover:text-red-500 transition-colors p-1 rounded"
            >
              {deletingId === p.id
                ? <Loader2 size={14} className="animate-spin" />
                : <Trash2 size={14} />
              }
            </button>
          </div>
        );
      })}
      <button
        onClick={onAdd}
        className="w-full flex items-center justify-center gap-2 border border-dashed border-gray-300 rounded-lg py-3 text-sm text-gray-500 hover:border-indigo-400 hover:text-indigo-600 transition-colors"
      >
        <Plus size={14} />
        Add Connection
      </button>
    </div>
  );
}

// ─── Main export ──────────────────────────────────────────────────────────── //

export default function OracleSettings({
  oracleStatus,
  onStatusRefresh,
  onProfileSelect,
  oracleProfileId,
  apiKey,
  apiProvider,
}) {
  const [profiles, setProfiles] = useState([]);
  const [loadingProfiles, setLoadingProfiles] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [initLoading, setInitLoading] = useState(false);
  const [initResult, setInitResult] = useState(null);
  const [syncLoading, setSyncLoading] = useState(false);
  const [syncResult, setSyncResult] = useState(null);
  const [embedLoading, setEmbedLoading] = useState(false);
  const [embedResult, setEmbedResult] = useState(null);

  const connected = oracleStatus?.connected;

  useEffect(() => {
    fetchProfiles();
  }, []);

  async function fetchProfiles() {
    setLoadingProfiles(true);
    try {
      const res = await api.get("/oracle/profiles");
      setProfiles(res.data);
    } catch {
      setProfiles([]);
    } finally {
      setLoadingProfiles(false);
    }
  }

  function handleProfileSaved() {
    setShowForm(false);
    fetchProfiles();
  }

  function handleProfileDeleted(id) {
    setProfiles((prev) => prev.filter((p) => p.id !== id));
    if (id === oracleProfileId) {
      onProfileSelect(null);
      onStatusRefresh();
    }
  }

  function handleProfileSelect(id) {
    onProfileSelect(id);
    onStatusRefresh();
  }

  function oracleHeaders() {
    return {
      ...(oracleProfileId && { "X-Oracle-Profile-Id": String(oracleProfileId) }),
    };
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

      <div className="p-5 space-y-6">
        {/* Profile management */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-gray-800">Connection Profiles</p>
            {!showForm && profiles.length > 0 && (
              <button
                onClick={() => setShowForm(true)}
                className="flex items-center gap-1.5 text-xs text-indigo-600 hover:text-indigo-800 font-medium"
              >
                <Plus size={12} />
                Add
              </button>
            )}
          </div>

          {showForm ? (
            <NewProfileForm
              onSaved={handleProfileSaved}
              onCancel={() => setShowForm(false)}
            />
          ) : loadingProfiles ? (
            <div className="flex items-center gap-2 text-sm text-gray-400 py-4">
              <Loader2 size={14} className="animate-spin" />
              Loading profiles…
            </div>
          ) : (
            <ProfileList
              profiles={profiles}
              activeProfileId={oracleProfileId}
              onSelect={handleProfileSelect}
              onDelete={handleProfileDeleted}
              onAdd={() => setShowForm(true)}
            />
          )}

          {oracleStatus?.error && !connected && (
            <p className="text-red-600 text-xs font-mono">{oracleStatus.error}</p>
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
