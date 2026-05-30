import React, { useState, useEffect } from "react";
import { 
  CalendarDays, 
  Boxes, 
  UserCheck, 
  IndianRupee, 
  AlertTriangle, 
  Trash2, 
  Edit2, 
  Plus, 
  X, 
  Clock, 
  History,
  AlertCircle,
  Wrench,
  ChevronDown,
  ChevronUp
} from "lucide-react";
import { 
  getDailySequenceLogs, 
  createManualActivityLog, 
  updateActivityLog, 
  deleteActivityLog, 
  reportMachineBreakdown,
  type ActivityLog,
  type DailySequenceGroup,
  type DailySequenceLogItem
} from "../lib/api";

export default function OperationsPage() {
  const [dailyGroups, setDailyGroups] = useState<DailySequenceGroup[]>([]);
  const [expandedDates, setExpandedDates] = useState<Record<string, boolean>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");

  // Edit Modal State
  const [editingLog, setEditingLog] = useState<ActivityLog | null>(null);
  const [editDesc, setEditDesc] = useState("");
  const [editType, setEditType] = useState<ActivityLog["event_type"]>("production");

  // Create Manual Log State
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newDesc, setNewDesc] = useState("");
  const [newType, setNewType] = useState<ActivityLog["event_type"]>("production");

  // Breakdown Modal State
  const [isBreakdownOpen, setIsBreakdownOpen] = useState(false);
  const [breakdownMachineId, setBreakdownMachineId] = useState("");
  const [breakdownCategory, setBreakdownCategory] = useState("Mechanical fault");
  const [breakdownNotes, setBreakdownNotes] = useState("");

  useEffect(() => {
    void fetchLogs();
  }, []);

  async function fetchLogs() {
    setIsLoading(true);
    setError("");
    try {
      const response = await getDailySequenceLogs();
      setDailyGroups(response);
      
      // Auto-expand the first date (which is usually today/most recent) by default
      if (response && response.length > 0) {
        const todayStr = new Date().toISOString().split("T")[0];
        const initialExpanded: Record<string, boolean> = {};
        response.forEach((group, idx) => {
          initialExpanded[group.date] = idx === 0 || group.date === todayStr;
        });
        setExpandedDates(initialExpanded);
      }
    } catch (err) {
      console.error("Failed to load operations logs:", err);
      setError("Failed to load sequence logs.");
      setDailyGroups([]);
    } finally {
      setIsLoading(false);
    }
  }

  function showToast(message: string) {
    setToast(message);
    setTimeout(() => setToast(""), 3000);
  }

  async function handleDelete(logId: number) {
    if (!window.confirm("Are you sure you want to permanently delete this floor audit log?")) {
      return;
    }
    try {
      await deleteActivityLog(logId);
      showToast("Event log deleted successfully");
      await fetchLogs();
    } catch (err) {
      console.error("Failed to delete log:", err);
      showToast("Failed to delete log entry");
    }
  }

  async function handleEditSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!editingLog) return;
    if (!editDesc.trim()) {
      alert("Description cannot be empty");
      return;
    }
    try {
      await updateActivityLog(editingLog.id, {
        event_type: editType,
        description: editDesc.trim()
      });
      showToast("Event log updated successfully");
      setEditingLog(null);
      await fetchLogs();
    } catch (err) {
      console.error("Failed to update log:", err);
      showToast("Failed to update log entry");
    }
  }

  async function handleCreateSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!newDesc.trim()) {
      alert("Description cannot be empty");
      return;
    }
    try {
      await createManualActivityLog({
        event_type: newType,
        description: newDesc.trim()
      });
      showToast("Manual event logged successfully");
      setNewDesc("");
      setIsCreateOpen(false);
      await fetchLogs();
    } catch (err) {
      console.error("Failed to log manual event:", err);
      showToast("Failed to log manual event");
    }
  }

  async function handleBreakdownSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!breakdownMachineId) {
      alert("Machine ID is required");
      return;
    }
    try {
      await reportMachineBreakdown({
        machine_id: Number(breakdownMachineId),
        issue_category: breakdownCategory,
        custom_notes: breakdownNotes.trim() || undefined
      });
      showToast("Machine breakdown reported successfully");
      setBreakdownMachineId("");
      setBreakdownCategory("Mechanical fault");
      setBreakdownNotes("");
      setIsBreakdownOpen(false);
      await fetchLogs();
    } catch (err) {
      console.error("Failed to report breakdown:", err);
      showToast("Failed to report machine breakdown");
    }
  }

  // Visual helper configuration per Event Type
  const eventConfig = {
    production: {
      color: "border-emerald-500 bg-emerald-50 text-emerald-700 dark:bg-emerald-950/20 dark:text-emerald-400",
      icon: Boxes,
      badge: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400",
      label: "Production"
    },
    attendance: {
      color: "border-blue-500 bg-blue-50 text-blue-700 dark:bg-blue-950/20 dark:text-blue-400",
      icon: UserCheck,
      badge: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
      label: "Attendance"
    },
    expense: {
      color: "border-amber-500 bg-amber-50 text-amber-700 dark:bg-amber-950/20 dark:text-amber-400",
      icon: IndianRupee,
      badge: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400",
      label: "Expense"
    },
    payment: {
      color: "border-teal-500 bg-teal-50 text-teal-700 dark:bg-teal-950/20 dark:text-teal-400",
      icon: IndianRupee,
      badge: "bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-400",
      label: "Payment Log"
    },
    machine_telemetry: {
      color: "border-rose-500 bg-rose-50 text-rose-700 dark:bg-rose-950/20 dark:text-rose-400",
      icon: AlertTriangle,
      badge: "bg-rose-100 text-rose-800 dark:bg-rose-900/30 dark:text-rose-400",
      label: "Machine Telemetry"
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Banner & Date Navigation Panel */}
      <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between rounded-2xl bg-white p-5 border border-zinc-150 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-purple-100 text-purple-700">
            <History className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-xl font-black text-zinc-950">Floor Audit Trail</h1>
            <p className="text-xs text-zinc-500">Unified chronological factory operations sequence timeline grouped by date</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 self-start sm:self-auto">
          {/* Manual Log Trigger */}
          <button
            onClick={() => setIsCreateOpen(true)}
            className="inline-flex h-10 items-center gap-2 rounded-lg bg-purple-700 px-4 text-sm font-bold text-white shadow hover:bg-purple-800 transition"
          >
            <Plus className="h-4 w-4" />
            Log Floor Event
          </button>

          <button
            onClick={() => setIsBreakdownOpen(true)}
            className="inline-flex h-10 items-center gap-2 rounded-lg bg-rose-600 px-4 text-sm font-bold text-white shadow hover:bg-rose-700 transition"
          >
            <AlertTriangle className="h-4 w-4" />
            ⚠️ Report Machine Breakdown
          </button>
        </div>
      </header>

      {/* Main Section */}
      <section className="rounded-2xl bg-white p-6 border border-zinc-150 shadow-sm min-h-[400px] relative">
        {toast && (
          <div className="absolute top-4 right-4 z-10 rounded-lg bg-zinc-900 px-4 py-2 text-xs font-semibold text-white shadow-lg animate-fade-in">
            {toast}
          </div>
        )}

        {isLoading ? (
          <div className="flex flex-col items-center justify-center p-12 text-sm text-zinc-400">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-zinc-200 border-t-purple-600 mb-2" />
            Loading Daily Sequence...
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center p-12 text-center text-sm text-rose-500">
            <AlertCircle className="h-8 w-8 mb-2" />
            {error}
          </div>
        ) : dailyGroups.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-12 text-center text-sm text-zinc-400 border border-dashed border-zinc-200 rounded-xl">
            <History className="h-8 w-8 text-zinc-300 mb-2" />
            <p className="font-semibold text-zinc-500">No events recorded yet</p>
            <p className="text-xs text-zinc-400 mt-1 max-w-xs">
              Factory activities (Production runs, attendance checkins, OEE telemetry changes, or expense ledgers) will populate automatically as they occur.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {dailyGroups.map((group) => {
              const isExpanded = !!expandedDates[group.date];
              return (
                <div key={group.date} className="border border-zinc-150 rounded-xl overflow-hidden shadow-sm">
                  {/* Collapsible Accordion Header */}
                  <button
                    type="button"
                    onClick={() => setExpandedDates(prev => ({ ...prev, [group.date]: !isExpanded }))}
                    className="w-full flex items-center justify-between bg-zinc-50/50 p-4 border-b border-zinc-100 hover:bg-zinc-50 transition"
                  >
                    <div className="flex items-center gap-3">
                      <span className="bg-purple-100 text-purple-800 text-xs px-2.5 py-0.5 rounded-full font-bold">
                        {new Date(group.date).toLocaleDateString("en-IN", { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
                      </span>
                      <span className="text-zinc-500 text-xs font-semibold">
                        ({group.logs.length} operations logged)
                      </span>
                    </div>
                    {isExpanded ? <ChevronUp className="h-4 w-4 text-zinc-500" /> : <ChevronDown className="h-4 w-4 text-zinc-500" />}
                  </button>

                  {/* Accordion Body */}
                  {isExpanded && (
                    <div className="p-5 bg-white space-y-6">
                      {group.logs.length === 0 ? (
                        <p className="text-sm text-zinc-400 text-center py-4">No events logged for this date.</p>
                      ) : (
                        <div className="relative border-l-2 border-zinc-100 ml-4 pl-6 space-y-6">
                          {group.logs.map((log) => {
                            const cfg = eventConfig[log.event_type as keyof typeof eventConfig] || eventConfig.production;
                            const IconComp = cfg.icon;
                            
                            const actionColors: Record<string, string> = {
                              CREATE: "bg-emerald-500 text-white font-bold px-1.5 py-0.5 rounded text-[9px]",
                              UPDATE: "bg-amber-500 text-white font-bold px-1.5 py-0.5 rounded text-[9px]",
                              DELETE: "bg-rose-500 text-white font-bold px-1.5 py-0.5 rounded text-[9px]",
                            };

                            return (
                              <div key={log.id} className="relative group">
                                {/* Stepper Bullet Node Icon */}
                                <span className={`absolute -left-[35px] top-1.5 flex h-8 w-8 items-center justify-center rounded-full border-2 bg-white shadow-sm transition group-hover:scale-110 ${cfg.color}`}>
                                  <IconComp className="h-4 w-4" />
                                </span>

                                {/* Log Content Card */}
                                <div className="rounded-xl border border-zinc-100 bg-zinc-50/50 p-4 transition-all duration-300 hover:border-zinc-200 hover:bg-white hover:shadow-sm flex flex-col md:flex-row md:items-start md:justify-between gap-4">
                                  <div className="space-y-2">
                                    <div className="flex flex-wrap items-center gap-2">
                                      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${cfg.badge}`}>
                                        {cfg.label}
                                      </span>
                                      <div className="inline-flex items-center gap-1 text-[11px] font-semibold text-zinc-500">
                                        <Clock className="h-3 w-3" />
                                        {log.created_time || "Pending"}
                                      </div>
                                      {log.action_type && (
                                        <span className={actionColors[log.action_type] || "bg-zinc-500 text-white font-bold px-1.5 py-0.5 rounded text-[9px]"}>
                                          {log.action_type}
                                        </span>
                                      )}
                                      {log.user_role && (
                                        <span className="bg-zinc-100 text-zinc-600 px-1.5 py-0.5 rounded text-[10px] font-medium border border-zinc-200">
                                          Role: {log.user_role}
                                        </span>
                                      )}
                                    </div>
                                    <p className="text-sm font-medium leading-relaxed text-zinc-800">{log.description}</p>
                                  </div>

                                  {/* Inline micro buttons */}
                                  <div className="flex items-center gap-1.5 self-end md:self-auto shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <button
                                      onClick={() => {
                                        setEditingLog(log as any);
                                        setEditDesc(log.description);
                                        setEditType(log.event_type as any);
                                      }}
                                      title="Edit Entry"
                                      className="grid h-7 w-7 place-items-center rounded border border-zinc-200 text-zinc-600 hover:bg-purple-50 hover:text-purple-700 transition"
                                    >
                                      <Edit2 className="h-3.5 w-3.5" />
                                    </button>
                                    <button
                                      onClick={() => handleDelete(log.id)}
                                      title="Delete Entry"
                                      className="grid h-7 w-7 place-items-center rounded border border-zinc-200 text-zinc-600 hover:bg-red-50 hover:text-red-700 transition"
                                    >
                                      <Trash2 className="h-3.5 w-3.5" />
                                    </button>
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Edit Log Modal */}
      {editingLog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-zinc-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-md overflow-hidden rounded-2xl border border-zinc-100 bg-white shadow-2xl">
            <header className="flex h-14 items-center justify-between border-b border-zinc-100 px-5">
              <h3 className="text-sm font-bold text-zinc-950">Override Sequence Log</h3>
              <button onClick={() => setEditingLog(null)} className="rounded-full p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700">
                <X className="h-4 w-4" />
              </button>
            </header>

            <form onSubmit={handleEditSubmit} className="p-5 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-zinc-600 mb-1">Event Category</label>
                <select
                  value={editType}
                  onChange={(e) => setEditType(e.target.value as ActivityLog["event_type"])}
                  className="h-9 w-full rounded-lg border border-zinc-200 px-2.5 text-xs bg-white focus:border-purple-600"
                >
                  <option value="production">Production</option>
                  <option value="attendance">Attendance</option>
                  <option value="expense">Expense</option>
                  <option value="payment">Payment Log</option>
                  <option value="machine_telemetry">Machine Telemetry</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-zinc-600 mb-1">Log Description</label>
                <textarea
                  rows={3}
                  value={editDesc}
                  onChange={(e) => setEditDesc(e.target.value)}
                  className="w-full rounded-lg border border-zinc-200 p-2.5 text-xs focus:border-purple-600 outline-none resize-none"
                />
              </div>

              <footer className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setEditingLog(null)}
                  className="h-9 rounded-lg border border-zinc-200 px-4 text-xs font-semibold text-zinc-700 hover:bg-zinc-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="h-9 rounded-lg bg-purple-700 px-4 text-xs font-bold text-white hover:bg-purple-800"
                >
                  Save Override
                </button>
              </footer>
            </form>
          </div>
        </div>
      )}

      {/* Create Log Modal */}
      {isCreateOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-zinc-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-md overflow-hidden rounded-2xl border border-zinc-100 bg-white shadow-2xl">
            <header className="flex h-14 items-center justify-between border-b border-zinc-100 px-5">
              <h3 className="text-sm font-bold text-zinc-950">Log Manual Floor Event</h3>
              <button onClick={() => setIsCreateOpen(false)} className="rounded-full p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700">
                <X className="h-4 w-4" />
              </button>
            </header>

            <form onSubmit={handleCreateSubmit} className="p-5 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-zinc-600 mb-1">Event Category</label>
                <select
                  value={newType}
                  onChange={(e) => setNewType(e.target.value as ActivityLog["event_type"])}
                  className="h-9 w-full rounded-lg border border-zinc-200 px-2.5 text-xs bg-white focus:border-purple-600"
                >
                  <option value="production">Production</option>
                  <option value="attendance">Attendance</option>
                  <option value="expense">Expense</option>
                  <option value="payment">Payment Log</option>
                  <option value="machine_telemetry">Machine Telemetry</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-zinc-600 mb-1">Log Description</label>
                <textarea
                  rows={3}
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  placeholder="Describe exact details e.g., Machine swapped to 150ml cups..."
                  className="w-full rounded-lg border border-zinc-200 p-2.5 text-xs focus:border-purple-600 outline-none resize-none"
                />
              </div>

              <footer className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsCreateOpen(false)}
                  className="h-9 rounded-lg border border-zinc-200 px-4 text-xs font-semibold text-zinc-700 hover:bg-zinc-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="h-9 rounded-lg bg-purple-700 px-4 text-xs font-bold text-white hover:bg-purple-800"
                >
                  Log Event
                </button>
              </footer>
            </form>
          </div>
        </div>
      )}

      {/* Machine Breakdown Modal */}
      {isBreakdownOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-zinc-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-md overflow-hidden rounded-2xl border border-zinc-100 bg-white shadow-2xl">
            <header className="flex h-14 items-center justify-between border-b border-zinc-100 px-5 bg-rose-50">
              <div className="flex items-center gap-2">
                <Wrench className="h-4 w-4 text-rose-600" />
                <h3 className="text-sm font-bold text-zinc-950">Report Machine Breakdown / Issue</h3>
              </div>
              <button onClick={() => setIsBreakdownOpen(false)} className="rounded-full p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700">
                <X className="h-4 w-4" />
              </button>
            </header>

            <form onSubmit={handleBreakdownSubmit} className="p-5 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-zinc-600 mb-1">Machine ID</label>
                <input
                  type="number"
                  value={breakdownMachineId}
                  onChange={(e) => setBreakdownMachineId(e.target.value)}
                  placeholder="Enter machine ID number"
                  className="h-9 w-full rounded-lg border border-zinc-200 px-2.5 text-xs bg-white focus:border-rose-500 outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-zinc-600 mb-1">Issue Category</label>
                <select
                  value={breakdownCategory}
                  onChange={(e) => setBreakdownCategory(e.target.value)}
                  className="h-9 w-full rounded-lg border border-zinc-200 px-2.5 text-xs bg-white focus:border-rose-500"
                >
                  <option value="Mechanical fault">Mechanical fault</option>
                  <option value="Heater failure">Heater failure</option>
                  <option value="Electrical issue">Electrical issue</option>
                  <option value="Paper jam">Paper jam</option>
                  <option value="Bottom roll jam">Bottom roll jam</option>
                  <option value="Mould damage">Mould damage</option>
                  <option value="Sensor malfunction">Sensor malfunction</option>
                  <option value="Lubrication needed">Lubrication needed</option>
                  <option value="Other">Other</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-zinc-600 mb-1">Custom Notes (optional)</label>
                <textarea
                  rows={3}
                  value={breakdownNotes}
                  onChange={(e) => setBreakdownNotes(e.target.value)}
                  placeholder="Describe the specific issue or observations..."
                  className="w-full rounded-lg border border-zinc-200 p-2.5 text-xs focus:border-rose-500 outline-none resize-none"
                />
              </div>

              <footer className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsBreakdownOpen(false)}
                  className="h-9 rounded-lg border border-zinc-200 px-4 text-xs font-semibold text-zinc-700 hover:bg-zinc-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="h-9 rounded-lg bg-rose-600 px-4 text-xs font-bold text-white hover:bg-rose-700"
                >
                  Report Breakdown
                </button>
              </footer>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
