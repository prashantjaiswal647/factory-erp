import { AlertTriangle, CheckCircle2, ExternalLink, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { getAlerts, resolveAlert } from "../lib/api";
import type { UnifiedAlert } from "../lib/api";

const severityStyles = {
  CRITICAL: "border-red-200 bg-red-50 text-red-800",
  WARNING: "border-amber-200 bg-amber-50 text-amber-800",
  INFO: "border-sky-200 bg-sky-50 text-sky-800"
};

export default function AlertsPage() {
  const [items, setItems] = useState<UnifiedAlert[]>([]);
  const [severity, setSeverity] = useState("");
  const [module, setModule] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const data = await getAlerts({
        severity: severity || undefined,
        module: module || undefined,
        status: "OPEN"
      });
      setItems(data.items);
    } catch {
      setError("Alerts could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [severity, module]);

  const modules = useMemo(
    () => Array.from(new Set(items.map((item) => item.source_module))).sort(),
    [items]
  );

  async function markResolved(id: number) {
    await resolveAlert(id);
    setItems((current) => current.filter((item) => item.id !== id));
  }

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-brand-700">Unified Alert Center</p>
          <h1 className="text-2xl font-bold text-zinc-950">Factory alerts</h1>
        </div>
        <button className="inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-semibold" onClick={load}>
          <RefreshCw className="h-4 w-4" /> Refresh
        </button>
      </header>

      <section className="flex flex-wrap gap-2 rounded-xl border bg-white p-3">
        <select className="rounded-lg border px-3 py-2 text-sm" value={severity} onChange={(event) => setSeverity(event.target.value)}>
          <option value="">All severities</option>
          <option value="CRITICAL">Critical</option>
          <option value="WARNING">Warning</option>
          <option value="INFO">Info</option>
        </select>
        <select className="rounded-lg border px-3 py-2 text-sm" value={module} onChange={(event) => setModule(event.target.value)}>
          <option value="">All modules</option>
          {modules.map((value) => <option key={value} value={value}>{value.replace(/_/g, " ")}</option>)}
        </select>
      </section>

      {error ? <p className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p> : null}
      {loading ? <p className="text-sm text-zinc-500">Loading alerts...</p> : null}
      {!loading && items.length === 0 ? (
        <div className="rounded-xl border bg-white p-8 text-center text-sm text-zinc-500">No open alerts match these filters.</div>
      ) : null}

      <div className="space-y-3">
        {items.map((alert) => (
          <article key={alert.id} className="rounded-xl border bg-white p-4 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex min-w-0 gap-3">
                <AlertTriangle className="mt-1 h-5 w-5 shrink-0 text-amber-600" />
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="font-bold text-zinc-950">{alert.title}</h2>
                    <span className={`rounded-full border px-2 py-0.5 text-xs font-bold ${severityStyles[alert.severity]}`}>
                      {alert.severity}
                    </span>
                    <span className="text-xs uppercase text-zinc-500">{alert.source_module.replace(/_/g, " ")}</span>
                  </div>
                  <p className="mt-1 text-sm text-zinc-700">{alert.message}</p>
                  {alert.suggested_action ? <p className="mt-2 text-sm font-medium text-zinc-900">Action: {alert.suggested_action}</p> : null}
                </div>
              </div>
              <div className="flex shrink-0 gap-2">
                {alert.related_route ? (
                  <Link className="inline-flex items-center gap-1 rounded-lg border px-3 py-2 text-xs font-semibold" to={alert.related_route}>
                    Open <ExternalLink className="h-3.5 w-3.5" />
                  </Link>
                ) : null}
                <button className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-2 text-xs font-semibold text-white" onClick={() => void markResolved(alert.id)}>
                  <CheckCircle2 className="h-3.5 w-3.5" /> Resolve
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
