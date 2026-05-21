import { Boxes, CheckCircle2, Factory, Gauge, RefreshCw, Settings, UserRound } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { getOnboardingOverview } from "../lib/api";
import type { OnboardingOverview } from "../lib/api";

export default function ConfigurationOverview() {
  const [data, setData] = useState<OnboardingOverview | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    setIsLoading(true);
    const response = await getOnboardingOverview();
    setData(response.data);
    setIsLoading(false);
  }

  const completion = useMemo(() => {
    if (!data) return 0;
    const done = [
      data.workers.length > 0,
      data.machines.length > 0,
      data.raw_material_metrics.length > 0,
      data.packaging_metrics.length > 0
    ].filter(Boolean).length;
    return Math.round((done / 4) * 100);
  }, [data]);

  if (isLoading) {
    return (
      <section className="rounded-lg border border-[#E5E7EB] bg-white p-5 shadow-sm">
        <div className="flex items-center gap-3 text-sm text-[#4B5563]">
          <RefreshCw className="h-4 w-4 animate-spin text-[#6D28D9]" />
          Loading configuration...
        </div>
      </section>
    );
  }

  if (!data) {
    return null;
  }

  return (
    <section className="space-y-4 rounded-lg border border-[#E5E7EB] bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-[#111827]">Configuration Overview</h2>
          <p className="mt-1 text-sm text-[#4B5563]">Current onboarding setup saved for this factory.</p>
        </div>
        <button className="inline-flex h-10 items-center gap-2 rounded-md border border-[#E5E7EB] px-3 text-sm font-semibold text-[#4B5563] hover:bg-[#FFF7ED]" type="button" onClick={load}>
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between text-xs font-semibold text-[#4B5563]">
          <span>{completion}% complete</span>
          <span>{data.workers.length + data.machines.length + data.raw_material_metrics.length + data.packaging_metrics.length} records</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-[#F3E8FF]">
          <div className="h-full rounded-full bg-[#6D28D9]" style={{ width: `${completion}%` }} />
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <SummaryCard icon={UserRound} title="Workers" count={data.workers.length} complete={data.workers.length > 0}>
          {data.workers.slice(0, 3).map((worker) => (
            <Line key={worker.id} label={worker.name} value={`Rs ${worker.daily_wages}/day`} />
          ))}
        </SummaryCard>

        <SummaryCard icon={Factory} title="Machines" count={data.machines.length} complete={data.machines.length > 0}>
          {data.machines.slice(0, 3).map((machine) => (
            <Line key={machine.id} label={machine.machine_number || `Machine ${machine.id}`} value={`${machine.mould_size_ml || "-"}ml`} />
          ))}
        </SummaryCard>

        <SummaryCard icon={Boxes} title="Raw Metrics" count={data.raw_material_metrics.length} complete={data.raw_material_metrics.length > 0}>
          {data.raw_material_metrics.slice(0, 3).map((metric) => (
            <Line key={metric.id} label={metric.material_type} value={`${metric.size_ml_or_mm} / ${metric.weight_per_sack_kg}kg`} />
          ))}
        </SummaryCard>

        <SummaryCard icon={Gauge} title="Packaging" count={data.packaging_metrics.length} complete={data.packaging_metrics.length > 0}>
          {data.packaging_metrics.slice(0, 3).map((metric) => (
            <Line key={metric.id} label={`${metric.cup_size_ml}ml`} value={`${metric.cups_per_box} packets/box`} />
          ))}
        </SummaryCard>
      </div>
    </section>
  );
}

function SummaryCard({
  icon: Icon,
  title,
  count,
  complete,
  children
}: {
  icon: typeof Settings;
  title: string;
  count: number;
  complete: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-[#E5E7EB] bg-[#FFF7ED] p-4">
      <div className="flex items-center justify-between gap-3">
        <span className="grid h-10 w-10 place-items-center rounded-md bg-white text-[#6D28D9] shadow-sm">
          <Icon className="h-5 w-5" />
        </span>
        {complete ? <CheckCircle2 className="h-5 w-5 text-[#16A34A]" /> : <span className="h-2 w-2 rounded-full bg-[#E5E7EB]" />}
      </div>
      <div className="mt-4">
        <p className="text-sm font-medium text-[#4B5563]">{title}</p>
        <p className="mt-1 text-2xl font-semibold text-[#111827]">{count}</p>
      </div>
      <div className="mt-4 space-y-2">
        {count === 0 ? <p className="text-sm text-[#4B5563]">No records yet</p> : children}
      </div>
    </div>
  );
}

function Line({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      <span className="truncate text-[#4B5563]">{label}</span>
      <span className="shrink-0 font-medium text-[#111827]">{value}</span>
    </div>
  );
}
