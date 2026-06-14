import axios from "axios";
import { Activity, AlertTriangle, Building2, CreditCard, Database, FileClock, LayoutDashboard, MessageSquareText, Plus, Search, Shield, UsersRound } from "lucide-react";
import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import { Link, Navigate, Outlet, useNavigate, useParams } from "react-router-dom";

import PasswordInput from "../components/PasswordInput";
import ActivateSubscriptionButton from "../components/billing/ActivateSubscriptionButton";
import { superAdminApi } from "../lib/api";
import { toNumber } from "../lib/format";

const ADMIN_TOKEN_KEY = "munshi_super_admin_token";

type Owner = {
  id: number;
  full_name?: string | null;
  username: string;
  email?: string | null;
  phone_number?: string | null;
  factory_id: number;
  is_active: boolean;
  last_login_at?: string | null;
  factory?: FactoryRecord | null;
};

type FactoryRecord = {
  id: number;
  name: string;
  factory_name?: string | null;
  owner?: Owner | null;
  owner_id?: number | null;
  is_active: boolean;
  active_plan?: string | null;
  plan_name?: string | null;
  subscription_status?: string | null;
  payment_status?: string | null;
  billing_cycle?: string | null;
  trial_start_date?: string | null;
  trial_end_date?: string | null;
  subscription_start_date?: string | null;
  subscription_end_date?: string | null;
  plan_expires_at?: string | null;
  usage_limit?: number | null;
  token_limit?: number | null;
  admin_note?: string | null;
  created_at?: string | null;
  counts?: Record<string, number>;
  app_usage_count?: number;
  last_active_at?: string | null;
  total_token_usage?: number;
  monthly_token_usage?: number;
};

type DashboardStats = {
  total_factories: number;
  total_factory_owners: number;
  free_users_count: number;
  paid_users_count: number;
  trial_users_count: number;
  expired_users_count: number;
  active_subscriptions: number;
  pending_payments: number;
  total_usage_tokens: number;
  recent_signups: Owner[];
  recent_payments: Array<Record<string, unknown>>;
};

type FactorySheetOverview = {
  factory_id: number;
  factory_name: string;
  registered_owner_email?: string | null;
  phone_number?: string | null;
  google_spreadsheet_id?: string | null;
  created_at?: string | null;
};

type UsageSummary = {
  total_app_events: number;
  total_token_usage: number;
  monthly_token_usage: number;
  last_active_at?: string | null;
};

type SuperAdminSettings = {
  bulk_delete_enabled: boolean;
  factory_delete_enabled?: boolean;
  bulk_delete_max: number;
};

type BulkDeleteFactoryPreview = {
  factory_id: number;
  factory_name: string;
  owner_name?: string | null;
  owner_email?: string | null;
  owner_phone?: string | null;
  owner_action?: string;
  owner?: { id?: number | null; name?: string | null; email?: string | null; phone?: string | null; action?: string };
  record_counts: Record<string, number>;
  warnings?: string[];
};

type BulkDeletePreview = {
  factories: BulkDeleteFactoryPreview[];
  total_counts: Record<string, number>;
};

type BulkDeleteResponse = {
  deleted_factory_ids: number[];
  deleted_counts: Record<string, number>;
  message: string;
};

type SingleDeleteResponse = {
  deleted_factory_id: number;
  owner_action: string;
  deleted_counts: Record<string, number>;
  message: string;
};

type AuditLog = {
  id: number;
  admin_email: string;
  action_type: string;
  entity_type: string;
  entity_id?: string | null;
  note?: string | null;
  created_at: string;
};

type BriefingEvent = {
  factory_id: number;
  factory_name: string;
  briefing_date: string;
  at: string;
};

type BriefingOverview = {
  total_factories: number;
  telegram_connected_factories: number;
  active_briefing_factories: number;
  delivery_success_rate: number;
  delivery_failure_rate: number;
  last_successful_delivery: BriefingEvent | null;
  last_failed_delivery: BriefingEvent | null;
  metrics: {
    today_sent: number;
    today_failed: number;
    seven_day_sent: number;
    seven_day_failed: number;
    thirty_day_sent: number;
    thirty_day_failed: number;
    delivery_success_rate: number;
  };
};

type BriefingLog = {
  id: number;
  factory_id: number;
  factory_name: string;
  briefing_date: string;
  generated_at: string;
  sent_at?: string | null;
  status: "generated" | "sent" | "failed" | "skipped";
  channel: string;
  error_message?: string | null;
  retry_count: number;
};

type WeeklyDigestLog = {
  id: number;
  factory_id: number;
  factory_name: string;
  week_start: string;
  week_end: string;
  message_sent: boolean;
  status: "sent" | "failed";
  sent_at?: string | null;
  created_at: string;
  error_message?: string | null;
};

type BriefingFactoryHealth = {
  factory_id: number;
  factory_name: string;
  telegram_connected: boolean;
  last_briefing_sent?: string | null;
  last_briefing_failed?: string | null;
  delivery_percent: number;
  seven_day_success_percent: number;
  thirty_day_success_percent: number;
};

type CostSpikeEvent = {
  id: number;
  factory_id: number;
  factory_name: string;
  snapshot_date: string;
  variance_percent?: number | null;
  primary_driver?: string | null;
  status: "generated" | "sent" | "failed" | "skipped";
  channel: string;
  sent_at?: string | null;
};

type PageResult<T> = {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
};

type FactoryHealthRank = {
  factory_id: number;
  factory_name: string;
  snapshot_date: string;
  overall_score: number;
  health_status: "CRITICAL" | "WARNING" | "GOOD" | "EXCELLENT";
  largest_strength: string;
  largest_risk: string;
};

type FactoryHealthLeaderboard = {
  snapshot_date: string;
  average_health: number;
  top_factories: FactoryHealthRank[];
  lowest_factories: FactoryHealthRank[];
};

type ProfitRank = {
  factory_id: number;
  factory_name: string;
  profit_margin_percent: number;
  gross_profit_paise: number;
  profit_status: string;
  largest_profit_risk: string;
};

type ProfitLeaderboard = {
  snapshot_date: string;
  average_margin: number;
  top_factories: ProfitRank[];
  lowest_factories: ProfitRank[];
};

function useAdminToken() {
  const [token, setToken] = useState(() => sessionStorage.getItem(ADMIN_TOKEN_KEY));
  function save(nextToken: string) {
    sessionStorage.setItem(ADMIN_TOKEN_KEY, nextToken);
    setToken(nextToken);
  }
  function clear() {
    sessionStorage.removeItem(ADMIN_TOKEN_KEY);
    setToken(null);
  }
  return { token, save, clear };
}

