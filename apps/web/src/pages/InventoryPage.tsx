import LiveInventory from "../components/LiveInventory";

export default function InventoryPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-950">Inventory</h1>
        <p className="mt-1 text-sm text-zinc-500">Raw materials, packaging materials, and ready box stock.</p>
      </div>

      <section className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm">
        <LiveInventory />
      </section>
    </div>
  );
}
