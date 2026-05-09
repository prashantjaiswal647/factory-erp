import CustomerBalances from "../components/CustomerBalances";

export default function CustomersPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-950">Customers</h1>
        <p className="mt-1 text-sm text-zinc-500">Party-wise billing and pending recoveries.</p>
      </div>

      <section className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm">
        <CustomerBalances />
      </section>
    </div>
  );
}
