import { useState } from "react";
import { api } from "../api";

export default function AIChat() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");

  const askAI = async () => {
    const res = await api.post("/ai/ask", { question });
    setAnswer(res.data.answer);
  };

  return (
    <div className="border p-4 mt-6 rounded">
      <h2 className="font-bold mb-2">Ask AI</h2>

      <input
        className="border p-2 w-full"
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        placeholder="Ask about water consumption..."
      />

      <button
        onClick={askAI}
        className="bg-blue-500 text-white px-4 py-2 mt-2"
      >
        Ask
      </button>

      {answer && (
        <p className="mt-3">{answer}</p>
      )}
    </div>
  );
}
