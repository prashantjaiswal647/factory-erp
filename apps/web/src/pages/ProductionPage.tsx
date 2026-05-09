import ProductionLog from "../components/ProductionLog";

export default function ProductionPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-950">Production</h1>
        <p className="mt-1 text-sm text-zinc-500">Shift-wise output, packing profile, and wastage calculations.</p>
      </div>

      <section className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm">
        <ProductionLog />
      </section>
    </div>
  );
}
