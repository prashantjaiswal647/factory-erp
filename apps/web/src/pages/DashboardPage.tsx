import { Activity, Clock3, PackageCheck, Percent, TrendingUp, WalletCards } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import EmptyState from "../components/EmptyState";
import LoadingState from "../components/LoadingState";
import { useDataRefresh } from "../context/DataRefreshContext";
import { api } from "../lib/api";
import { asNumber, formatCurrency, formatNumber, formatShortDate } from "../lib/format";

type DashboardStats = {
  monthly_net_profit: string;
  total_pending_recoveries: string;
  total_boxes_in_stock: number;
  overall_wastage_percent: string;
  recent_7_days: Array<{
    date: string;
    production_boxes: number;
    sales_boxes: number;
  }>;
  wastage_mix: {
    good_production_pcs: number;
    blank_waste_pcs: number;
    bottom_waste_kg: string;
  };
};

type LiveActivity = {
  id: number;
  customer_id: number;
  customer_name: string;
  activity_type: string;
  created_at: string;
};

const pieColors = ["#1f9d8a", "#dc2626"];

function formatRelativeActivityTime(value: string) {
  const createdAt = new Date(value).getTime();
  const elapsedSeconds = Math.max(Math.floor((Date.now() - createdAt) / 1000), 0);

  if (elapsedSeconds < 60) {
    return "just now";
  }

  const elapsedMinutes = Math.floor(elapsedSeconds / 60);
  if (elapsedMinutes < 60) {
    return `${elapsedMinutes} min ago`;
  }

  const elapsedHours = Math.floor(elapsedMinutes / 60);
  if (elapsedHours < 24) {
    return `${elapsedHours} hr ago`;
  }

  const elapsedDays = Math.floor(elapsedHours / 24);
  return `${elapsedDays} day${elapsedDays === 1 ? "" : "s"} ago`;
}

