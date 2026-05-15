import { useState } from "react";
import { api } from "../api";
import { Database, Search, MessageSquare, AlertCircle, CheckCircle2, ChevronDown, ChevronUp } from "lucide-react";

function ConnectionBanner({ status, onNavigateSettings }) {
  if (!status) {
    return (
      <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-gray-100 text-gray-500 text-sm mb-6">
        <div className="w-2 h-2 rounded-full bg-gray-400 animate-pulse" />
        Checking Oracle connection…
      </div>
    );
  }

  if (status.connected) {
    return (
      <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-green-50 border border-green-200 text-green-800 text-sm mb-6">
        <CheckCircle2 size={16} className="flex-shrink-0" />
        <span>
          Connected to Oracle 26ai
          {status.version && (
            <span className="text-green-600 ml-1">· v{status.version}</span>
          )}
        </span>
      </div>
    );
  }

  return (
    <div className="rounded-lg bg-amber-50 border border-amber-200 p-4 mb-6">
      <div className="flex items-start gap-3">
        <AlertCircle size={18} className="text-amber-500 flex-shrink-0 mt-0.5" />
        <div className="flex-1">
          <p className="font-semibold text-amber-800 text-sm">Oracle 26ai not connected</p>
          <p className="text-amber-700 text-xs mt-0.5">
            {status.error ?? "Configure Oracle connection details to enable these features."}
          </p>
          <button
            onClick={onNavigateSettings}
            className="mt-2 text-xs font-medium text-amber-800 underline hover:text-amber-900"
          >
            Go to Settings →
          </button>
        </div>
      </div>
    </div>
  );
}

