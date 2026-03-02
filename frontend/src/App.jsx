import { useState, useEffect } from "react";
import { api } from "./api";
import AIChat from "./components/AIChat";
import ReadingTable from "./components/ReadingTable";
import DashboardSummary from "./components/DashboardSummary";

function App() {
  const [readings, setReadings] = useState([]);
  const [csvFile, setCsvFile] = useState(null);

  useEffect(() => {
    // Fetch all readings from backend
    api.get("/readings").then((res) => {
      setReadings(res.data);
    });
  }, []);

  // Handle CSV file selection
  const handleFileChange = (e) => {
    setCsvFile(e.target.files[0]);
  };

  // Upload CSV file to backend
  const handleUpload = async () => {
    if (!csvFile) return;
    const formData = new FormData();
    formData.append("file", csvFile);

    try {
      const res = await api.post("/import-csv", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      console.log(res.data.message);

      // Refetch updated readings
      const updated = await api.get("/readings");
      setReadings(updated.data);
    } catch (error) {
      console.error("CSV upload failed:", error);
    } finally {
      setCsvFile(null);
    }
  };

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