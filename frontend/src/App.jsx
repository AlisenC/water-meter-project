import { useState, useEffect } from "react";
import { api } from "./api";
import AIChat from "./components/AIChat";
import ReadingTable from "./components/ReadingTable";
import DashboardSummary from "./components/DashboardSummary";
import UsageCharts from "./components/UsageCharts";
import DataQuality from "./components/DataQuality";

function App() {
  const [readings, setReadings] = useState([]);
  const [anomalies, setAnomalies] = useState([]);
  const [csvFile, setCsvFile] = useState(null);
  const [uploadStatus, setUploadStatus] = useState(null);
  const [importReport, setImportReport] = useState(null);

  useEffect(() => {
    Promise.all([api.get("/readings"), api.get("/anomalies")]).then(
      ([readingsRes, anomaliesRes]) => {
        setReadings(readingsRes.data);
        setAnomalies(anomaliesRes.data);
      }
    );
  }, []);

  const handleFileChange = (e) => {
    setCsvFile(e.target.files[0]);
  };

  const handleUpload = async () => {
    if (!csvFile) return;
    const formData = new FormData();
    formData.append("file", csvFile);

    try {
      const res = await api.post("/import-csv", formData);
      const report = res.data;
      setImportReport(report);
      setUploadStatus({
        ok: true,
        message: `${report.inserted} rows imported, ${report.skipped} skipped.`,
      });

      const [updatedReadings, updatedAnomalies] = await Promise.all([
        api.get("/readings"),
        api.get("/anomalies"),
      ]);
      setReadings(updatedReadings.data);
      setAnomalies(updatedAnomalies.data);
    } catch (error) {
      setUploadStatus({ ok: false, message: "Upload failed. Check the CSV format." });
      setImportReport(null);
      console.error("CSV upload failed:", error);
    } finally {
      setCsvFile(null);
    }
  };

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">Water Meter Dashboard</h1>

      <DashboardSummary readings={readings} anomalies={anomalies} />

      <UsageCharts readings={readings} />

      <AIChat />

      {/* CSV Upload */}
      <div className="mb-4 flex gap-2 items-center flex-wrap">
        <input type="file" accept=".csv" onChange={handleFileChange} />
        <button
          onClick={handleUpload}
          className="bg-green-500 text-white px-4 py-2"
        >
          Upload CSV
        </button>
        {uploadStatus && (
          <span className={uploadStatus.ok ? "text-green-600 text-sm" : "text-red-600 text-sm"}>
            {uploadStatus.message}
          </span>
        )}
      </div>

      <DataQuality importReport={importReport} anomalies={anomalies} />

      <ReadingTable readings={readings} setReadings={setReadings} />
    </div>
  );
}

export default App;