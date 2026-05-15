import { useState } from "react";
import { KeyRound } from "lucide-react";

const LS_KEY = "wm_api_key";
const LS_PROVIDER = "wm_api_provider";

function maskKey(key) {
  if (!key || key.length < 8) return "****";
  return key.slice(0, 4) + "..." + key.slice(-4);
}

export default function ApiKeySettings({ apiKey, apiProvider, onSave, onClear }) {
  const [open, setOpen] = useState(!apiKey);
  const [draftKey, setDraftKey] = useState(apiKey || "");
  const [draftProvider, setDraftProvider] = useState(apiProvider || "anthropic");

  function handleSave() {
    if (!draftKey.trim()) return;
    localStorage.setItem(LS_KEY, draftKey.trim());
    localStorage.setItem(LS_PROVIDER, draftProvider);
    onSave(draftKey.trim(), draftProvider);
    setOpen(false);
  }

  function handleClear() {
    localStorage.removeItem(LS_KEY);
    localStorage.removeItem(LS_PROVIDER);
    setDraftKey("");
    setDraftProvider("anthropic");
    onClear();
    setOpen(true);
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-5 py-3 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <KeyRound size={16} className="text-blue-600" />
          <h3 className="font-semibold text-gray-800 text-sm">AI Provider Settings</h3>
        </div>
        <button
          onClick={() => setOpen((v) => !v)}
          className="text-xs text-blue-600 hover:text-blue-800 underline"
        >
          {open ? "Collapse" : "Edit"}
        </button>
      </div>

      <div className="px-5 py-4">
        {/* Status line */}
        <div className="flex items-center gap-2 mb-4">
          <span
            className={`w-2 h-2 rounded-full flex-shrink-0 ${apiKey ? "bg-green-400" : "bg-amber-400"}`}
          />
          <span className={`text-sm font-medium ${apiKey ? "text-green-700" : "text-amber-700"}`}>
            {apiKey
              ? `${apiProvider === "openai" ? "OpenAI (GPT-4o)" : "Anthropic (Claude)"} · ${maskKey(apiKey)}`
              : "No API key — configure to use PDF import and AI chat"}
          </span>
        </div>

        {open && (
          <div className="space-y-3">
            <p className="text-xs text-gray-500 leading-relaxed">
              Your key is stored in this browser only and sent directly to the AI provider. It is never
              stored on the server.
            </p>
            <div className="flex flex-wrap gap-2 items-center">
              <select
                value={draftProvider}
                onChange={(e) => setDraftProvider(e.target.value)}
                className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="anthropic">Anthropic (Claude)</option>
                <option value="openai">OpenAI (GPT-4o)</option>
              </select>
              <input
                type="password"
                placeholder="Paste API key"
                value={draftKey}
                onChange={(e) => setDraftKey(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSave()}
                className="border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono w-72 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                autoComplete="off"
              />
              <button
                onClick={handleSave}
                disabled={!draftKey.trim()}
                className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 text-sm font-medium rounded-lg disabled:opacity-50 transition-colors"
              >
                Save
              </button>
              {apiKey && (
                <button
                  onClick={handleClear}
                  className="text-red-500 hover:text-red-700 text-sm underline"
                >
                  Clear
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
