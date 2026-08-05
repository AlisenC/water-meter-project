import {
  LayoutDashboard,
  BarChart2,
  Receipt,
  ClipboardList,
  MessageSquare,
  Settings,
  ChevronLeft,
  ChevronRight,
  Droplets,
  AlertTriangle,
} from "lucide-react";

const NAV_ITEMS = [
  { id: "overview",    label: "Overview",       icon: LayoutDashboard },
  { id: "analysis",    label: "Analysis",       icon: BarChart2 },
  { id: "statements",  label: "Bill Statements",icon: Receipt },
  { id: "readings",    label: "Readings",       icon: ClipboardList },
  { id: "leak",        label: "Leak Detection", icon: AlertTriangle },
  { id: "ai",          label: "AI Assistant",   icon: MessageSquare },
];

function NavBadge({ count }) {
  if (!count) return null;
  return (
    <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-blue-500 text-white leading-none">
      {count}
    </span>
  );
}

function StatusDot({ color }) {
  const colors = {
    green:  "bg-green-400",
    amber:  "bg-amber-400",
    gray:   "bg-gray-500",
    red:    "bg-red-400",
  };
  return <span className={`w-2 h-2 rounded-full flex-shrink-0 ${colors[color] ?? colors.gray}`} />;
}

export default function Sidebar({
  activeSection,
  onNavigate,
  collapsed,
  onToggleCollapse,
  anomalyCount,
  billingCount,
  apiKeySet,
  oracleConnected,
}) {
  return (
    <div
      className={`${
        collapsed ? "w-[60px]" : "w-60"
      } bg-slate-900 flex flex-col h-screen sticky top-0 flex-shrink-0 transition-[width] duration-300 ease-in-out overflow-hidden`}
    >
      {/* Logo */}
      <div className="flex items-center justify-between px-3 py-4 border-b border-slate-700/60 min-h-[60px]">
        <div className="flex items-center gap-2.5 min-w-0 overflow-hidden">
          <Droplets className="text-blue-400 flex-shrink-0" size={20} />
          {!collapsed && (
            <span className="text-white font-semibold text-sm tracking-tight truncate">
              Water Meter
            </span>
          )}
        </div>
        <button
          onClick={onToggleCollapse}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="text-slate-500 hover:text-slate-200 flex-shrink-0 p-1 rounded-md hover:bg-slate-800 transition-colors ml-1"
        >
          {collapsed ? <ChevronRight size={15} /> : <ChevronLeft size={15} />}
        </button>
      </div>

      {/* Main nav */}
      <nav className="flex-1 py-3 px-2 space-y-0.5 overflow-y-auto overflow-x-hidden">
        {NAV_ITEMS.map(({ id, label, icon: Icon }) => {
          const isActive = activeSection === id;
          const badge = id === "analysis" ? anomalyCount : id === "statements" ? billingCount : 0;
          const oracleDot = id === "ai" ? (oracleConnected ? "green" : "gray") : null;

          return (
            <button
              key={id}
              onClick={() => onNavigate(id)}
              title={collapsed ? label : undefined}
              className={`w-full flex items-center gap-3 px-2.5 py-2 rounded-lg text-[13px] font-medium transition-colors duration-150 ${
                isActive
                  ? "bg-slate-800 text-white border-l-2 border-blue-500"
                  : "text-slate-400 hover:bg-slate-800 hover:text-slate-100 border-l-2 border-transparent"
              }`}
            >
              <Icon size={17} className={`flex-shrink-0 ${isActive ? "text-blue-400" : ""}`} />
              {!collapsed && (
                <>
                  <span className="flex-1 text-left truncate">{label}</span>
                  {badge > 0 && <NavBadge count={badge} />}
                  {oracleDot && <StatusDot color={oracleDot} />}
                </>
              )}
            </button>
          );
        })}
      </nav>

      {/* Divider */}
      <div className="mx-3 border-t border-slate-700/60" />

      {/* Settings at bottom */}
      <div className="px-2 py-3">
        <button
          onClick={() => onNavigate("settings")}
          title={collapsed ? "Settings" : undefined}
          className={`w-full flex items-center gap-3 px-2.5 py-2 rounded-lg text-[13px] font-medium transition-colors duration-150 ${
            activeSection === "settings"
              ? "bg-slate-800 text-white border-l-2 border-blue-500"
              : "text-slate-400 hover:bg-slate-800 hover:text-slate-100 border-l-2 border-transparent"
          }`}
        >
          <Settings size={17} className={`flex-shrink-0 ${activeSection === "settings" ? "text-blue-400" : ""}`} />
          {!collapsed && (
            <>
              <span className="flex-1 text-left">Settings</span>
              <StatusDot color={apiKeySet ? "green" : "amber"} />
            </>
          )}
        </button>
      </div>
    </div>
  );
}
