import { Check, ReceiptText } from "lucide-react";
import { useEffect, useState } from "react";

import { createFactoryExpense, getFactoryExpenses } from "../lib/api";
import type { FactoryExpense } from "../lib/api";

type ExpenseForm = {
  expense_name: string;
  amount: number | "";
};

const initialForm: ExpenseForm = {
  expense_name: "",
  amount: ""
};

export default function FactoryExpensesPage() {
  const [form, setForm] = useState<ExpenseForm>(initialForm);
  const [expenses, setExpenses] = useState<FactoryExpense[]>([]);
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    void loadExpenses();
  }, []);

  async function loadExpenses() {
    const response = await getFactoryExpenses();
    setExpenses(response.data);
  }

  async function submit() {
    setError("");
    if (!form.expense_name.trim() || form.amount === "") {
      setError("Expense name and amount are required.");
      return;
    }

    setIsSaving(true);
    try {
      await createFactoryExpense({
        expense_name: form.expense_name.trim(),
        amount: form.amount,
        category: "General"
      });
      setToast("Expense added");
      setForm(initialForm);
      await loadExpenses();
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      {toast ? <Toast message={toast} onClose={() => setToast("")} /> : null}
      <header>
        <h1 className="text-2xl font-semibold text-zinc-950">Factory Expenses</h1>
        <p className="mt-1 text-sm text-zinc-500">Track factory-level spending for reporting and future AI tables.</p>
      </header>

      <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
        <div className="mb-5 flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-md bg-brand-50 text-brand-700">
            <ReceiptText className="h-5 w-5" />
          </span>
          <h2 className="text-lg font-semibold text-zinc-950">Add Expense</h2>
        </div>

        <div className="grid gap-4 md:grid-cols-[1fr_220px_auto] md:items-end">
          <TextField label="Expense Name" value={form.expense_name} onChange={(expense_name) => setForm({ ...form, expense_name })} />
          <NumberField label="Amount" value={form.amount} onChange={(amount) => setForm({ ...form, amount })} />
          <button className="inline-flex h-10 items-center gap-2 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 disabled:bg-zinc-300" disabled={isSaving} type="button" onClick={submit}>
            <Check className="h-4 w-4" />
            {isSaving ? "Adding..." : "Add Expense"}
          </button>
        </div>

        {error ? <p className="mt-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p> : null}
      </section>

      <section className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm">
        <div className="border-b border-zinc-200 p-5">
          <h2 className="text-lg font-semibold text-zinc-950">Recent Expenses</h2>
        </div>
        {expenses.length === 0 ? (
          <div className="p-6 text-sm text-zinc-500">No expenses added yet.</div>
        ) : (
          <table className="min-w-full divide-y divide-zinc-200 text-sm">
            <thead className="bg-zinc-50 text-left text-xs font-semibold uppercase text-zinc-500">
              <tr>
                <th className="px-5 py-3">Expense</th>
                <th className="px-5 py-3">Category</th>
                <th className="px-5 py-3">Amount</th>
                <th className="px-5 py-3">Time</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {expenses.map((expense) => (
                <tr key={expense.id} className="hover:bg-zinc-50">
                  <td className="px-5 py-3 font-medium text-zinc-950">{expense.expense_name}</td>
                  <td className="px-5 py-3 text-zinc-700">{expense.category}</td>
                  <td className="px-5 py-3 text-zinc-700">Rs {Number(expense.amount).toFixed(2)}</td>
                  <td className="px-5 py-3 text-zinc-500">{new Date(expense.timestamp).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

function TextField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-zinc-700">{label}</span>
      <input className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" placeholder={label} value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function NumberField({ label, value, onChange }: { label: string; value: number | ""; onChange: (value: number | "") => void }) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-zinc-700">{label}</span>
      <input className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" inputMode="decimal" placeholder="0.00" type="number" value={value} onChange={(event) => onChange(event.target.value === "" ? "" : Number(event.target.value))} />
    </label>
  );
}

function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  return (
    <button className="fixed right-5 top-20 z-50 rounded-md bg-[#16A34A] px-4 py-3 text-sm font-semibold text-white shadow-lg" type="button" onClick={onClose}>
      {message}
    </button>
  );
}
