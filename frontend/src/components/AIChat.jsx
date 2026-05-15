import { useState, useRef, useEffect } from "react";
import { api } from "../api";
import { Send } from "lucide-react";

export default function AIChat({ apiKey, apiProvider }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send() {
    const q = input.trim();
    if (!q || loading) return;

    if (!apiKey) {
      setMessages((prev) => [
        ...prev,
        { role: "user", text: q },
        { role: "error", text: "No API key configured — add one in Settings." },
      ]);
      setInput("");
      return;
    }

    setMessages((prev) => [...prev, { role: "user", text: q }]);
    setInput("");
    setLoading(true);

    try {
      const res = await api.post(
        "/ai/ask",
        { question: q },
        { headers: { "X-Api-Key": apiKey, "X-Api-Provider": apiProvider } }
      );
      const text = res.data.error ?? res.data.answer ?? "No response.";
      const role = res.data.error ? "error" : "ai";
      setMessages((prev) => [...prev, { role, text }]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "error", text: err.response?.data?.detail ?? "Request failed." },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col h-full bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden" style={{ minHeight: "520px" }}>
      {/* Message list */}
      <div className="flex-1 overflow-y-auto px-5 py-5 space-y-4">
        {messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-center text-gray-400 gap-2 py-16">
            <p className="text-sm font-medium">Ask anything about your water usage data</p>
            <p className="text-xs">e.g. "Which household used the most water last quarter?"</p>
          </div>
        )}

        {messages.map((m, i) => {
          if (m.role === "user") {
            return (
              <div key={i} className="flex justify-end">
                <div className="bg-blue-600 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm max-w-[75%] leading-relaxed">
                  {m.text}
                </div>
              </div>
            );
          }
          if (m.role === "error") {
            return (
              <div key={i} className="flex justify-start">
                <div className="bg-red-50 border border-red-200 text-red-700 rounded-2xl rounded-tl-sm px-4 py-2.5 text-sm max-w-[75%] leading-relaxed">
                  {m.text}
                </div>
              </div>
            );
          }
          return (
            <div key={i} className="flex justify-start">
              <div className="bg-gray-50 border border-gray-200 text-gray-800 rounded-2xl rounded-tl-sm px-4 py-2.5 text-sm max-w-[75%] leading-relaxed whitespace-pre-wrap">
                {m.text}
              </div>
            </div>
          );
        })}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-50 border border-gray-200 rounded-2xl rounded-tl-sm px-4 py-3 flex gap-1">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce"
                  style={{ animationDelay: `${i * 0.15}s` }}
                />
              ))}
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="border-t border-gray-100 px-4 py-3 flex gap-3 bg-white">
        <input
          className="flex-1 border border-gray-300 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send()}
          placeholder={apiKey ? "Ask about your water usage…" : "Add an API key in Settings to chat"}
          disabled={loading}
        />
        <button
          onClick={send}
          disabled={loading || !input.trim()}
          className="bg-blue-600 hover:bg-blue-700 text-white p-2.5 rounded-xl disabled:opacity-40 transition-colors flex-shrink-0"
        >
          <Send size={16} />
        </button>
      </div>
    </div>
  );
}
