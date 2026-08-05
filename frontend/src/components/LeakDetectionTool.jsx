import { useState, useEffect, useCallback } from "react";
import { toast } from "react-hot-toast";
import { api } from "../api";
import LeakCsvImport from "./LeakCsvImport";
import LeakSessionView from "./LeakSessionView";

function sessionRangeLabel(s) {
  if (!s.date_min) return "No data yet";
  const fmt = (d) => new Date(d).toLocaleDateString("en-AU", { month: "short", day: "numeric", year: "numeric" });
  return `${fmt(s.date_min)} – ${fmt(s.date_max)}`;
}

export default function LeakDetectionTool() {
  const [tab, setTab] = useState("active");
  const [activeSession, setActiveSession] = useState(null);
  const [archivedSessions, setArchivedSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const [expandedId, setExpandedId] = useState(null);

  const refresh = useCallback(async () => {
    const [activeRes, allRes] = await Promise.all([
      api.get("/leak/sessions/active"),
      api.get("/leak/sessions"),
    ]);
    setActiveSession(activeRes.data);
    setArchivedSessions(allRes.data.filter((s) => s.status === "archived"));
    setRefreshKey((k) => k + 1);
  }, []);

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, [refresh]);

  async function handleArchive() {
    if (!window.confirm(
      `Archive the current leak detection session (${activeSession.submeter_row_count} submeter rows, ${activeSession.main_meter_row_count} main meter rows)? It will remain viewable under Archived Sessions and a fresh workspace will start.`
    )) return;
    try {
      await api.post(`/leak/sessions/${activeSession.id}/archive`);
      toast.success("Session archived. Starting a fresh workspace.");
      await refresh();
    } catch (err) {
      toast.error(err.response?.data?.detail ?? "Archive failed.");
    }
  }

  async function handleRestore(session) {
    const warning = activeSession?.submeter_row_count > 0 || activeSession?.main_meter_row_count > 0
      ? ` The current active workspace (${activeSession.submeter_row_count} submeter rows, ${activeSession.main_meter_row_count} main meter rows) will be archived first.`
      : "";
    if (!window.confirm(`Restore this session (${sessionRangeLabel(session)}) as the active workspace?${warning}`)) return;
    try {
      await api.post(`/leak/sessions/${session.id}/restore`);
      toast.success("Session restored as active.");
      setTab("active");
      await refresh();
    } catch (err) {
      toast.error(err.response?.data?.detail ?? "Restore failed.");
    }
  }

  if (loading) return <p className="text-sm text-gray-400 italic">Loading…</p>;

  return (
    <div className="space-y-5">
      {/* Sub-tabs */}
      <div className="flex gap-2 border-b border-gray-200">
        {[
          { id: "active", label: "Active Session" },
          { id: "archived", label: `Archived Sessions (${archivedSessions.length})` },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t.id ? "border-blue-600 text-blue-700" : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "active" && activeSession && (
        <div className="space-y-5">
          <div className="flex items-center justify-between bg-white rounded-xl border border-gray-200 shadow-sm px-4 py-3">
            <div>
              <p className="text-sm font-semibold text-gray-700">Current Workspace</p>
              <p className="text-xs text-gray-500 mt-0.5">
                {sessionRangeLabel(activeSession)} · {activeSession.submeter_row_count} submeter rows · {activeSession.main_meter_row_count} main meter rows
              </p>
            </div>
            <button
              onClick={handleArchive}
              disabled={activeSession.submeter_row_count === 0 && activeSession.main_meter_row_count === 0}
              className="bg-amber-600 hover:bg-amber-700 disabled:opacity-40 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              Archive Session
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <LeakCsvImport
              title="Import Daily Submeter Readings"
              hint="Columns: mi, reading, record_date, unit (0 = gallons, 1 = CCF)"
              previewUrl="/leak/submeter/import/preview"
              confirmUrl="/leak/submeter/import/confirm"
              onImported={(res) => { toast.success(`${res.inserted} submeter row(s) imported.`); refresh(); }}
            />
            <LeakCsvImport
              title="Import Daily Main Meter Readings"
              hint="AMI range-export CSV (Account_ID, Read_Time, Read, Flow_Time, Flow, …)"
              previewUrl="/leak/main-meter/import/preview"
              confirmUrl="/leak/main-meter/import/confirm"
              onImported={(res) => { toast.success(`${res.inserted} main meter row(s) imported.`); refresh(); }}
            />
          </div>

          <LeakSessionView key={`active-${activeSession.id}-${refreshKey}`} sessionId={activeSession.id} />
        </div>
      )}

      {tab === "archived" && (
        <div className="space-y-3">
          {archivedSessions.length === 0 ? (
            <p className="text-sm text-gray-400 italic">No archived sessions yet.</p>
          ) : (
            archivedSessions.map((s) => (
              <div key={s.id} className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                <div className="flex items-center justify-between px-4 py-3">
                  <div>
                    <p className="text-sm font-medium text-gray-800">{sessionRangeLabel(s)}</p>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {s.submeter_row_count} submeter rows · {s.main_meter_row_count} main meter rows · archived {new Date(s.archived_at).toLocaleDateString("en-AU")}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setExpandedId(expandedId === s.id ? null : s.id)}
                      className="border border-gray-300 hover:bg-gray-50 text-gray-700 px-3 py-1.5 rounded-lg text-xs font-medium"
                    >
                      {expandedId === s.id ? "Hide" : "View"}
                    </button>
                    <button
                      onClick={() => handleRestore(s)}
                      className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded-lg text-xs font-medium"
                    >
                      Restore
                    </button>
                  </div>
                </div>
                {expandedId === s.id && (
                  <div className="border-t border-gray-100 px-4 py-4">
                    <LeakSessionView sessionId={s.id} />
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
