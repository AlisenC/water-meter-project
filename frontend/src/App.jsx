import { useState, useEffect } from "react";
import { api } from "./api";
import AIChat from "./components/AIChat";
import ReadingTable from "./components/ReadingTable";
import DashboardSummary from "./components/DashboardSummary";

function App() {
  const [readings, setReadings] = useState([]);

  useEffect(() => {
    api.get("/readings").then((res) => {
      setReadings(res.data);
    });
  }, []);

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">Water Meter Dashboard</h1>
      <DashboardSummary readings={readings} />

      <AIChat />

      {/* CSV Upload */}
      <div className="mb-4 flex gap-2 items-center">
        <input type="file" accept=".csv" onChange={handleFileChange} />
        <button
          onClick={handleUpload}
          className="bg-green-500 text-white px-4 py-2"
        >
          Upload CSV
        </button>
      </div>

      <ReadingTable readings={readings} setReadings={setReadings} />
    </div>
  );
}

export default App;
