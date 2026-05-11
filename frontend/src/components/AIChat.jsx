import { useState } from "react";
import { api } from "../api";

export default function AIChat({ apiKey, apiProvider }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const askAI = async () => {
    if (!question.trim()) return;
    if (!apiKey) {
      setError("No API key configured. Add your key in the API Settings panel above.");
      setAnswer("");
      return;
    }

    setLoading(true);
    setError("");
    setAnswer("");

    try {
      const res = await api.post(
        "/ai/ask",
        { question },
        { headers: { "X-Api-Key": apiKey, "X-Api-Provider": apiProvider } }
      );
      if (res.data.error) {
        setError(res.data.error);
      } else {
        setAnswer(res.data.answer);
      }
    } catch (err) {
      setError(err.response?.data?.detail ?? "Request failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="border p-4 mt-6 rounded">
      <h2 className="font-bold mb-2">Ask AI</h2>

      <input
        className="border p-2 w-full"
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && askAI()}
        placeholder="Ask about water consumption..."
      />

      <button
        onClick={askAI}
        disabled={loading}
        className="bg-blue-500 text-white px-4 py-2 mt-2 disabled:opacity-50"
      >
        {loading ? "Thinking…" : "Ask"}
      </button>

      {answer && <p className="mt-3 text-gray-800">{answer}</p>}
      {error && <p className="mt-3 text-red-600 text-sm">{error}</p>}
    </div>
  );
}