export function SuperAdminLoginPage() {
  const navigate = useNavigate();
  const { token, save } = useAdminToken();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(() => sessionStorage.getItem("munshi_super_admin_auth_error") || "");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    sessionStorage.removeItem("munshi_super_admin_auth_error");
  }, []);

  if (token) return <Navigate to="/munshi-control-room/dashboard" replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      const response = await superAdminApi.post<{ access_token: string }>("/api/super-admin/login", { email, password });
      const nextToken = response.data.access_token;
      sessionStorage.setItem(ADMIN_TOKEN_KEY, nextToken);
      save(nextToken);
      navigate("/munshi-control-room/dashboard", { replace: true });
    } catch {
      setError("Invalid super admin credentials.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-[#111827] px-4 py-10 text-white">
      <form className="w-full max-w-md rounded-lg border border-white/10 bg-white p-7 text-[#111827] shadow-2xl" onSubmit={submit}>
        <div className="mx-auto grid h-12 w-12 place-items-center rounded-md bg-red-600 text-white">
          <Shield className="h-6 w-6" />
        </div>
        <h1 className="mt-4 text-center text-2xl font-black">Super Admin Only</h1>
        <p className="mt-2 text-center text-sm text-zinc-600">Hidden Munshi AI platform control room.</p>
        {error ? <p className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-700">{error}</p> : null}
        <label className="mt-5 block text-sm font-semibold">
          Email
          <input className="mt-1 h-11 w-full rounded-md border border-zinc-300 px-3 outline-none focus:ring-2 focus:ring-indigo-600" value={email} onChange={(event) => setEmail(event.target.value)} type="email" required />
        </label>
        <PasswordInput
          label="Password"
          value={password}
          onChange={setPassword}
          required
          className="mt-4"
          data-testid="super-admin-password-input"
        />
        <button className="mt-6 inline-flex h-11 w-full items-center justify-center rounded-md bg-[#6D28D9] text-sm font-bold text-white hover:bg-[#4C1D95] disabled:bg-zinc-300" disabled={isSubmitting} type="submit">
          {isSubmitting ? "Checking..." : "Enter Control Room"}
        </button>
      </form>
    </main>
  );
}

export function SuperAdminRoute() {
  const { token, clear } = useAdminToken();
  const [isChecking, setChecking] = useState(Boolean(token));

  useEffect(() => {
    let active = true;
    if (!token) {
      setChecking(false);
      return;
    }
    async function verifyToken() {
      try {
        await superAdminApi.get("/api/super-admin/me");
        if (active) setChecking(false);
      } catch {
        if (!active) return;
        clear();
        sessionStorage.setItem("munshi_super_admin_auth_error", "Session expired, please login again.");
        setChecking(false);
      }
    }
    void verifyToken();
    return () => {
      active = false;
    };
  }, [token]);

  if (!token) return <Navigate to="/munshi-control-room" replace />;
  if (isChecking) {
    return (
      <main className="grid min-h-screen place-items-center bg-zinc-100 px-4 text-sm font-bold text-zinc-700">
        Checking control room session...
      </main>
    );
  }
  return <SuperAdminShell />;
}

function SuperAdminShell() {
  const { clear } = useAdminToken();
  const navigate = useNavigate();
  const links = [
    ["/munshi-control-room/dashboard", "Dashboard", LayoutDashboard],
    ["/munshi-control-room/owners", "Owners", UsersRound],
    ["/munshi-control-room/factories", "Factories", Building2],
    ["/munshi-control-room/subscriptions", "Subscriptions", CreditCard],
    ["/munshi-control-room/payments", "Payments", Database],
    ["/munshi-control-room/briefings", "Briefing Delivery", MessageSquareText],
    ["/munshi-control-room/usage", "Usage", Activity],
    ["/munshi-control-room/audit-logs", "Audit Logs", FileClock],
  ] as const;
  return (
    <div data-testid="super-admin-layout" className="min-h-screen overflow-x-hidden bg-zinc-100 text-zinc-950">
      <header className="border-b border-zinc-200 bg-white px-4 py-4 lg:px-5">
        <div className="mx-auto max-w-[1440px] flex w-full flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs font-black uppercase tracking-wider text-red-600">Super Admin Only</p>
            <h1 className="text-xl font-black">Munshi Control Room</h1>
          </div>
          <button className="inline-flex h-10 items-center justify-center rounded-md border border-zinc-300 px-4 text-sm font-bold hover:bg-zinc-50" type="button" onClick={() => { clear(); navigate("/munshi-control-room", { replace: true }); }}>
            Sign Out
          </button>
        </div>
      </header>
      <div className="mx-auto max-w-[1440px] grid w-full gap-4 px-3 py-4 sm:px-4 lg:grid-cols-[240px_minmax(0,1fr)] lg:gap-5 lg:px-5 lg:py-5">
        <nav data-testid="super-admin-sidebar" className="h-fit rounded-lg border border-zinc-200 bg-white p-3 shadow-sm lg:sticky lg:top-4">
          {links.map(([href, label, Icon]) => (
            <Link key={href} className="flex h-10 items-center gap-3 rounded-md px-3 text-sm font-semibold text-zinc-700 hover:bg-zinc-100" to={href}>
              <Icon className="h-4 w-4 text-[#6D28D9]" />
              {label}
            </Link>
          ))}
        </nav>
        <section data-testid="super-admin-main" className="min-w-0 w-full">
          <Outlet />
        </section>
      </div>
    </div>
  );
}

function useAdminData<T>(path: string, fallback: T) {
  const [data, setData] = useState<T>(fallback);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const reload = async () => {
    setIsLoading(true);
    setError("");
    try {
      const response = await superAdminApi.get<T>(path);
      setData(response.data);
    } catch (caught) {
      setError(getAdminApiError(caught, "Request failed"));
    } finally {
      setIsLoading(false);
    }
  };
  useEffect(() => {
    void reload();
  }, [path]);
  return { data, error, isLoading, reload };
}

function Panel({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-lg font-black">{title}</h2>
        {action}
      </div>
      {children}
    </div>
  );
}

function ErrorNote({ message }: { message?: string }) {
  if (!message) return null;
  return <p className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-700">{message}</p>;
}

function getAdminApiError(caught: unknown, fallback: string) {
  if (!axios.isAxiosError(caught)) return fallback;
  const detail = caught.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => item?.msg || JSON.stringify(item)).join(", ");
  return caught.message || fallback;
}

function SuccessNote({ message }: { message?: string }) {
  if (!message) return null;
  return <p data-testid="bulk-delete-success-toast" className="mb-4 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm font-semibold text-emerald-700">{message}</p>;
}

function EmptyState({ children }: { children: ReactNode }) {
  return <p className="rounded-md border border-dashed border-zinc-300 p-5 text-center text-sm font-semibold text-zinc-500">{children}</p>;
}

export function SuperAdminDashboardPage() {
  const { data, error, isLoading } = useAdminData<DashboardStats>("/api/super-admin/dashboard", {
    total_factories: 0,
    total_factory_owners: 0,
    free_users_count: 0,
    paid_users_count: 0,
    trial_users_count: 0,
    expired_users_count: 0,
    active_subscriptions: 0,
    pending_payments: 0,
    total_usage_tokens: 0,
    recent_signups: [],
    recent_payments: [],
  });
  const sheetOverview = useAdminData<FactorySheetOverview[]>("/api/admin/overview", []);
  const healthLeaderboard = useAdminData<FactoryHealthLeaderboard>("/api/admin/factory-health/leaderboard?limit=5", {
    snapshot_date: "",
    average_health: 0,
    top_factories: [],
    lowest_factories: [],
  });
  const profitLeaderboard = useAdminData<ProfitLeaderboard>("/api/admin/profit-leaderboard?limit=5", {
    snapshot_date: "",
    average_margin: 0,
    top_factories: [],
    lowest_factories: [],
  });
  const [selectedFactoryId, setSelectedFactoryId] = useState("");
  const activeSheetFactories = useMemo(
    () => sheetOverview.data.filter((factory) => Boolean(factory.google_spreadsheet_id)),
    [sheetOverview.data],
  );
  useEffect(() => {
    if (selectedFactoryId || activeSheetFactories.length === 0) return;
    setSelectedFactoryId(String(activeSheetFactories[0].factory_id));
  }, [activeSheetFactories, selectedFactoryId]);
  const selectedFactory = useMemo(
    () => sheetOverview.data.find((factory) => String(factory.factory_id) === selectedFactoryId) || null,
    [sheetOverview.data, selectedFactoryId],
  );
  const spreadsheetSrc = selectedFactory?.google_spreadsheet_id
    ? `https://docs.google.com/spreadsheets/d/${selectedFactory.google_spreadsheet_id}/edit?usp=sharing`
    : "";
  const cards = [
    ["Total factories", data.total_factories],
    ["Factory owners", data.total_factory_owners],
    ["Free users", data.free_users_count],
    ["Paid users", data.paid_users_count],
    ["Trial users", data.trial_users_count],
    ["Expired users", data.expired_users_count],
    ["Active subscriptions", data.active_subscriptions],
    ["Pending payments", data.pending_payments],
    ["Tokens used", data.total_usage_tokens],
  ];
  return (
    <div className="space-y-5">
      <Panel title="Platform Dashboard">
        <ErrorNote message={error} />
        {isLoading ? <p>Loading...</p> : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {cards.map(([label, value]) => <Metric key={label} label={String(label)} value={String(value)} />)}
          </div>
        )}
      </Panel>
      <Panel title="Recent Signups">
        <OwnerTable owners={data.recent_signups || []} />
      </Panel>
      <Panel title="Factory Health Leaderboard">
        <ErrorNote message={healthLeaderboard.error} />
        {healthLeaderboard.isLoading ? <p>Loading health scores...</p> : (
          <div className="space-y-4">
            <Metric label="Average Health" value={`${toNumber(healthLeaderboard.data.average_health).toFixed(1)}/100`} />
            <div className="grid gap-4 lg:grid-cols-2">
              <HealthRankTable title="Top Factories" rows={healthLeaderboard.data.top_factories} />
              <HealthRankTable title="Lowest Factories" rows={healthLeaderboard.data.lowest_factories} />
            </div>
          </div>
        )}
      </Panel>
      <Panel title="Profit Intelligence Leaderboard">
        <ErrorNote message={profitLeaderboard.error} />
        {profitLeaderboard.isLoading ? <p>Loading profit margins...</p> : (
          <div className="space-y-4">
            <Metric label="Average Margin" value={`${toNumber(profitLeaderboard.data.average_margin).toFixed(1)}%`} />
            <div className="grid gap-4 lg:grid-cols-2">
              <ProfitRankTable title="Top Profitable Factories" rows={profitLeaderboard.data.top_factories} />
              <ProfitRankTable title="Lowest Profit Factories" rows={profitLeaderboard.data.lowest_factories} />
            </div>
          </div>
        )}
      </Panel>
      <Panel
        title="Live Spreadsheet Audit Room"
        action={
          <select
            className="h-10 min-w-[220px] rounded-md border border-zinc-300 bg-white px-3 text-sm font-semibold outline-none focus:ring-2 focus:ring-indigo-600"
            value={selectedFactoryId}
            onChange={(event) => setSelectedFactoryId(event.target.value)}
          >
            <option value="">Select Factory ID</option>
            {sheetOverview.data.map((factory) => (
              <option key={factory.factory_id} value={factory.factory_id}>
                #{factory.factory_id} - {factory.factory_name}
              </option>
            ))}
          </select>
        }
      >
        <ErrorNote message={sheetOverview.error} />
        {sheetOverview.isLoading ? <p>Loading factory sheets...</p> : (
          <div className="space-y-4">
            <FactorySheetOverviewTable factories={sheetOverview.data} selectedFactoryId={selectedFactoryId} onSelect={setSelectedFactoryId} />
            <div className="bg-white p-4 rounded-xl">
              {spreadsheetSrc ? (
                <iframe
                  key={spreadsheetSrc}
                  title={`Live Google Sheet for ${selectedFactory?.factory_name || selectedFactoryId}`}
                  src={spreadsheetSrc}
                  className="w-full h-[650px] border border-gray-200 rounded-lg shadow-md relative block"
                />
              ) : (
                <EmptyState>{selectedFactory ? "Selected factory does not have a Google Spreadsheet ID yet." : "Select a Factory ID to inspect its live Google Sheet."}</EmptyState>
              )}
            </div>
          </div>
        )}
      </Panel>
    </div>
  );
}

