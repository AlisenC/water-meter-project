import { useState, useEffect } from "react";
import { api } from "./api";
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
      <ReadingTable readings={readings} setReadings={setReadings} />
    </div>
  );
}

export default App;
