import { useState } from "react";
import { api } from "../api";


export default function ReadingTable({ readings, setReadings }) {
  const [household, setHousehold] = useState("");
  const [amount, setAmount] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();

    try {
      const response = await api.post("/readings", {
        household,
        amount: parseFloat(amount),
      });

      // Update UI immediately
      setReadings([...readings, response.data]);

      setHousehold("");
      setAmount("");
    } catch (error) {
      console.error("Error creating reading:", error);
    }
  };

   return (
    <div>
      <form onSubmit={handleSubmit} className="mb-4 flex gap-2">
        <input
          className="border p-2"
          value={household}
          onChange={(e) => setHousehold(e.target.value)}
          placeholder="Household"
        />
        <input
          className="border p-2"
          type="number"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          placeholder="Water usage"
        />
        <button className="bg-blue-500 text-white px-4 py-2">
          Add
        </button>
      </form>
      <table className="table-auto w-full border-collapse border border-gray-300">
        <thead>
          <tr>
            <th className="border px-2 py-1">Household</th>
            <th className="border px-2 py-1">Consumption (m³)</th>
          </tr>
        </thead>
        <tbody>
          {readings.map((r, i) => (
            <tr key={i}>
              <td className="border px-2 py-1">{r.household}</td>
              <td className="border px-2 py-1">{r.amount}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}