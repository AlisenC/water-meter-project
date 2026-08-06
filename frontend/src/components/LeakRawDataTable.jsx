import { useState, useEffect, useCallback } from "react";
import { toast } from "react-hot-toast";
import { Trash2, Loader2 } from "lucide-react";
import { api } from "../api";

const KIND_CONFIG = {
  submeter: {
    title: "Submeter Readings",
    listUrl: (sessionId) => `/leak/sessions/${sessionId}/submeter-readings`,
    deleteUrl: (id) => `/leak/submeter/${id}`,
    columns: [
      { key: "mi", label: "Meter" },
      { key: "reading", label: "Reading" },
      { key: "record_date", label: "Date", format: (v) => new Date(v).toLocaleDateString("en-AU") },
      { key: "unit", label: "Unit", format: (v) => (v === 1 ? "CCF" : "gal") },
    ],
  },
  "main-meter": {
    title: "Main Meter Readings",
    listUrl: (sessionId) => `/leak/sessions/${sessionId}/main-meter-readings`,
    deleteUrl: (id) => `/leak/main-meter/${id}`,
    columns: [
      { key: "read_time", label: "Read Time", format: (v) => new Date(v).toLocaleString("en-AU") },
      { key: "read_value", label: "Read (CCF)" },
      { key: "flow_value", label: "Flow (CCF)", format: (v) => (v != null ? v : "—") },
    ],
  },
};

export default function LeakRawDataTable({ sessionId, kind, onChanged }) {
  const config = KIND_CONFIG[kind];
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(new Set());
  const [deleting, setDeleting] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get(config.listUrl(sessionId));
      setRows(res.data);
      setSelected(new Set());
    } finally {
      setLoading(false);
    }
  }, [sessionId, config]);

  useEffect(() => { refresh(); }, [refresh]);

  function toggleRow(id) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setSelected((prev) => (prev.size === rows.length ? new Set() : new Set(rows.map((r) => r.id))));
  }

  async function handleDeleteSelected() {
    if (selected.size === 0) return;
    if (!window.confirm(`Delete ${selected.size} selected row(s)? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      await Promise.all([...selected].map((id) => api.delete(config.deleteUrl(id))));
      toast.success(`${selected.size} row(s) deleted.`);
      await refresh();
      onChanged?.();
    } catch (err) {
      toast.error(err.response?.data?.detail ?? "Delete failed.");
    } finally {
      setDeleting(false);
    }
  }

  if (loading) return <p className="text-xs text-gray-400 italic">Loading…</p>;

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100 bg-gray-50">
        <p className="text-xs font-semibold text-gray-700 uppercase tracking-wider">{config.title} ({rows.length})</p>
        <button
          onClick={handleDeleteSelected}
          disabled={selected.size === 0 || deleting}
          className="flex items-center gap-1.5 text-xs font-medium text-red-700 disabled:text-gray-300 disabled:cursor-not-allowed hover:text-red-800"
        >
          {deleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
          Delete Selected ({selected.size})
        </button>
      </div>
      {rows.length === 0 ? (
        <p className="text-xs text-gray-400 italic px-4 py-3">No rows imported yet.</p>
      ) : (
        <div className="max-h-64 overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-gray-50">
              <tr className="text-left text-gray-500">
                <th className="px-4 py-2">
                  <input type="checkbox" checked={selected.size === rows.length && rows.length > 0} onChange={toggleAll} />
                </th>
                {config.columns.map((c) => (
                  <th key={c.key} className="px-2 py-2 font-semibold uppercase tracking-wider">{c.label}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {rows.map((r) => (
                <tr key={r.id} className={selected.has(r.id) ? "bg-blue-50" : ""}>
                  <td className="px-4 py-1.5">
                    <input type="checkbox" checked={selected.has(r.id)} onChange={() => toggleRow(r.id)} />
                  </td>
                  {config.columns.map((c) => (
                    <td key={c.key} className="px-2 py-1.5 font-mono text-gray-700">
                      {c.format ? c.format(r[c.key]) : r[c.key]}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