function HealthRankTable({ title, rows }: { title: string; rows: FactoryHealthRank[] }) {
  return (
    <div className="rounded-lg border border-zinc-200 p-3">
      <h3 className="text-sm font-black">{title}</h3>
      <div className="mt-3 space-y-2">
        {rows.map((row) => (
          <div key={row.factory_id} className="flex items-center justify-between rounded-md bg-zinc-50 px-3 py-2 text-sm">
            <div className="min-w-0">
              <p className="truncate font-semibold">{row.factory_name}</p>
              <p className="text-xs text-zinc-500">{row.health_status} · Risk: {row.largest_risk}</p>
            </div>
            <strong>{toNumber(row.overall_score).toFixed(1)}</strong>
          </div>
        ))}
        {rows.length === 0 ? <p className="text-sm text-zinc-500">No health snapshots available.</p> : null}
      </div>
    </div>
  );
}

function ProfitRankTable({ title, rows }: { title: string; rows: ProfitRank[] }) {
  return (
    <div className="rounded-lg border border-zinc-200 p-3">
      <h3 className="text-sm font-black">{title}</h3>
      <div className="mt-3 space-y-2">
        {rows.map((row) => (
          <div key={row.factory_id} className="flex items-center justify-between rounded-md bg-zinc-50 px-3 py-2 text-sm">
            <div className="min-w-0">
              <p className="truncate font-semibold">{row.factory_name}</p>
              <p className="text-xs text-zinc-500">{row.profit_status} · Risk: {row.largest_profit_risk}</p>
            </div>
            <strong>{toNumber(row.profit_margin_percent).toFixed(1)}%</strong>
          </div>
        ))}
        {rows.length === 0 ? <p className="text-sm text-zinc-500">No profit snapshots available.</p> : null}
      </div>
    </div>
  );
}