function formatActivityMessage(activity: LiveActivity) {
  if (activity.activity_type === "Viewed Store") {
    return `${activity.customer_name} viewed live rates`;
  }

  return `${activity.customer_name} ${activity.activity_type.toLowerCase()}`;
}

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [activities, setActivities] = useState<LiveActivity[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isActivityLoading, setIsActivityLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activityError, setActivityError] = useState<string | null>(null);
  const { refreshVersion } = useDataRefresh();

  useEffect(() => {
    async function loadDashboardStats() {
      setIsLoading(true);
      setError(null);

      try {
        const response = await api.get<DashboardStats>("/api/dashboard-stats");
        setStats(response.data);
      } catch {
        setError("Unable to load dashboard metrics.");
      } finally {
        setIsLoading(false);
      }
    }

    void loadDashboardStats();
  }, [refreshVersion]);

  useEffect(() => {
    async function loadLiveActivity() {
      setIsActivityLoading(true);
      setActivityError(null);

      try {
        const response = await api.get<LiveActivity[]>("/api/admin/live-activity");
        setActivities(response.data);
      } catch {
        setActivityError("Unable to load live activity.");
      } finally {
        setIsActivityLoading(false);
      }
    }

    void loadLiveActivity();
  }, [refreshVersion]);

  const productionSalesData = useMemo(() => {
    return (
      stats?.recent_7_days.map((row) => ({
        date: formatShortDate(row.date),
        Production: row.production_boxes,
        Sales: row.sales_boxes
      })) ?? []
    );
  }, [stats]);

  const wastageData = useMemo(() => {
    if (!stats) {
      return [];
    }

    return [
      { name: "Good Production", value: stats.wastage_mix.good_production_pcs },
      { name: "Blank Wastage", value: stats.wastage_mix.blank_waste_pcs }
    ];
  }, [stats]);

  if (isLoading) {
    return <LoadingState label="Loading command center..." />;
  }

  if (error || !stats) {
    return <EmptyState title="Dashboard unavailable" message={error ?? "Dashboard metrics were not returned."} />;
  }

  const kpis = [
    {
      label: "Monthly Net Profit",
      value: formatCurrency(stats.monthly_net_profit),
      icon: TrendingUp,
      color: asNumber(stats.monthly_net_profit) >= 0 ? "text-emerald-600" : "text-red-600"
    },
    {
      label: "Total Pending Recoveries",
      value: formatCurrency(stats.total_pending_recoveries),
      icon: WalletCards,
      color: asNumber(stats.total_pending_recoveries) > 0 ? "text-amber-700" : "text-emerald-600"
    },
    {
      label: "Total Boxes in Stock",
      value: formatNumber(stats.total_boxes_in_stock),
      icon: PackageCheck,
      color: "text-brand-700"
    },
    {
      label: "Overall Wastage %",
      value: `${formatNumber(stats.overall_wastage_percent, 2)}%`,
      icon: Percent,
      color: asNumber(stats.overall_wastage_percent) > 5 ? "text-red-600" : "text-emerald-600"
    }
  ];

  const hasWastageChartData = wastageData.some((row) => row.value > 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-normal text-zinc-950">Command Center</h1>
        <p className="mt-1 text-sm text-zinc-500">Paper cup factory performance, recoveries, stock, and wastage.</p>
      </div>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {kpis.map((kpi) => (
          <div key={kpi.label} className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
            <div className="flex items-center justify-between">
              <p className="text-sm text-zinc-500">{kpi.label}</p>
              <kpi.icon className={`h-4 w-4 ${kpi.color}`} aria-hidden="true" />
            </div>
            <p className={`mt-4 text-2xl font-semibold tabular-nums ${kpi.color}`}>{kpi.value}</p>
          </div>
        ))}
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.7fr)_minmax(360px,1fr)]">
        <div className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
          <div className="mb-5 flex items-center justify-between">
            <div>
              <h2 className="text-base font-semibold text-zinc-950">Recent 7 Days Production vs Sales</h2>
              <p className="mt-1 text-sm text-zinc-500">Boxes produced and sold by day.</p>
            </div>
          </div>
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={productionSalesData} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" vertical={false} />
                <XAxis dataKey="date" tickLine={false} axisLine={false} fontSize={12} />
                <YAxis tickLine={false} axisLine={false} fontSize={12} />
                <Tooltip
                  cursor={{ fill: "#f4f4f5" }}
                  contentStyle={{ borderRadius: 8, borderColor: "#e4e4e7", fontSize: 12 }}
                />
                <Legend />
                <Bar dataKey="Production" fill="#1f9d8a" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Sales" fill="#2563eb" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
          <div className="mb-5">
            <h2 className="text-base font-semibold text-zinc-950">Good Production vs Wastage</h2>
            <p className="mt-1 text-sm text-zinc-500">
              Bottom waste: {formatNumber(stats.wastage_mix.bottom_waste_kg, 3)} kg
            </p>
          </div>

          {hasWastageChartData ? (
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={wastageData} dataKey="value" nameKey="name" innerRadius={70} outerRadius={110} paddingAngle={2}>
                    {wastageData.map((entry, index) => (
                      <Cell key={entry.name} fill={pieColors[index % pieColors.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(value) => formatNumber(value as number)}
                    contentStyle={{ borderRadius: 8, borderColor: "#e4e4e7", fontSize: 12 }}
                  />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyState title="No wastage data" message="Production entries with packing profiles will populate this chart." />
          )}
        </div>
      </section>

      <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <h2 className="flex items-center gap-2 text-base font-semibold text-zinc-950">
              <Activity className="h-4 w-4 text-brand-700" />
              Live Activity Feed
            </h2>
            <p className="mt-1 text-sm text-zinc-500">Recent customer storefront visits and rate checks.</p>
          </div>
        </div>

        {isActivityLoading ? (
          <div className="space-y-3">
            {[0, 1, 2].map((item) => (
              <div className="h-12 animate-pulse rounded-md bg-zinc-100" key={item} />
            ))}
          </div>
        ) : activityError ? (
          <EmptyState title="Activity unavailable" message={activityError} />
        ) : activities.length === 0 ? (
          <EmptyState title="No customer activity yet" message="Storefront visits will appear here in real time." />
        ) : (
          <div className="grid gap-3 lg:grid-cols-2">
            {activities.map((activity) => (
              <div
                className="flex items-start gap-3 rounded-md border border-zinc-200 bg-zinc-50 p-3"
                key={activity.id}
              >
                <div className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-brand-50 text-brand-700">
                  <Clock3 className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-zinc-900">
                    {formatActivityMessage(activity)}{" "}
                    <span className="font-normal text-zinc-500">{formatRelativeActivityTime(activity.created_at)}</span>
                  </p>
                  <p className="mt-1 text-xs text-zinc-500">{activity.activity_type}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