function AskOracle({ apiKey, apiProvider, disabled }) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [sqlOpen, setSqlOpen] = useState(false);

  async function submit() {
    const q = question.trim();
    if (!q || disabled) return;
    setLoading(true);
    setResult(null);
    try {
      const res = await api.post(
        "/oracle/ask",
        { question: q },
        { headers: { "X-Api-Key": apiKey, "X-Api-Provider": apiProvider } }
      );
      setResult(res.data);
    } catch (err) {
      setResult({ error: err.response?.data?.detail ?? "Request failed." });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-3">
        <input
          className="flex-1 border border-gray-300 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-50 disabled:text-gray-400"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder={disabled ? "Connect Oracle to enable this feature" : "e.g. Which household used the most water this year?"}
          disabled={disabled}
        />
        <button
          onClick={submit}
          disabled={disabled || loading || !question.trim()}
          className="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2.5 rounded-lg text-sm font-medium disabled:opacity-50 transition-colors whitespace-nowrap"
        >
          {loading ? "Running…" : "Ask Oracle"}
        </button>
      </div>

      {result && (
        <div className="space-y-3">
          {result.error && (
            <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
              {result.error}
            </div>
          )}

          {result.answer && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 text-sm text-blue-900 leading-relaxed">
              {result.answer}
            </div>
          )}

          {result.sql && (
            <div className="border border-gray-200 rounded-lg overflow-hidden">
              <button
                onClick={() => setSqlOpen((v) => !v)}
                className="w-full flex items-center justify-between px-4 py-2 bg-gray-50 text-xs font-semibold text-gray-600 hover:bg-gray-100 transition-colors"
              >
                <span>Generated SQL</span>
                {sqlOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              </button>
              {sqlOpen && (
                <pre className="px-4 py-3 text-xs font-mono text-gray-700 overflow-x-auto bg-white whitespace-pre-wrap">
                  {result.sql}
                </pre>
              )}
            </div>
          )}

          {result.result && result.result.length > 0 && (
            <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
              <div className="px-4 py-2 bg-gray-50 border-b text-xs font-semibold text-gray-500 uppercase tracking-wide">
                Results — {result.result.length} row{result.result.length !== 1 ? "s" : ""}
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm divide-y divide-gray-100">
                  <thead>
                    <tr className="bg-gray-50">
                      {Object.keys(result.result[0]).map((col) => (
                        <th key={col} className="px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {result.result.map((row, i) => (
                      <tr key={i} className="hover:bg-blue-50 transition-colors">
                        {Object.values(row).map((val, j) => (
                          <td key={j} className="px-4 py-2 text-gray-700 font-mono text-xs">
                            {val === null ? <span className="text-gray-400 italic">null</span> : String(val)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function VectorSearch({ apiKey, apiProvider, disabled }) {
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(5);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);

  async function submit() {
    const q = query.trim();
    if (!q || disabled) return;
    setLoading(true);
    setResults(null);
    setError(null);
    try {
      const res = await api.post(
        "/oracle/vector-search",
        { query: q, top_k: topK },
        { headers: { "X-Api-Key": apiKey, "X-Api-Provider": apiProvider } }
      );
      setResults(res.data.results);
    } catch (err) {
      setError(err.response?.data?.detail ?? "Vector search failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-500">
        Find meter readings semantically similar to your query using Oracle 26ai vector embeddings.
        Requires embeddings to be generated first — use the Sync tool in Settings.
      </p>

      <div className="flex gap-3">
        <input
          className="flex-1 border border-gray-300 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-50 disabled:text-gray-400"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder={disabled ? "Connect Oracle to enable this feature" : "e.g. high usage in Unit 3 during winter"}
          disabled={disabled}
        />
        <select
          value={topK}
          onChange={(e) => setTopK(Number(e.target.value))}
          className="border border-gray-300 rounded-lg px-3 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          disabled={disabled}
        >
          {[3, 5, 10, 20].map((n) => (
            <option key={n} value={n}>Top {n}</option>
          ))}
        </select>
        <button
          onClick={submit}
          disabled={disabled || loading || !query.trim()}
          className="bg-indigo-600 hover:bg-indigo-700 text-white px-5 py-2.5 rounded-lg text-sm font-medium disabled:opacity-50 transition-colors whitespace-nowrap"
        >
          {loading ? "Searching…" : "Search"}
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {results && results.length === 0 && (
        <p className="text-sm text-gray-400 italic text-center py-8">
          No results — make sure embeddings have been generated in Settings.
        </p>
      )}

      {results && results.length > 0 && (
        <div className="space-y-3">
          {results.map((r, i) => (
            <div
              key={i}
              className="bg-white border border-gray-200 rounded-lg px-4 py-3 flex items-start justify-between gap-4 hover:border-indigo-300 transition-colors"
            >
              <div>
                <p className="font-semibold text-gray-900 text-sm">{r.household}</p>
                <p className="text-xs text-gray-500 mt-0.5">{r.description}</p>
                {r.record_date && (
                  <p className="text-xs text-gray-400 mt-1">{r.record_date}</p>
                )}
              </div>
              <div className="flex-shrink-0 text-right">
                <span
                  className={`text-xs font-semibold px-2 py-1 rounded-full ${
                    r.similarity >= 80
                      ? "bg-green-100 text-green-700"
                      : r.similarity >= 60
                      ? "bg-blue-100 text-blue-700"
                      : "bg-gray-100 text-gray-600"
                  }`}
                >
                  {r.similarity}% match
                </span>
                <p className="text-xs font-mono text-gray-500 mt-1">{r.reading_value} kL</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const TABS = [
  { id: "ask",    label: "Ask Oracle",     icon: MessageSquare },
  { id: "search", label: "Semantic Search", icon: Search },
];

export default function OracleAI({ oracleStatus, apiKey, apiProvider, onNavigateSettings }) {
  const [activeTab, setActiveTab] = useState("ask");
  const disabled = !oracleStatus?.connected;

  return (
    <div className="space-y-6">
      <ConnectionBanner status={oracleStatus} onNavigateSettings={onNavigateSettings} />

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-100 rounded-lg p-1 w-fit">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === id
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            <Icon size={15} />
            {label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div>
        {activeTab === "ask" && (
          <AskOracle apiKey={apiKey} apiProvider={apiProvider} disabled={disabled} />
        )}
        {activeTab === "search" && (
          <VectorSearch apiKey={apiKey} apiProvider={apiProvider} disabled={disabled} />
        )}
      </div>
    </div>
  );
}