function FactorySheetOverviewTable({ factories, selectedFactoryId, onSelect }: { factories: FactorySheetOverview[]; selectedFactoryId: string; onSelect: (factoryId: string) => void }) {
  const navigate = useNavigate();
  if (factories.length === 0) return <EmptyState>No active factory spreadsheet metadata found.</EmptyState>;
  return (
    <div className="w-full overflow-x-auto block">
      <table className="min-w-full divide-y divide-zinc-200 text-sm">
        <thead className="bg-zinc-50">
          <tr>{["Factory ID", "Factory", "Owner Email", "Phone", "Google Spreadsheet ID", "Created", "Actions"].map((head) => <th key={head} className="px-3 py-2 text-left font-bold text-zinc-600">{head}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-zinc-100">
          {factories.map((factory) => {
            const selected = String(factory.factory_id) === selectedFactoryId;
            return (
              <tr key={factory.factory_id} className={selected ? "bg-indigo-50" : ""}>
                <td className="px-3 py-2 font-black">#{factory.factory_id}</td>
                <td className="px-3 py-2 font-semibold">
                  <button className="text-left font-bold text-[#6D28D9] hover:underline" type="button" onClick={() => navigate(`/munshi-control-room/factory/${factory.factory_id}`)}>
                    {factory.factory_name}
                  </button>
                </td>
                <td className="px-3 py-2">{factory.registered_owner_email || "-"}</td>
                <td className="px-3 py-2">{factory.phone_number || "-"}</td>
                <td className="px-3 py-2 font-mono text-xs">{factory.google_spreadsheet_id || "-"}</td>
                <td className="px-3 py-2">{formatDate(factory.created_at)}</td>
                <td className="px-3 py-2">
                  <div className="flex flex-col gap-2 sm:flex-row">
                    <button className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs font-bold hover:bg-zinc-50 disabled:opacity-50" type="button" disabled={selected} onClick={() => onSelect(String(factory.factory_id))}>
                      {selected ? "Selected" : "Preview"}
                    </button>
                    <button className="rounded-md bg-slate-900 px-3 py-1.5 text-xs font-bold text-white hover:bg-slate-700" type="button" onClick={() => navigate(`/munshi-control-room/factory/${factory.factory_id}`)}>
                      Open Google Sheet Grid
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="rounded-md border border-zinc-200 bg-zinc-50 p-4"><p className="text-sm text-zinc-500">{label}</p><p className="mt-2 text-2xl font-black">{value}</p></div>;
}

function SearchBox({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <div className="relative">
      <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
      <input className="h-10 rounded-md border border-zinc-300 pl-9 pr-3 text-sm outline-none focus:ring-2 focus:ring-indigo-600" placeholder="Search" value={value} onChange={(event) => onChange(event.target.value)} />
    </div>
  );
}

export function SuperAdminOwnersPage() {
  const [search, setSearch] = useState("");
  const [isCreateOpen, setCreateOpen] = useState(false);
  const [editingSubscription, setEditingSubscription] = useState<Owner | null>(null);
  const [mutationError, setMutationError] = useState("");
  const { data, error, isLoading, reload } = useAdminData<Owner[]>(`/api/super-admin/owners${search ? `?search=${encodeURIComponent(search)}` : ""}`, []);
  async function setOwnerStatus(owner: Owner, isActive: boolean) {
    if (!window.confirm(`${isActive ? "Enable" : "Disable"} owner login for ${owner.full_name || owner.username}?`)) return;
    setMutationError("");
    try {
      await superAdminApi.patch(`/api/super-admin/owners/${owner.id}/status`, { is_active: isActive, note: "Updated from control room" });
      await reload();
    } catch (caught) {
      setMutationError(getAdminApiError(caught, "Owner status update failed"));
    }
  }
  return (
    <Panel
      title="Factory Owner Management"
      action={
        <div className="flex flex-col gap-2 sm:flex-row">
          <SearchBox value={search} onChange={setSearch} />
          <button className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-[#6D28D9] px-4 text-sm font-bold text-white hover:bg-[#4C1D95]" type="button" onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" />
            Add Factory Owner
          </button>
        </div>
      }
    >
      <ErrorNote message={error} />
      <ErrorNote message={mutationError} />
      {isLoading ? <p>Loading owners...</p> : <OwnerTable owners={data} onStatus={setOwnerStatus} onEditSubscription={setEditingSubscription} />}
      {isCreateOpen ? <CreateOwnerModal onClose={() => setCreateOpen(false)} onCreated={reload} /> : null}
      {editingSubscription?.factory ? <SubscriptionModal factory={editingSubscription.factory} onClose={() => setEditingSubscription(null)} onSaved={reload} /> : null}
    </Panel>
  );
}

function OwnerTable({ owners, onStatus, onEditSubscription }: { owners: Owner[]; onStatus?: (owner: Owner, isActive: boolean) => void; onEditSubscription?: (owner: Owner) => void }) {
  if (owners.length === 0) return <EmptyState>No real factory owners found yet.</EmptyState>;
  return (
    <div className="w-full overflow-x-auto block">
      <table className="min-w-full divide-y divide-zinc-200 text-sm">
        <thead className="bg-zinc-50"><tr>{["Owner", "Email", "Phone", "Factory", "Plan", "Sub Status", "Payment", "Tokens", "Usage", "Last Active", "Active", "Actions"].map((head) => <th key={head} className="px-3 py-2 text-left font-bold text-zinc-600">{head}</th>)}</tr></thead>
        <tbody className="divide-y divide-zinc-100">
          {owners.map((owner) => (
            <tr key={owner.id}>
              <td className="px-3 py-2 font-semibold">{owner.full_name || owner.username}<div className="text-xs text-zinc-500">#{owner.id}</div></td>
              <td className="px-3 py-2">{owner.email || "-"}</td>
              <td className="px-3 py-2">{owner.phone_number || "-"}</td>
              <td className="px-3 py-2">{owner.factory?.factory_name || owner.factory?.name || owner.factory_id}</td>
              <td className="px-3 py-2">{owner.factory?.plan_name || "-"}</td>
              <td className="px-3 py-2">{owner.factory?.subscription_status || "-"}</td>
              <td className="px-3 py-2">{owner.factory?.payment_status || "-"}</td>
              <td className="px-3 py-2">{owner.factory?.total_token_usage ?? 0} / {owner.factory?.token_limit ?? "-"}</td>
              <td className="px-3 py-2">{owner.factory?.app_usage_count ?? 0}</td>
              <td className="px-3 py-2">{formatDate(owner.factory?.last_active_at || owner.last_login_at)}</td>
              <td className="px-3 py-2">{owner.is_active ? "Active" : "Inactive"}</td>
              <td className="px-3 py-2">
                <div className="flex gap-2">
                  <Link className="text-xs font-bold text-[#6D28D9]" to={`/munshi-control-room/factories/${owner.factory_id}`}>View</Link>
                  {onEditSubscription && owner.factory ? <button className="text-xs font-bold text-[#6D28D9]" type="button" onClick={() => onEditSubscription(owner)}>Edit Subscription</button> : null}
                  {onStatus ? <button className="text-xs font-bold text-red-700" type="button" onClick={() => onStatus(owner, !owner.is_active)}>{owner.is_active ? "Disable" : "Enable"}</button> : null}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CreateOwnerModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => Promise<void> }) {
  const [form, setForm] = useState({
    owner_name: "",
    email: "",
    country_code: "+91",
    phone_number: "",
    password: "",
    confirm_password: "",
    factory_name: "",
    factory_address: "",
    initial_subscription_plan: "trial",
    subscription_status: "trial_active",
    payment_status: "free",
    billing_cycle: "none",
    subscription_end_date: "",
    usage_limit: "",
    token_limit: "",
    notes: "",
  });
  const [error, setError] = useState("");
  const [isSaving, setSaving] = useState(false);
  function setField(name: string, value: string) {
    setForm((current) => ({ ...current, [name]: value }));
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (form.password !== form.confirm_password) {
      setError("Password and confirm password must match.");
      return;
    }
    setSaving(true);
    try {
      await superAdminApi.post("/api/super-admin/owners", {
        ...form,
        email: form.email.trim() === "" ? null : form.email.trim(),
        phone_number: form.phone_number.trim() === "" ? null : form.phone_number.trim(),
        factory_address: form.factory_address.trim() === "" ? null : form.factory_address.trim(),
        notes: form.notes.trim() === "" ? null : form.notes.trim(),
        billing_cycle: form.billing_cycle === "none" ? null : form.billing_cycle,
        subscription_end_date: form.subscription_end_date ? new Date(form.subscription_end_date).toISOString() : null,
        usage_limit: form.usage_limit ? Number(form.usage_limit) : null,
        token_limit: form.token_limit ? Number(form.token_limit) : null,
      });
      await onCreated();
      onClose();
    } catch (caught) {
      setError(getAdminApiError(caught, "Create owner failed"));
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4">
      <form className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-lg bg-white p-5 shadow-xl" onSubmit={save}>
        <h3 className="text-lg font-black">Add Factory Owner</h3>
        <ErrorNote message={error} />
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <Input label="Owner Name" value={form.owner_name} onChange={(value) => setField("owner_name", value)} />
          <Input label="Email" value={form.email} onChange={(value) => setField("email", value)} type="email" />
          <label className="text-sm font-semibold">
            Phone Country Code
            <select className="mt-1 h-10 w-full rounded-md border border-zinc-300 px-3 outline-none focus:ring-2 focus:ring-indigo-600" value={form.country_code} onChange={(event) => setField("country_code", event.target.value)}>
              <option value="+91">India (+91)</option>
              <option value="+1">United States (+1)</option>
              <option value="+44">United Kingdom (+44)</option>
              <option value="+971">UAE (+971)</option>
            </select>
          </label>
          <Input label="Phone Number" value={form.phone_number} onChange={(value) => setField("phone_number", value)} />
          <PasswordInput label="Password" value={form.password} onChange={(value) => setField("password", value)} data-testid="super-admin-owner-password-input" />
          <PasswordInput label="Confirm Password" value={form.confirm_password} onChange={(value) => setField("confirm_password", value)} data-testid="super-admin-owner-confirm-password-input" />
          <Input label="Factory Name" value={form.factory_name} onChange={(value) => setField("factory_name", value)} />
          <Input label="Factory Address" value={form.factory_address} onChange={(value) => setField("factory_address", value)} />
          <SelectInput label="Initial Subscription Plan" value={form.initial_subscription_plan} onChange={(value) => setField("initial_subscription_plan", value)} options={["free", "trial", "basic", "pro", "enterprise", "custom"]} />
          <SelectInput label="Subscription Status" value={form.subscription_status} onChange={(value) => setField("subscription_status", value)} options={["active", "inactive", "trial_active", "trial", "expired", "suspended"]} />
          <SelectInput label="Payment Status" value={form.payment_status} onChange={(value) => setField("payment_status", value)} options={["free", "paid", "pending", "overdue", "failed"]} />
          <SelectInput label="Billing Cycle" value={form.billing_cycle} onChange={(value) => setField("billing_cycle", value)} options={["none", "monthly", "yearly", "custom"]} />
          <Input label="Subscription End Date" value={form.subscription_end_date} onChange={(value) => setField("subscription_end_date", value)} type="date" />
          <Input label="Usage Limit" value={form.usage_limit} onChange={(value) => setField("usage_limit", value)} type="number" />
          <Input label="Token Limit" value={form.token_limit} onChange={(value) => setField("token_limit", value)} type="number" />
          <Input label="Notes" value={form.notes} onChange={(value) => setField("notes", value)} />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button className="rounded-md border px-4 py-2 text-sm font-bold" type="button" onClick={onClose}>Cancel</button>
          <button data-testid="add-owner-submit" className="rounded-md bg-[#6D28D9] px-4 py-2 text-sm font-bold text-white disabled:bg-zinc-300" type="submit" disabled={isSaving}>{isSaving ? "Creating..." : "Create Owner"}</button>
        </div>
      </form>
    </div>
  );
}

export function SuperAdminFactoriesPage() {
  const [search, setSearch] = useState("");
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [preview, setPreview] = useState<BulkDeletePreview | null>(null);
  const [singlePreview, setSinglePreview] = useState<BulkDeleteFactoryPreview | null>(null);
  const [previewError, setPreviewError] = useState("");
  const [isPreviewLoading, setPreviewLoading] = useState(false);
  const [successMessage, setSuccessMessage] = useState("");
  const settings = useAdminData<SuperAdminSettings>("/api/super-admin/settings", { bulk_delete_enabled: false, bulk_delete_max: 50 });
  const { data, error, isLoading, reload } = useAdminData<FactoryRecord[]>(`/api/super-admin/factories${search ? `?search=${encodeURIComponent(search)}` : ""}`, []);
  const maxDelete = settings.data.bulk_delete_max || 50;
  const selectedCount = selectedIds.length;
  function toggleFactory(factoryId: number) {
    setSelectedIds((current) => {
      if (current.includes(factoryId)) return current.filter((id) => id !== factoryId);
      if (current.length >= maxDelete) return current;
      return [...current, factoryId];
    });
  }
  function toggleAll() {
    const pageIds = data.map((factory) => factory.id);
    const allSelected = pageIds.length > 0 && pageIds.every((id) => selectedIds.includes(id));
    if (allSelected) {
      setSelectedIds((current) => current.filter((id) => !pageIds.includes(id)));
      return;
    }
    setSelectedIds(Array.from(new Set([...selectedIds, ...pageIds])).slice(0, maxDelete));
  }
  async function openDeletePreview() {
    setPreviewError("");
    setPreviewLoading(true);
    try {
      const response = await superAdminApi.post<BulkDeletePreview>("/api/super-admin/factories/bulk-delete-preview", { factory_ids: selectedIds });
      setPreview(response.data);
    } catch (caught) {
      setPreviewError(getAdminApiError(caught, "Preview failed"));
    } finally {
      setPreviewLoading(false);
    }
  }
  async function openSingleDeletePreview(factory: FactoryRecord) {
    setPreviewError("");
    setPreviewLoading(true);
    try {
      const response = await superAdminApi.get<BulkDeleteFactoryPreview>(`/api/super-admin/factories/${factory.id}/delete-preview`);
      setSinglePreview(response.data);
    } catch (caught) {
      setPreviewError(getAdminApiError(caught, "Preview failed"));
    } finally {
      setPreviewLoading(false);
    }
  }
  async function handleDeleted(response: BulkDeleteResponse) {
    setSuccessMessage(response.message);
    setPreview(null);
    setSelectedIds([]);
    await reload();
    await settings.reload();
  }
  return (
    <Panel title="Factory Management" action={<SearchBox value={search} onChange={setSearch} />}>
      <SuccessNote message={successMessage} />
      <ErrorNote message={error} />
      <ErrorNote message={previewError} />
      {settings.error ? <ErrorNote message={settings.error} /> : null}
      {!settings.data.bulk_delete_enabled ? <p className="mb-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-800">Bulk delete is disabled by server configuration. Preview is available, final deletion is blocked.</p> : null}
      {!settings.data.factory_delete_enabled ? <p className="mb-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-800">Single factory delete is disabled by server configuration. Preview is available, final deletion is blocked.</p> : null}
      {selectedCount > 0 ? (
        <div className="mb-4 flex flex-col gap-2 rounded-md border border-red-200 bg-red-50 p-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm font-bold text-red-800">{selectedCount} {selectedCount === 1 ? "factory" : "factories"} selected</p>
          <button
            data-testid="bulk-delete-factories-button"
            className="inline-flex h-10 items-center justify-center rounded-md bg-red-700 px-4 text-sm font-bold text-white hover:bg-red-800 disabled:bg-zinc-300"
            type="button"
            disabled={isPreviewLoading}
            onClick={openDeletePreview}
          >
            {isPreviewLoading ? "Loading Preview..." : "Delete Selected Factories"}
          </button>
        </div>
      ) : null}
      {selectedCount >= maxDelete ? <p className="mb-3 text-sm font-semibold text-amber-700">You can delete up to {maxDelete} factories at a time.</p> : null}
      {isLoading ? <p>Loading factories...</p> : (
        <FactoryTable
          factories={data}
          selectedIds={selectedIds}
          onToggle={toggleFactory}
          onToggleAll={toggleAll}
          maxSelected={maxDelete}
          onSingleDelete={openSingleDeletePreview}
        />
      )}
      {preview ? (
        <BulkDeleteModal
          preview={preview}
          settings={settings.data}
          onClose={() => setPreview(null)}
          onDeleted={handleDeleted}
        />
      ) : null}
      {singlePreview ? (
        <SingleDeleteModal
          preview={singlePreview}
          settings={settings.data}
          onClose={() => setSinglePreview(null)}
          onDeleted={async (response) => {
            setSuccessMessage(response.message);
            setSinglePreview(null);
            setSelectedIds((current) => current.filter((id) => id !== response.deleted_factory_id));
            await reload();
            await settings.reload();
          }}
        />
      ) : null}
    </Panel>
  );
}

function FactoryTable({ factories, selectedIds, onToggle, onToggleAll, maxSelected, onSingleDelete }: { factories: FactoryRecord[]; selectedIds?: number[]; onToggle?: (factoryId: number) => void; onToggleAll?: () => void; maxSelected?: number; onSingleDelete?: (factory: FactoryRecord) => void }) {
  if (factories.length === 0) return <EmptyState>No factories found.</EmptyState>;
  const selectable = Boolean(onToggle && onToggleAll && selectedIds);
  const allSelected = selectable && factories.every((factory) => selectedIds?.includes(factory.id));
  return (
    <div className="w-full overflow-x-auto block">
      <table className="min-w-full divide-y divide-zinc-200 text-sm">
        <thead className="bg-zinc-50"><tr>{selectable ? <th className="px-3 py-2 text-left font-bold text-zinc-600"><input data-testid="factory-select-all" type="checkbox" checked={Boolean(allSelected)} onChange={onToggleAll} /></th> : null}{["Factory", "Owner", "Email", "Phone", "Plan", "Subscription", "Payment", "Tokens", "Usage", "Last Active", "Created", "Actions"].map((head) => <th key={head} className="px-3 py-2 text-left font-bold text-zinc-600">{head}</th>)}</tr></thead>
        <tbody className="divide-y divide-zinc-100">
          {factories.map((factory) => (
            <tr key={factory.id}>
              {selectable ? (
                <td className="px-3 py-2">
                  <input
                    data-testid="factory-row-checkbox"
                    type="checkbox"
                    checked={selectedIds?.includes(factory.id) || false}
                    disabled={!selectedIds?.includes(factory.id) && selectedIds?.length === maxSelected}
                    onChange={() => onToggle?.(factory.id)}
                    aria-label={`Select ${factory.factory_name || factory.name}`}
                  />
                </td>
              ) : null}
              <td className="px-3 py-2 font-semibold">{factory.factory_name || factory.name}<div className="text-xs text-zinc-500">#{factory.id}</div></td>
              <td className="px-3 py-2">{factory.owner?.full_name || factory.owner?.username || "-"}</td>
              <td className="px-3 py-2">{factory.owner?.email || "-"}</td>
              <td className="px-3 py-2">{factory.owner?.phone_number || "-"}</td>
              <td className="px-3 py-2">{factory.plan_name || factory.active_plan || "-"}</td>
              <td className="px-3 py-2">{factory.subscription_status || "-"}</td>
              <td className="px-3 py-2">{factory.payment_status || "-"}</td>
              <td className="px-3 py-2">{factory.total_token_usage ?? 0} / {factory.token_limit ?? "-"}</td>
              <td className="px-3 py-2">{factory.app_usage_count ?? 0}</td>
              <td className="px-3 py-2">{formatDate(factory.last_active_at)}</td>
              <td className="px-3 py-2">{formatDate(factory.created_at)}</td>
              <td className="px-3 py-2">
                <div className="flex gap-2">
                  <Link className="text-xs font-bold text-[#6D28D9]" to={`/munshi-control-room/factories/${factory.id}`}>Details</Link>
                  {onSingleDelete ? <button className="text-xs font-bold text-red-700" type="button" onClick={() => onSingleDelete(factory)}>Delete Factory</button> : null}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BulkDeleteModal({ preview, settings, onClose, onDeleted }: { preview: BulkDeletePreview; settings: SuperAdminSettings; onClose: () => void; onDeleted: (response: BulkDeleteResponse) => Promise<void> }) {
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState("");
  const [isDeleting, setDeleting] = useState(false);
  const confirmationPhrase = "DELETE SELECTED FACTORIES";
  const canDelete = settings.bulk_delete_enabled && confirmation === confirmationPhrase;
  async function deleteFactories() {
    if (!canDelete) return;
    setError("");
    setDeleting(true);
    try {
      const response = await superAdminApi.delete<BulkDeleteResponse>("/api/super-admin/factories/bulk-delete", {
        data: {
          factory_ids: preview.factories.map((factory) => factory.factory_id),
          confirmation,
        },
      });
      await onDeleted(response.data);
    } catch (caught) {
      setError(getAdminApiError(caught, "Bulk delete failed"));
    } finally {
      setDeleting(false);
    }
  }
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4">
      <div data-testid="bulk-delete-preview-modal" className="max-h-[90vh] w-full max-w-4xl overflow-y-auto rounded-lg bg-white p-5 shadow-xl">
        <h3 className="text-lg font-black text-red-800">Delete {preview.factories.length} Selected {preview.factories.length === 1 ? "Factory" : "Factories"}</h3>
        <p className="mt-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm font-bold text-red-800">This will permanently delete selected factories and all related data.</p>
        {!settings.bulk_delete_enabled ? <p className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-800">Bulk delete is disabled by server configuration.</p> : null}
        {error ? <p data-testid="bulk-delete-error" className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-700">{error}</p> : null}
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full divide-y divide-zinc-200 text-sm">
            <thead className="bg-zinc-50">
              <tr>{["Factory", "Owner", "Owner Action", "Email", "Phone", "Records"].map((head) => <th key={head} className="px-3 py-2 text-left font-bold text-zinc-600">{head}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {preview.factories.map((factory) => (
                <tr key={factory.factory_id}>
                  <td className="px-3 py-2 font-semibold">{factory.factory_name}<div className="text-xs text-zinc-500">#{factory.factory_id}</div></td>
                  <td className="px-3 py-2">{factory.owner_name || "-"}</td>
                  <td className="px-3 py-2">{formatOwnerAction(factory.owner_action || factory.owner?.action)}</td>
                  <td className="px-3 py-2">{factory.owner_email || "-"}</td>
                  <td className="px-3 py-2">{factory.owner_phone || "-"}</td>
                  <td className="px-3 py-2">{Object.values(factory.record_counts).reduce((sum, value) => sum + Number(value || 0), 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-4 grid gap-2 rounded-md border border-zinc-200 bg-zinc-50 p-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
          {Object.entries(preview.total_counts).map(([key, value]) => <div key={key}><span className="font-bold">{key.replace(/_/g, " ")}:</span> {String(value)}</div>)}
        </div>
        <label className="mt-4 block text-sm font-semibold">
          Type {confirmationPhrase} to confirm
          <input
            data-testid="bulk-delete-confirmation-input"
            className="mt-1 h-10 w-full rounded-md border border-zinc-300 px-3 outline-none focus:ring-2 focus:ring-red-600"
            value={confirmation}
            onChange={(event) => setConfirmation(event.target.value)}
          />
        </label>
        <div className="mt-5 flex justify-end gap-2">
          <button className="rounded-md border px-4 py-2 text-sm font-bold" type="button" onClick={onClose} disabled={isDeleting}>Cancel</button>
          <button
            data-testid="bulk-delete-final-button"
            className="rounded-md bg-red-700 px-4 py-2 text-sm font-bold text-white disabled:bg-zinc-300"
            type="button"
            disabled={!canDelete || isDeleting}
            onClick={deleteFactories}
          >
            {isDeleting ? "Deleting..." : "Permanently Delete"}
          </button>
        </div>
      </div>
    </div>
  );
}

function SingleDeleteModal({ preview, settings, onClose, onDeleted }: { preview: BulkDeleteFactoryPreview; settings: SuperAdminSettings; onClose: () => void; onDeleted: (response: SingleDeleteResponse) => Promise<void> }) {
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState("");
  const [isDeleting, setDeleting] = useState(false);
  const confirmationPhrase = "DELETE FACTORY";
  const canDelete = Boolean(settings.factory_delete_enabled) && confirmation === confirmationPhrase;
  async function deleteFactory() {
    if (!canDelete) return;
    setError("");
    setDeleting(true);
    try {
      const response = await superAdminApi.delete<SingleDeleteResponse>(`/api/super-admin/factories/${preview.factory_id}`, {
        data: { confirmation },
      });
      await onDeleted(response.data);
    } catch (caught) {
      setError(getAdminApiError(caught, "Factory delete failed"));
    } finally {
      setDeleting(false);
    }
  }
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4">
      <div className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-lg bg-white p-5 shadow-xl">
        <h3 className="text-lg font-black text-red-800">Delete Factory: {preview.factory_name}</h3>
        <p className="mt-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm font-bold text-red-800">This will permanently delete this factory and all associated owner, workers, and related data.</p>
        {!settings.factory_delete_enabled ? <p className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-800">Factory delete is disabled by server configuration.</p> : null}
        {error ? <p data-testid="bulk-delete-error" className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-700">{error}</p> : null}
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <Metric label="Owner action" value={formatOwnerAction(preview.owner_action || preview.owner?.action)} />
          <Metric label="Workers/staff" value={String((preview.record_counts.workers || 0) + (preview.record_counts.staff || 0))} />
        </div>
        {preview.warnings?.length ? <ul className="mt-4 list-disc rounded-md border border-amber-200 bg-amber-50 p-4 pl-8 text-sm font-semibold text-amber-900">{preview.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : null}
        <div className="mt-4 grid gap-2 rounded-md border border-zinc-200 bg-zinc-50 p-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
          {Object.entries(preview.record_counts).map(([key, value]) => <div key={key}><span className="font-bold">{key.replace(/_/g, " ")}:</span> {String(value)}</div>)}
        </div>
        <label className="mt-4 block text-sm font-semibold">
          Type {confirmationPhrase} to confirm
          <input className="mt-1 h-10 w-full rounded-md border border-zinc-300 px-3 outline-none focus:ring-2 focus:ring-red-600" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} />
        </label>
        <div className="mt-5 flex justify-end gap-2">
          <button className="rounded-md border px-4 py-2 text-sm font-bold" type="button" onClick={onClose} disabled={isDeleting}>Cancel</button>
          <button className="rounded-md bg-red-700 px-4 py-2 text-sm font-bold text-white disabled:bg-zinc-300" type="button" disabled={!canDelete || isDeleting} onClick={deleteFactory}>
            {isDeleting ? "Deleting..." : "Permanently Delete Factory"}
          </button>
        </div>
      </div>
    </div>
  );
}

function formatOwnerAction(value?: string) {
  if (value === "delete_owner_because_only_factory") return "Owner will be deleted";
  if (value === "kept_multiple_factories") return "Owner kept";
  if (value === "none") return "No linked owner";
  return value || "-";
}

export function SuperAdminFactoryDetailPage() {
  const { factoryId } = useParams();
  const { data, error, isLoading } = useAdminData<FactoryRecord>(`/api/super-admin/factories/${factoryId}`, {} as FactoryRecord);
  const counts = data.counts || {};
  return (
    <div className="space-y-5">
      <Panel title={`Factory Detail #${factoryId}`}>
        <ErrorNote message={error} />
        {isLoading ? <p>Loading factory...</p> : (
          <div className="grid gap-3 md:grid-cols-3">
            <Metric label="Factory" value={data.factory_name || data.name || "-"} />
            <Metric label="Owner" value={data.owner?.full_name || data.owner?.username || "-"} />
            <Metric label="Subscription" value={`${data.plan_name || "-"} / ${data.subscription_status || "-"}`} />
          </div>
        )}
      </Panel>
      <Panel title="Factory Data Summary">
        <div className="grid gap-3 md:grid-cols-3">
          {Object.entries(counts).map(([key, value]) => <Metric key={key} label={key.replace(/_/g, " ")} value={String(value)} />)}
        </div>
      </Panel>
    </div>
  );
}

export function SuperAdminSubscriptionsPage() {
  const { data, error, isLoading, reload } = useAdminData<FactoryRecord[]>("/api/super-admin/subscriptions", []);
  const [editing, setEditing] = useState<FactoryRecord | null>(null);
  return (
    <Panel title="Manual Subscription Management">
      <ErrorNote message={error} />
      {isLoading ? <p>Loading subscriptions...</p> : <FactoryTable factories={data} />}
      <div className="mt-4 grid gap-2 md:grid-cols-3">
        {data.slice(0, 60).map((factory) => <button key={factory.id} className="rounded-md border border-zinc-200 p-3 text-left text-sm hover:bg-zinc-50" type="button" onClick={() => setEditing(factory)}>{factory.factory_name || factory.name}<span className="block text-xs text-zinc-500">{factory.plan_name} / {factory.subscription_status}</span></button>)}
      </div>
      {editing ? <SubscriptionModal factory={editing} onClose={() => setEditing(null)} onSaved={reload} /> : null}
    </Panel>
  );
}

function SubscriptionModal({ factory, onClose, onSaved }: { factory: FactoryRecord; onClose: () => void; onSaved: () => Promise<void> }) {
  const [plan, setPlan] = useState(factory.plan_name || "premium");
  const [status, setStatus] = useState(factory.subscription_status || "active");
  const [payment, setPayment] = useState(factory.payment_status || "paid");
  const [billingCycle, setBillingCycle] = useState(factory.billing_cycle || "monthly");
  const [endDate, setEndDate] = useState((factory.subscription_end_date || factory.plan_expires_at || "").slice(0, 10));
  const [usageLimit, setUsageLimit] = useState(factory.usage_limit ? String(factory.usage_limit) : "");
  const [tokenLimit, setTokenLimit] = useState(factory.token_limit ? String(factory.token_limit) : "");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [isSaving, setSaving] = useState(false);

  async function save() {
    if (!window.confirm("Save manual subscription change?")) return;
    setError("");
    setSaving(true);
    try {
      await superAdminApi.patch(`/api/super-admin/subscriptions/${factory.id}`, {
        active_plan: plan,
        plan_name: plan,
        subscription_status: status,
        payment_status: payment,
        billing_cycle: billingCycle === "none" ? null : billingCycle,
        subscription_end_date: endDate ? new Date(endDate).toISOString() : undefined,
        plan_expires_at: endDate ? new Date(endDate).toISOString() : undefined,
        usage_limit: usageLimit ? Number(usageLimit) : null,
        token_limit: tokenLimit ? Number(tokenLimit) : null,
        admin_note: note || factory.admin_note,
        note,
      });
      await onSaved();
      onClose();
    } catch (caught) {
      setError(getAdminApiError(caught, "Subscription update failed"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4">
      <div className="w-full max-w-lg rounded-lg bg-white p-5 shadow-xl">
        <h3 className="text-lg font-black">Edit Subscription: {factory.factory_name || factory.name}</h3>
        <ErrorNote message={error} />
        <div className="mt-4 grid gap-3">
          <SelectInput label="Plan" value={plan} onChange={setPlan} options={["free", "trial", "basic", "pro", "enterprise", "custom"]} />
          <SelectInput label="Subscription Status" value={status} onChange={setStatus} options={["active", "inactive", "trial_active", "trial", "expired", "suspended"]} />
          <SelectInput label="Payment Status" value={payment} onChange={setPayment} options={["free", "paid", "pending", "overdue", "failed"]} />
          <SelectInput label="Billing Cycle" value={billingCycle} onChange={setBillingCycle} options={["none", "monthly", "yearly", "custom"]} />
          <Input label="Expiry Date" value={endDate} onChange={setEndDate} type="date" />
          <Input label="Usage Limit" value={usageLimit} onChange={setUsageLimit} type="number" />
          <Input label="Token Limit" value={tokenLimit} onChange={setTokenLimit} type="number" />
          <Input label="Admin Note" value={note} onChange={setNote} />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <ActivateSubscriptionButton factoryId={factory.id} />
          <button className="rounded-md border px-4 py-2 text-sm font-bold" type="button" onClick={onClose} disabled={isSaving}>Cancel</button>
          <button className="rounded-md bg-[#6D28D9] px-4 py-2 text-sm font-bold text-white disabled:bg-zinc-300" type="button" onClick={save} disabled={isSaving}>
            {isSaving ? "Saving..." : "Save Change"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Input({ label, value, onChange, type = "text" }: { label: string; value: string; onChange: (value: string) => void; type?: string }) {
  return <label className="text-sm font-semibold">{label}<input className="mt-1 h-10 w-full rounded-md border border-zinc-300 px-3 outline-none focus:ring-2 focus:ring-indigo-600" type={type} value={value} onChange={(event) => onChange(event.target.value)} /></label>;
}

function SelectInput({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: string[] }) {
  return (
    <label className="text-sm font-semibold">
      {label}
      <select className="mt-1 h-10 w-full rounded-md border border-zinc-300 px-3 outline-none focus:ring-2 focus:ring-indigo-600" value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => <option key={option} value={option}>{option}</option>)}
      </select>
    </label>
  );
}

export function SuperAdminUsagePage() {
  const summary = useAdminData<UsageSummary>("/api/super-admin/usage/summary", { total_app_events: 0, total_token_usage: 0, monthly_token_usage: 0, last_active_at: null });
  const appLogs = useAdminData<Array<Record<string, unknown>>>("/api/super-admin/usage/app-logs", []);
  const tokenLogs = useAdminData<Array<Record<string, unknown>>>("/api/super-admin/usage/token-logs", []);
  return (
    <div className="space-y-5">
      <Panel title="Usage and Token Tracking">
        <ErrorNote message={summary.error} />
        {summary.isLoading ? <p>Loading usage...</p> : (
          <div className="grid gap-3 md:grid-cols-4">
            <Metric label="App usage events" value={String(summary.data.total_app_events)} />
            <Metric label="Total tokens" value={String(summary.data.total_token_usage)} />
            <Metric label="This month tokens" value={String(summary.data.monthly_token_usage)} />
            <Metric label="Last active" value={formatDate(summary.data.last_active_at)} />
          </div>
        )}
      </Panel>
      <Panel title="App Usage Logs">
        <ErrorNote message={appLogs.error} />
        {appLogs.isLoading ? <p>Loading app logs...</p> : <SimpleTable rows={appLogs.data} />}
      </Panel>
      <Panel title="Token Usage Logs">
        <ErrorNote message={tokenLogs.error} />
        {tokenLogs.isLoading ? <p>Loading token logs...</p> : <SimpleTable rows={tokenLogs.data} />}
      </Panel>
    </div>
  );
}

export function SuperAdminPaymentsPage() {
  const { data, error, isLoading } = useAdminData<Array<Record<string, unknown>>>("/api/super-admin/payments", []);
  return (
    <Panel title="Payment Tracking">
      <ErrorNote message={error} />
      {isLoading ? <p>Loading payments...</p> : <SimpleTable rows={data} />}
    </Panel>
  );
}

export function SuperAdminAuditLogsPage() {
  const { data, error, isLoading } = useAdminData<AuditLog[]>("/api/super-admin/audit-logs", []);
  return (
    <Panel title="Audit Logs">
      <ErrorNote message={error} />
      {isLoading ? <p>Loading audit logs...</p> : <SimpleTable rows={data as unknown as Array<Record<string, unknown>>} />}
    </Panel>
  );
}

function formatAdminDate(value?: string | null) {
  if (!value) return "Not available";
  return new Date(value).toLocaleString("en-IN");
}

function BriefingStatus({ status }: { status: BriefingLog["status"] }) {
  const classes = {
    generated: "bg-blue-100 text-blue-800",
    sent: "bg-emerald-100 text-emerald-800",
    failed: "bg-red-100 text-red-800",
    skipped: "bg-amber-100 text-amber-800",
  };
  return <span className={`rounded-full px-2 py-1 text-xs font-bold capitalize ${classes[status]}`}>{status}</span>;
}

export function SuperAdminBriefingsPage() {
  const overview = useAdminData<BriefingOverview>("/api/admin/briefings/overview", {
    total_factories: 0,
    telegram_connected_factories: 0,
    active_briefing_factories: 0,
    delivery_success_rate: 0,
    delivery_failure_rate: 0,
    last_successful_delivery: null,
    last_failed_delivery: null,
    metrics: {
      today_sent: 0,
      today_failed: 0,
      seven_day_sent: 0,
      seven_day_failed: 0,
      thirty_day_sent: 0,
      thirty_day_failed: 0,
      delivery_success_rate: 0,
    },
  });
  const [factoryId, setFactoryId] = useState("");
  const [briefingDate, setBriefingDate] = useState("");
  const [status, setStatus] = useState("");
  const [logPage, setLogPage] = useState(1);
  const [healthPage, setHealthPage] = useState(1);
  const [spikePage, setSpikePage] = useState(1);
  const [digestPage, setDigestPage] = useState(1);
  const logQuery = new URLSearchParams({
    page: String(logPage),
    page_size: "25",
    ...(factoryId ? { factory_id: factoryId } : {}),
    ...(briefingDate ? { briefing_date: briefingDate } : {}),
    ...(status ? { status } : {}),
  });
  const logs = useAdminData<PageResult<BriefingLog>>(`/api/admin/briefings/logs?${logQuery}`, {
    items: [], page: 1, page_size: 25, total: 0, pages: 0,
  });
  const health = useAdminData<PageResult<BriefingFactoryHealth>>(
    `/api/admin/briefings/factory-health?page=${healthPage}&page_size=25`,
    { items: [], page: 1, page_size: 25, total: 0, pages: 0 },
  );
  const spikes = useAdminData<PageResult<CostSpikeEvent>>(
    `/api/admin/briefings/cost-spikes?page=${spikePage}&page_size=25`,
    { items: [], page: 1, page_size: 25, total: 0, pages: 0 },
  );
  const digests = useAdminData<PageResult<WeeklyDigestLog>>(
    `/api/admin/weekly-digest?page=${digestPage}&page_size=25`,
    { items: [], page: 1, page_size: 25, total: 0, pages: 0 },
  );
  const cards = [
    ["Total Factories", overview.data.total_factories],
    ["Telegram Connected", overview.data.telegram_connected_factories],
    ["Active Briefing Factories", overview.data.active_briefing_factories],
    ["Success Rate", `${overview.data.delivery_success_rate}%`],
    ["Failure Rate", `${overview.data.delivery_failure_rate}%`],
    ["Today Sent / Failed", `${overview.data.metrics.today_sent} / ${overview.data.metrics.today_failed}`],
    ["7 Day Sent / Failed", `${overview.data.metrics.seven_day_sent} / ${overview.data.metrics.seven_day_failed}`],
    ["30 Day Sent / Failed", `${overview.data.metrics.thirty_day_sent} / ${overview.data.metrics.thirty_day_failed}`],
  ];

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-2xl font-black">Briefing Delivery Observability</h2>
        <p className="text-sm text-zinc-600">Cross-factory delivery health and failure investigation.</p>
      </div>
      <ErrorNote message={overview.error || logs.error || health.error || spikes.error || digests.error} />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map(([label, value]) => (
          <div key={label} className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
            <p className="text-xs font-bold uppercase tracking-wide text-zinc-500">{label}</p>
            <p className="mt-2 text-2xl font-black">{value}</p>
          </div>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Last Successful Delivery">
          <p className="font-bold">{overview.data.last_successful_delivery?.factory_name || "Not available"}</p>
          <p className="text-sm text-zinc-600">{formatAdminDate(overview.data.last_successful_delivery?.at)}</p>
        </Panel>
        <Panel title="Last Failed Delivery">
          <p className="font-bold">{overview.data.last_failed_delivery?.factory_name || "Not available"}</p>
          <p className="text-sm text-zinc-600">{formatAdminDate(overview.data.last_failed_delivery?.at)}</p>
        </Panel>
      </div>
      <Panel title="Briefing Delivery Logs">
        <div className="mb-4 grid gap-3 md:grid-cols-3">
          <select className="h-10 rounded-md border border-zinc-300 px-3 text-sm" value={factoryId} onChange={(event) => { setFactoryId(event.target.value); setLogPage(1); }}>
            <option value="">All factories</option>
            {health.data.items.map((factory) => <option key={factory.factory_id} value={factory.factory_id}>{factory.factory_name}</option>)}
          </select>
          <input className="h-10 rounded-md border border-zinc-300 px-3 text-sm" type="date" value={briefingDate} onChange={(event) => { setBriefingDate(event.target.value); setLogPage(1); }} />
          <select className="h-10 rounded-md border border-zinc-300 px-3 text-sm" value={status} onChange={(event) => { setStatus(event.target.value); setLogPage(1); }}>
            <option value="">All statuses</option>
            <option value="generated">Generated</option>
            <option value="sent">Sent</option>
            <option value="failed">Failed</option>
            <option value="skipped">Skipped</option>
          </select>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-zinc-200 text-xs uppercase text-zinc-500"><tr>
              {["Factory", "Briefing Date", "Generated At", "Sent At", "Status", "Channel", "Error Message", "Retries"].map((heading) => <th key={heading} className="px-3 py-3">{heading}</th>)}
            </tr></thead>
            <tbody>{logs.data.items.map((log) => <tr key={log.id} className="border-b border-zinc-100 align-top">
              <td className="px-3 py-3 font-semibold">{log.factory_name}</td>
              <td className="px-3 py-3">{log.briefing_date}</td>
              <td className="px-3 py-3 whitespace-nowrap">{formatAdminDate(log.generated_at)}</td>
              <td className="px-3 py-3 whitespace-nowrap">{formatAdminDate(log.sent_at)}</td>
              <td className="px-3 py-3"><BriefingStatus status={log.status} /></td>
              <td className="px-3 py-3 capitalize">{log.channel}</td>
              <td className="max-w-xs px-3 py-3 text-red-700">{log.error_message || "-"}</td>
              <td className="px-3 py-3">{log.retry_count}</td>
            </tr>)}</tbody>
          </table>
          {!logs.isLoading && logs.data.items.length === 0 ? <EmptyState>No briefing logs match these filters.</EmptyState> : null}
        </div>
        <div className="mt-4 flex items-center justify-between text-sm">
          <span>{logs.data.total} records</span>
          <div className="flex gap-2">
            <button className="rounded border px-3 py-1 disabled:opacity-40" disabled={logPage <= 1} onClick={() => setLogPage((page) => page - 1)}>Previous</button>
            <button className="rounded border px-3 py-1 disabled:opacity-40" disabled={logPage >= logs.data.pages} onClick={() => setLogPage((page) => page + 1)}>Next</button>
          </div>
        </div>
      </Panel>
      <Panel title="Factory Briefing Health">
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-zinc-200 text-xs uppercase text-zinc-500"><tr>
              {["Factory", "Telegram", "Last Sent", "Last Failed", "Delivery %", "7 Day %", "30 Day %"].map((heading) => <th key={heading} className="px-3 py-3">{heading}</th>)}
            </tr></thead>
            <tbody>{health.data.items.map((factory) => <tr key={factory.factory_id} className="border-b border-zinc-100">
              <td className="px-3 py-3 font-semibold">{factory.factory_name}</td>
              <td className="px-3 py-3 font-bold">{factory.telegram_connected ? "YES" : "NO"}</td>
              <td className="px-3 py-3 whitespace-nowrap">{formatAdminDate(factory.last_briefing_sent)}</td>
              <td className="px-3 py-3 whitespace-nowrap">{formatAdminDate(factory.last_briefing_failed)}</td>
              <td className="px-3 py-3">{factory.delivery_percent}%</td>
              <td className="px-3 py-3">{factory.seven_day_success_percent}%</td>
              <td className="px-3 py-3">{factory.thirty_day_success_percent}%</td>
            </tr>)}</tbody>
          </table>
        </div>
        <div className="mt-4 flex items-center justify-between text-sm">
          <span>{health.data.total} factories</span>
          <div className="flex gap-2">
            <button className="rounded border px-3 py-1 disabled:opacity-40" disabled={healthPage <= 1} onClick={() => setHealthPage((page) => page - 1)}>Previous</button>
            <button className="rounded border px-3 py-1 disabled:opacity-40" disabled={healthPage >= health.data.pages} onClick={() => setHealthPage((page) => page + 1)}>Next</button>
          </div>
        </div>
      </Panel>
      <Panel title="Cost Spike Events">
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-zinc-200 text-xs uppercase text-zinc-500"><tr>
              {["Factory", "Date", "Variance", "Primary Driver", "Status"].map((heading) => <th key={heading} className="px-3 py-3">{heading}</th>)}
            </tr></thead>
            <tbody>{spikes.data.items.map((event) => <tr key={event.id} className="border-b border-zinc-100">
              <td className="px-3 py-3 font-semibold">{event.factory_name}</td>
              <td className="px-3 py-3">{event.snapshot_date}</td>
              <td className="px-3 py-3 font-semibold">{event.variance_percent == null ? "Not available" : `${toNumber(event.variance_percent) > 0 ? "+" : ""}${toNumber(event.variance_percent).toFixed(1)}%`}</td>
              <td className="px-3 py-3">{event.primary_driver || "Not available"}</td>
              <td className="px-3 py-3"><BriefingStatus status={event.status} /></td>
            </tr>)}</tbody>
          </table>
          {!spikes.isLoading && spikes.data.items.length === 0 ? <EmptyState>No cost spike events recorded.</EmptyState> : null}
        </div>
        <div className="mt-4 flex items-center justify-between text-sm">
          <span>{spikes.data.total} events</span>
          <div className="flex gap-2">
            <button className="rounded border px-3 py-1 disabled:opacity-40" disabled={spikePage <= 1} onClick={() => setSpikePage((page) => page - 1)}>Previous</button>
            <button className="rounded border px-3 py-1 disabled:opacity-40" disabled={spikePage >= spikes.data.pages} onClick={() => setSpikePage((page) => page + 1)}>Next</button>
          </div>
        </div>
      </Panel>
      <Panel title="Weekly Digest Log">
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-zinc-200 text-xs uppercase text-zinc-500"><tr>
              {["Factory", "Week", "Status", "Sent Time", "Message Sent", "Error"].map((heading) => <th key={heading} className="px-3 py-3">{heading}</th>)}
            </tr></thead>
            <tbody>{digests.data.items.map((log) => <tr key={log.id} className="border-b border-zinc-100">
              <td className="px-3 py-3 font-semibold">{log.factory_name}</td>
              <td className="px-3 py-3">{log.week_start} to {log.week_end}</td>
              <td className="px-3 py-3 font-semibold uppercase">{log.status}</td>
              <td className="px-3 py-3 whitespace-nowrap">{formatAdminDate(log.sent_at)}</td>
              <td className="px-3 py-3">{log.message_sent ? "YES" : "NO"}</td>
              <td className="max-w-xs px-3 py-3 text-red-700">{log.error_message || "-"}</td>
            </tr>)}</tbody>
          </table>
          {!digests.isLoading && digests.data.items.length === 0 ? <EmptyState>No weekly digest logs recorded.</EmptyState> : null}
        </div>
        <div className="mt-4 flex items-center justify-between text-sm">
          <span>{digests.data.total} records</span>
          <div className="flex gap-2">
            <button className="rounded border px-3 py-1 disabled:opacity-40" disabled={digestPage <= 1} onClick={() => setDigestPage((page) => page - 1)}>Previous</button>
            <button className="rounded border px-3 py-1 disabled:opacity-40" disabled={digestPage >= digests.data.pages} onClick={() => setDigestPage((page) => page + 1)}>Next</button>
          </div>
        </div>
      </Panel>
    </div>
  );
}

function SimpleTable({ rows }: { rows: Array<Record<string, unknown>> }) {
  const columns = useMemo(() => Array.from(new Set(rows.flatMap((row) => Object.keys(row)))).slice(0, 10), [rows]);
  if (rows.length === 0) return <EmptyState>No rows found.</EmptyState>;
  return (
    <div className="w-full overflow-x-auto block">
      <table className="min-w-full divide-y divide-zinc-200 text-sm">
        <thead className="bg-zinc-50"><tr>{columns.map((column) => <th key={column} className="px-3 py-2 text-left font-bold text-zinc-600">{column}</th>)}</tr></thead>
        <tbody className="divide-y divide-zinc-100">{rows.map((row, index) => <tr key={index}>{columns.map((column) => <td key={column} className="px-3 py-2">{String(row[column] ?? "-")}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  return new Date(value).toLocaleDateString("en-IN");
}

export function SuperAdminNotConfigured() {
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
      <AlertTriangle className="mr-2 inline h-4 w-4" />
      Super admin environment variables must be configured on the backend.
    </div>
  );
}
