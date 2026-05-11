import { useState } from "react";

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
    <div className={`mb-4 rounded-md border ${apiKey ? "border-green-200 bg-green-50" : "border-amber-200 bg-amber-50"}`}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex justify-between items-center px-4 py-2 text-sm font-semibold text-left"
      >
        <span className={apiKey ? "text-green-800" : "text-amber-800"}>
          {apiKey
            ? `API key set — ${apiProvider === "openai" ? "OpenAI (GPT-4o)" : "Anthropic (Claude)"} · ${maskKey(apiKey)}`
            : "API key required — configure to use PDF import and AI chat"}
        </span>
        <span className="text-gray-400 ml-2">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-3">
          <p className="text-xs text-gray-500">
            Your key is saved in this browser only and sent directly to the AI provider. It is never stored on the server.
          </p>
          <div className="flex flex-wrap gap-2 items-center">
            <select
              value={draftProvider}
              onChange={(e) => setDraftProvider(e.target.value)}
              className="border rounded px-2 py-1.5 text-sm bg-white"
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
              className="border rounded px-2 py-1.5 text-sm font-mono w-72 bg-white"
              autoComplete="off"
            />
            <button
              onClick={handleSave}
              disabled={!draftKey.trim()}
              className="bg-blue-600 text-white px-4 py-1.5 text-sm rounded disabled:opacity-50 hover:bg-blue-700"
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
  );
}
