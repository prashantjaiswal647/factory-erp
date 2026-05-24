import { CalendarDays, Check, IndianRupee, PanelRightClose, Plus, ReceiptIndianRupee, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  addWorkerAdvance,
  getAttendanceSummary,
  getWorkerLedger,
  settleWorkerHisab,
  upsertWorkerAttendance
} from "../lib/api";
import type { AttendanceSummaryRow, SettlementResponse, WorkerLedgerDay, WorkerLedgerResponse } from "../lib/api";

const currentMonth = new Date().toISOString().slice(0, 7);

function money(value: string | number) {
  return `Rs ${Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

function defaultSettlement(workerId: number, month: string) {
  const [year, monthNumber] = month.split("-").map(Number);
  const from = `${month}-01`;
  const to = new Date(year, monthNumber, 0).toISOString().slice(0, 10);
  return {
    worker_id: workerId,
    duty_from_date: from,
    duty_to_date: to,
    advance_cutoff_date: new Date().toISOString().slice(0, 10),
    confirm: false
  };
}

export default function AttendancePage() {
  const [month, setMonth] = useState(currentMonth);
  const [summary, setSummary] = useState<AttendanceSummaryRow[]>([]);
  const [query, setQuery] = useState("");
  const [selectedWorker, setSelectedWorker] = useState<AttendanceSummaryRow | null>(null);
  const [ledger, setLedger] = useState<WorkerLedgerResponse | null>(null);
  const [advanceDraft, setAdvanceDraft] = useState<{ date: string; amount: number } | null>(null);
  const [settlementOpen, setSettlementOpen] = useState(false);
  const [settlement, setSettlement] = useState(defaultSettlement(0, currentMonth));
  const [settlementPreview, setSettlementPreview] = useState<SettlementResponse | null>(null);
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  async function loadSummary() {
    setIsLoading(true);
    setError("");
    try {
      const response = await getAttendanceSummary(month);
      setSummary(response.data.workers);
    } catch {
      setError("Attendance summary load nahi ho paaya.");
    } finally {
      setIsLoading(false);
    }
  }

  async function loadLedger(worker: AttendanceSummaryRow) {
    setSelectedWorker(worker);
    setSettlement(defaultSettlement(worker.worker_id, month));
    setSettlementPreview(null);
    const response = await getWorkerLedger(worker.worker_id, month);
    setLedger(response.data);
  }

  useEffect(() => {
    void loadSummary();
  }, [month]);

  const filteredSummary = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return summary;
    return summary.filter((row) => [row.worker_name, row.phone || ""].some((value) => value.toLowerCase().includes(term)));
  }, [query, summary]);

  async function updateAttendance(day: WorkerLedgerDay, patch: Partial<WorkerLedgerDay>) {
    if (!selectedWorker) return;
    const next = { ...day, ...patch };
    await upsertWorkerAttendance(selectedWorker.worker_id, {
      date: next.date,
      status: next.status,
      production_qty: next.production_qty ? Number(next.production_qty) : null
    });
    await loadLedger(selectedWorker);
    await loadSummary();
  }

  async function saveAdvance() {
    if (!selectedWorker || !advanceDraft || advanceDraft.amount <= 0) return;
    await addWorkerAdvance(selectedWorker.worker_id, advanceDraft);
    setAdvanceDraft(null);
    await loadLedger(selectedWorker);
    await loadSummary();
    setToast("Advance saved");
  }

  async function previewSettlement() {
    setIsSaving(true);
    try {
      const response = await settleWorkerHisab({ ...settlement, confirm: false });
      setSettlementPreview(response.data);
    } finally {
      setIsSaving(false);
    }
  }

  async function confirmSettlement() {
    setIsSaving(true);
    try {
      const response = await settleWorkerHisab({ ...settlement, confirm: true });
      setSettlementPreview(response.data);
      setSettlementOpen(false);
      setToast("Hisab cleared");
      if (selectedWorker) await loadLedger(selectedWorker);
      await loadSummary();
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      {toast ? <button className="fixed right-5 top-20 z-50 rounded-md bg-[#16A34A] px-4 py-3 text-sm font-semibold text-white shadow-lg" type="button" onClick={() => setToast("")}>{toast}</button> : null}
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-950">Attendance & Worker Ledger</h1>
          <p className="text-sm text-zinc-500">Duty, advance aur clear hisab ek hi jagah.</p>
        </div>
        <label className="grid gap-1 text-sm font-medium text-zinc-700">
          Month Filter
          <input className="h-10 rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" type="month" value={month} onChange={(event) => setMonth(event.target.value)} />
        </label>
      </header>

      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{error}</div> : null}

      <section className="rounded-lg border border-zinc-200 bg-white shadow-sm">
        <div className="flex flex-col gap-3 border-b border-zinc-200 p-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <CalendarDays className="h-5 w-5 text-brand-700" />
            <h2 className="font-semibold text-zinc-950">Worker Summary</h2>
          </div>
          <div className="relative w-full sm:max-w-xs">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
            <input className="h-10 w-full rounded-md border border-zinc-200 pl-9 pr-3 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" placeholder="Search worker" value={query} onChange={(event) => setQuery(event.target.value)} />
          </div>
        </div>

        {isLoading ? (
          <div className="p-6 text-sm text-zinc-500">Loading attendance...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-zinc-200 text-sm">
              <thead className="bg-zinc-50 text-left text-xs font-semibold uppercase text-zinc-500">
                <tr>
                  <th className="px-5 py-3">Worker Name</th>
                  <th className="px-5 py-3 text-right">Current Month Duty Days</th>
                  <th className="px-5 py-3 text-right">Uncleared Advance</th>
                  <th className="px-5 py-3 text-right">Net Current Balance</th>
                  <th className="px-5 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {filteredSummary.map((worker) => (
                  <tr key={worker.worker_id} className="hover:bg-zinc-50">
                    <td className="px-5 py-3">
                      <p className="font-medium text-zinc-950">{worker.worker_name}</p>
                      <p className="text-xs text-zinc-500">{worker.phone || "No phone"} | Rate {money(worker.daily_wage_rate)}</p>
                    </td>
                    <td className="px-5 py-3 text-right">{worker.duty_days}</td>
                    <td className="px-5 py-3 text-right text-red-700">{money(worker.uncleared_advance)}</td>
                    <td className="px-5 py-3 text-right font-semibold">{money(worker.net_current_balance)}</td>
                    <td className="px-5 py-3 text-right">
                      <button className="rounded-md bg-brand-600 px-3 py-2 text-xs font-semibold text-white hover:bg-brand-700" type="button" onClick={() => loadLedger(worker)}>
                        View Ledger
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {selectedWorker && ledger ? (
        <div className="fixed inset-0 z-40 bg-zinc-950/30">
          <aside className="ml-auto flex h-full w-full max-w-5xl flex-col bg-white shadow-2xl">
            <div className="flex items-start justify-between gap-4 border-b border-zinc-200 p-5">
              <div>
                <h2 className="text-xl font-semibold text-zinc-950">{selectedWorker.worker_name}</h2>
                <p className="text-sm text-zinc-500">{month} date-wise duty, production aur advance.</p>
              </div>
              <button className="grid h-9 w-9 place-items-center rounded-md border border-zinc-200 text-zinc-600" type="button" onClick={() => setSelectedWorker(null)}>
                <PanelRightClose className="h-4 w-4" />
              </button>
            </div>

            <div className="flex-1 overflow-auto p-5">
              <div className="mb-4 flex justify-end">
                <button className="inline-flex h-10 items-center gap-2 rounded-md bg-[#16A34A] px-4 text-sm font-semibold text-white hover:bg-[#16A34A]/90" type="button" onClick={() => setSettlementOpen(true)}>
                  <ReceiptIndianRupee className="h-4 w-4" />
                  Clear Hisab
                </button>
              </div>
              <table className="min-w-full divide-y divide-zinc-200 text-sm">
                <thead className="sticky top-0 bg-zinc-50 text-left text-xs font-semibold uppercase text-zinc-500">
                  <tr>
                    <th className="px-4 py-3">Date</th>
                    <th className="px-4 py-3">Attendance Status</th>
                    <th className="px-4 py-3">Production</th>
                    <th className="px-4 py-3 text-right">Duty</th>
                    <th className="px-4 py-3 text-right">Advance Taken</th>
                    <th className="px-4 py-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-100">
                  {ledger.days.map((day) => {
                    const isDateInOpeningPeriod = () => {
                      if (!ledger?.opening_attendance) return false;
                      const d = new Date(day.date);
                      const start = new Date(ledger.opening_attendance.period_start);
                      const end = new Date(ledger.opening_attendance.period_end);
                      return d >= start && d <= end;
                    };
                    const inOpening = isDateInOpeningPeriod();
                    return (
                      <tr key={day.date}>
                        <td className="px-4 py-3 font-medium text-zinc-900">
                          <div>{day.date}</div>
                          {inOpening && (
                            <span 
                              className="mt-1 inline-block rounded bg-amber-50 border border-amber-200 px-1.5 py-0.5 text-[10px] font-bold text-amber-700 leading-none"
                              title="This date is covered by opening attendance and will not be double-counted in salary."
                            >
                              Opening Period
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <select className="h-9 rounded-md border border-zinc-200 px-2 text-sm outline-none focus:border-brand-500" value={day.status} onChange={(event) => updateAttendance(day, { status: event.target.value as WorkerLedgerDay["status"] })}>
                            <option value="Present">Present</option>
                            <option value="Absent">Absent</option>
                            <option value="Half-day">Half-day</option>
                          </select>
                        </td>
                      <td className="px-4 py-3">
                        <input className="h-9 w-28 rounded-md border border-zinc-200 px-2 text-sm outline-none focus:border-brand-500" inputMode="decimal" type="number" value={day.production_qty || ""} onFocus={(event) => event.target.select()} onChange={(event) => updateAttendance(day, { production_qty: event.target.value })} />
                      </td>
                      <td className="px-4 py-3 text-right">{money(day.duty_amount)}</td>
                      <td className="px-4 py-3 text-right text-red-700">{money(day.advance_amount)}</td>
                      <td className="px-4 py-3 text-right">
                        <button className="inline-flex items-center gap-1 rounded-md border border-zinc-200 px-3 py-2 text-xs font-semibold text-zinc-700 hover:bg-zinc-50" type="button" onClick={() => setAdvanceDraft({ date: day.date, amount: 0 })}>
                          <Plus className="h-3.5 w-3.5" />
                          Advance
                        </button>
                      </td>
                    </tr>
                  )})}
                </tbody>
              </table>
            </div>
          </aside>
        </div>
      ) : null}

      {advanceDraft ? (
        <Modal title={`Add Advance - ${advanceDraft.date}`} onClose={() => setAdvanceDraft(null)}>
          <label className="grid gap-1 text-sm font-medium text-zinc-700">
            Amount
            <input className="h-10 rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" inputMode="decimal" type="number" value={advanceDraft.amount} onFocus={(event) => event.target.select()} onChange={(event) => setAdvanceDraft({ ...advanceDraft, amount: Number(event.target.value) })} />
          </label>
          <div className="mt-5 flex justify-end gap-3">
            <button className="h-10 rounded-md border border-zinc-200 px-4 text-sm font-semibold text-zinc-700" type="button" onClick={() => setAdvanceDraft(null)}>Cancel</button>
            <button className="h-10 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white" type="button" onClick={saveAdvance}>Save Advance</button>
          </div>
        </Modal>
      ) : null}

      {settlementOpen ? (
        <Modal title="Clear Hisab" onClose={() => setSettlementOpen(false)}>
          <div className="grid gap-4 sm:grid-cols-3">
            <DateField label="Duty From" value={settlement.duty_from_date} onChange={(duty_from_date) => setSettlement({ ...settlement, duty_from_date })} />
            <DateField label="Duty To" value={settlement.duty_to_date} onChange={(duty_to_date) => setSettlement({ ...settlement, duty_to_date })} />
            <DateField label="Advance Cut-off" value={settlement.advance_cutoff_date} onChange={(advance_cutoff_date) => setSettlement({ ...settlement, advance_cutoff_date })} />
          </div>
          {settlementPreview ? (
            <div className="mt-5 grid gap-3 rounded-lg border border-zinc-200 bg-zinc-50 p-4 text-sm sm:grid-cols-3">
              <Metric label="Total Duty" value={money(settlementPreview.total_duty_amount)} />
              <Metric label="Advance Deducted" value={money(settlementPreview.total_advance_deducted)} />
              <Metric label="Net Payable" value={money(settlementPreview.net_payable)} />
            </div>
          ) : null}
          <div className="mt-5 flex justify-end gap-3">
            <button className="h-10 rounded-md border border-zinc-200 px-4 text-sm font-semibold text-zinc-700" type="button" onClick={previewSettlement} disabled={isSaving}>Preview</button>
            <button className="inline-flex h-10 items-center gap-2 rounded-md bg-[#16A34A] px-4 text-sm font-semibold text-white hover:bg-[#16A34A]/90 disabled:bg-[#E5E7EB]" type="button" onClick={confirmSettlement} disabled={isSaving || !settlementPreview}>
              <Check className="h-4 w-4" />
              Confirm Settlement
            </button>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}

function DateField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="grid gap-1 text-sm font-medium text-zinc-700">
      {label}
      <input className="h-10 rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" type="date" value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase text-zinc-500">{label}</p>
      <p className="mt-1 text-lg font-semibold text-zinc-950">{value}</p>
    </div>
  );
}

function Modal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-zinc-950/40 px-4">
      <section className="w-full max-w-2xl rounded-lg bg-white p-5 shadow-xl">
        <div className="mb-5 flex items-center justify-between gap-4">
          <h2 className="text-lg font-semibold text-zinc-950">{title}</h2>
          <button className="grid h-9 w-9 place-items-center rounded-md border border-zinc-200 text-zinc-600" type="button" onClick={onClose}>x</button>
        </div>
        {children}
      </section>
    </div>
  );
}
