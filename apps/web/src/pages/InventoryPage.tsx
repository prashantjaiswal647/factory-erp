import axios from "axios";
import { Camera, ChevronDown, Download, Edit3, FileSpreadsheet, Loader2, PackagePlus, RefreshCw, Search, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { isOwnerLevelRole, useAuth } from "../context/AuthContext";
import { API_BASE_URL, deleteOnboardingItem, exportFinishedGoodsSnapshot, getInventory } from "../lib/api";
import type { LiveStockRow } from "../lib/api";

type InventoryFilter = "all" | "low" | "critical" | "raw" | "finished" | "packaging";
type StockStatus = "In Stock" | "Low Stock" | "Out of Stock";
type InventoryBucket = NonNullable<LiveStockRow["bucket"]>;
type GroupKey = "critical_low" | InventoryBucket;
type SortKey = "item" | "size" | "stock" | "status";
type SortState = { key: SortKey; direction: "asc" | "desc" } | null;

type InventoryDisplayRow = {
  key: string;
  item: string;
  size: string;
  quantity: number;
  unit: string;
  status: StockStatus;
  source: LiveStockRow;
};

type InventoryGroup = {
  key: GroupKey;
  title: string;
  rows: InventoryDisplayRow[];
};

const filters: Array<{ key: InventoryFilter; label: string }> = [
  { key: "all", label: "All" },
  { key: "low", label: "Low Stock" },
  { key: "critical", label: "Critical" },
  { key: "raw", label: "Raw Materials" },
  { key: "finished", label: "Finished" }
];

const defaultCollapsed: Record<GroupKey, boolean> = {
  critical_low: false,
  cup_blanks: false,
  finished_goods: false,
  bottom_reels: true,
  boxes: true,
  polybags_packing: true,
  raw_other: true,
  needs_mapping_review: false
};

export default function InventoryPage() {
  const { user } = useAuth();
  const canDelete = isOwnerLevelRole(user?.role);
  const [rows, setRows] = useState<LiveStockRow[]>([]);
  const [activeFilter, setActiveFilter] = useState<InventoryFilter>("all");
  const [collapsed, setCollapsed] = useState<Record<GroupKey, boolean>>(defaultCollapsed);
  const [sortByGroup, setSortByGroup] = useState<Partial<Record<GroupKey, SortState>>>({});
  const [searchInput, setSearchInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedMobile, setExpandedMobile] = useState<Record<string, boolean>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [uploadingId, setUploadingId] = useState<number | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState("");

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => setSearchQuery(searchInput.trim().toLowerCase()), 150);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  async function load() {
    setIsLoading(true);
    setError("");
    try {
      const response = await getInventory();
      setRows(Array.isArray(response.data) ? response.data : []);
      setLastRefreshed(new Date());
    } catch (caught) {
      const message = axios.isAxiosError(caught) ? caught.response?.data?.detail || caught.message : "Inventory load failed";
      setError(String(message));
    } finally {
      setIsLoading(false);
    }
  }

  async function handleImageUpload(productId: number, file: File) {
    const formData = new FormData();
    formData.append("file", file);
    setUploadingId(productId);
    try {
      const token = localStorage.getItem("token") || localStorage.getItem("ai_erp_token");
      await axios.post(`${API_BASE_URL}/api/inventory/final-stock/${productId}/image`, formData, {
        headers: { "Content-Type": "multipart/form-data", Authorization: `Bearer ${token}` }
      });
      await load();
    } catch (caught) {
      const message = axios.isAxiosError(caught) ? caught.response?.data?.detail || caught.message : "Failed to upload image";
      window.alert(String(message));
    } finally {
      setUploadingId(null);
    }
  }

  async function handleExportSnapshot(format: "xlsx" | "csv" = "xlsx") {
    setIsExporting(true);
    setExportError("");
    try {
      const response = await exportFinishedGoodsSnapshot(undefined, format);
      // axios response is wrapped: response.data is the blob
      const blob = response.data instanceof Blob
        ? response.data
        : new Blob([response.data], {
            type: format === "csv"
              ? "text/csv; charset=utf-8"
              : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      const ext = format === "csv" ? "csv" : "xlsx";
      const dateStr = new Date().toISOString().slice(0, 10);
      link.href = url;
      link.setAttribute("download", `finished_goods_snapshot_${dateStr}.${ext}`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (caught) {
      const message = axios.isAxiosError(caught)
        ? caught.response?.data?.detail || caught.message
        : "Failed to download snapshot";
      setExportError(String(message));
    } finally {
      setIsExporting(false);
    }
  }

  async function handleDelete(row: InventoryDisplayRow) {
    if (!canDelete) {
      window.alert("Access Denied: Only the Factory Owner is authorized to delete entries.");
      return;
    }
    if (!window.confirm("Are you sure you want to remove this entry?")) return;
    try {
      const { id, stock_type: stockType } = row.source;
      let actualId: number | string = id;
      let actualType = String(stockType);
      if (typeof id === "string") {
        const mappings = [
          ["blank-", "blankstock"],
          ["bottom-", "bottomstock"],
          ["box-", "boxstock"],
          ["plastic-", "plasticstock"],
          ["polybag-", "polybagstock"],
          ["final-", "final"]
        ] as const;
        const mapping = mappings.find(([prefix]) => id.startsWith(prefix));
        if (mapping) {
          actualId = id.replace(mapping[0], "");
          actualType = mapping[1];
        }
      } else if (stockType === "Carton Box" || stockType === "Box") {
        actualType = "boxstock";
      }
      await deleteOnboardingItem(Number(actualId), actualType);
      await load();
    } catch (caught) {
      const message = axios.isAxiosError(caught) ? caught.response?.data?.detail || caught.message : "Failed to delete entry";
      window.alert(String(message));
    }
  }

  const displayRows = useMemo(() => rows.map(toDisplayRow).filter((row) => bucketFor(row.source) !== "polybags_packing"), [rows]);
  const counts = useMemo(() => ({
    total: displayRows.length,
    raw: displayRows.filter((row) => ["cup_blanks", "bottom_reels", "raw_other"].includes(bucketFor(row.source))).length,
    packaging: 0,
    boxes: displayRows.filter((row) => bucketFor(row.source) === "boxes").length,
    other: displayRows.filter((row) => bucketFor(row.source) === "needs_mapping_review").length,
    healthy: displayRows.filter((row) => row.status === "In Stock").length,
    low: displayRows.filter((row) => row.status === "Low Stock").length,
    critical: displayRows.filter((row) => row.status === "Out of Stock").length,
    blanks: displayRows.filter((row) => bucketFor(row.source) === "cup_blanks").length,
    bottoms: displayRows.filter((row) => bucketFor(row.source) === "bottom_reels").length,
    finished: displayRows.filter((row) => bucketFor(row.source) === "finished_goods").length
  }), [displayRows]);
  const groups = useMemo(
    () => buildGroups(displayRows, activeFilter, searchQuery, sortByGroup),
    [displayRows, activeFilter, searchQuery, sortByGroup]
  );
  const visibleCount = groups.reduce((sum, group) => sum + group.rows.length, 0);

  function toggleSort(group: GroupKey, key: SortKey) {
    setSortByGroup((current) => {
      const existing = current[group];
      if (!existing || existing.key !== key) return { ...current, [group]: { key, direction: "asc" } };
      if (existing.direction === "asc") return { ...current, [group]: { key, direction: "desc" } };
      const next = { ...current };
      delete next[group];
      return next;
    });
  }

  return (
    <div className="min-w-0 space-y-4 overflow-x-hidden">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-950">Live Inventory</h1>
          <p className="mt-1 text-sm text-zinc-500">
            {displayRows.length} items · {counts.critical} critical · {counts.low} low
            {lastRefreshed ? ` · refreshed ${relativeTime(lastRefreshed)}` : ""}
          </p>
        </div>
        <div className="flex gap-2">
          <Link className="inline-flex h-9 items-center gap-2 rounded-lg bg-brand-600 px-3 text-sm font-semibold text-white hover:bg-brand-700" to="/onboarding">
            <PackagePlus className="h-4 w-4" /> Add Item
          </Link>
          <div className="relative">
            <button
              aria-haspopup="true"
              className="inline-flex h-9 items-center gap-2 rounded-lg border border-zinc-200 bg-white px-3 text-sm font-semibold text-zinc-700 hover:bg-zinc-50 disabled:bg-zinc-100"
              disabled={isExporting}
              title="Download Finished Goods Snapshot (Excel)"
              type="button"
              onClick={() => handleExportSnapshot("xlsx")}
            >
              {isExporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileSpreadsheet className="h-4 w-4" />}
              Download Snapshot
            </button>
          </div>
          <button className="inline-flex h-9 items-center gap-2 rounded-lg border border-zinc-200 bg-white px-3 text-sm font-semibold text-zinc-700 hover:bg-zinc-50" type="button" onClick={load}>
            <RefreshCw className="h-4 w-4" /> Refresh
          </button>
        </div>
      </header>

      {exportError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-700">{exportError}</div>
      ) : null}

      <section className="grid grid-cols-3 gap-2 lg:grid-cols-8" aria-label="Inventory summary">
        <Kpi label="Total" value={counts.total} />
        <Kpi label="Raw Materials" value={counts.raw} />
        <Kpi label="Finished Goods" value={counts.finished} />
        <Kpi label="Boxes" value={counts.boxes} />
        <Kpi label="Other" value={counts.other} />
        <Kpi label="Healthy" value={counts.healthy} />
        <Kpi label="Low" value={counts.low} tone="amber" />
        <a href="#critical-low-stock"><Kpi label="Critical" value={counts.critical} tone="red" /></a>
      </section>

      <section className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5" aria-label="Risk by category">
        {riskCategories(displayRows).filter((risk) => risk.label !== "Packaging").map((risk) => (
          <div key={risk.label} className="rounded-lg border border-zinc-200 bg-white px-3 py-2">
            <div className="flex items-center justify-between text-xs font-semibold text-zinc-700">
              <span>{risk.label}</span><span>{risk.atRisk}/{risk.total}</span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-zinc-100">
              <div className={`h-full ${risk.atRisk ? "bg-amber-500" : "bg-emerald-500"}`} style={{ width: `${risk.total ? Math.max(8, (risk.atRisk / risk.total) * 100) : 0}%` }} />
            </div>
          </div>
        ))}
      </section>

      <section className="sticky top-[65px] z-[5] rounded-xl border border-zinc-200 bg-white/95 p-3 shadow-sm backdrop-blur">
        <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
          <label className="relative min-w-0 flex-1">
            <span className="sr-only">Search inventory</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
            <input
              className="h-9 w-full rounded-lg border border-zinc-200 bg-white pl-9 pr-3 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
              placeholder="Search item, size, code, or packaging"
              type="search"
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
            />
          </label>
          <div className="flex gap-2 overflow-x-auto">
            {filters.map((filter) => (
              <button
                key={filter.key}
                className={`shrink-0 rounded-full px-3 py-2 text-xs font-semibold ${
                  activeFilter === filter.key ? "bg-zinc-900 text-white" : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200"
                }`}
                type="button"
                onClick={() => setActiveFilter(filter.key)}
              >
                {filter.label}
              </button>
            ))}
          </div>
        </div>
      </section>

      {error ? <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-700">{error}</div> : null}

      {isLoading ? (
        <div className="rounded-lg bg-zinc-50 px-4 py-5 text-sm text-zinc-500">Loading inventory...</div>
      ) : visibleCount === 0 ? (
        <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-8 text-center text-sm text-zinc-500">No inventory results.</div>
      ) : (
        <section className="space-y-3">
          {groups.map((group) => (
            <InventoryGroupSection
              key={group.key}
              group={group}
              collapsed={collapsed[group.key]}
              sort={sortByGroup[group.key] || null}
              uploadingId={uploadingId}
              canDelete={canDelete}
              expandedMobile={expandedMobile}
              onToggle={() => setCollapsed((current) => ({ ...current, [group.key]: !current[group.key] }))}
              onToggleMobile={(key) => setExpandedMobile((current) => ({ ...current, [key]: !current[key] }))}
              onSort={(key) => toggleSort(group.key, key)}
              onDelete={handleDelete}
              onImageUpload={handleImageUpload}
            />
          ))}
        </section>
      )}
    </div>
  );
}

function Kpi({ label, value, tone = "neutral" }: { label: string; value: number; tone?: "neutral" | "amber" | "red" }) {
  const background = tone === "red" ? "bg-red-50" : tone === "amber" ? "bg-amber-50" : "bg-zinc-50";
  return (
    <div className={`rounded-lg px-3 py-3 ${background}`}>
      <p className="text-[11px] font-semibold text-zinc-500">{label}</p>
      <p className="mt-1 text-xl font-bold text-zinc-950">{value}</p>
    </div>
  );
}

function InventoryGroupSection(props: {
  group: InventoryGroup;
  collapsed: boolean;
  sort: SortState;
  uploadingId: number | null;
  canDelete: boolean;
  expandedMobile: Record<string, boolean>;
  onToggle: () => void;
  onToggleMobile: (key: string) => void;
  onSort: (key: SortKey) => void;
  onDelete: (row: InventoryDisplayRow) => void;
  onImageUpload: (productId: number, file: File) => Promise<void>;
}) {
  const { group } = props;
  return (
    <section id={group.key === "critical_low" ? "critical-low-stock" : undefined} className="scroll-mt-24 overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-sm">
      <button className="flex w-full items-center justify-between px-4 py-3 text-left" type="button" onClick={props.onToggle}>
        <span className={`flex items-center gap-2 text-sm font-semibold ${group.key === "critical_low" ? "text-red-700" : "text-zinc-950"}`}>
          {group.key === "critical_low" ? "!" : null} {group.title}
          <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-semibold text-zinc-700">{group.rows.length}</span>
        </span>
        <ChevronDown className={`h-4 w-4 text-zinc-500 transition ${props.collapsed ? "-rotate-90" : ""}`} />
      </button>
      {props.collapsed ? null : group.rows.length === 0 ? (
        <div className="border-t border-zinc-100 bg-zinc-50 px-4 py-4 text-sm text-zinc-500">No items in this group.</div>
      ) : (
        <>
          <div className="hidden overflow-x-auto border-t border-zinc-100 md:block">
            <InventoryTable {...props} />
          </div>
          <div className="divide-y divide-zinc-100 border-t border-zinc-100 md:hidden">
          {group.rows.map((row) => (
              <MobileInventoryRow
                key={row.key}
                row={row}
                expanded={Boolean(props.expandedMobile[row.key])}
                uploadingId={props.uploadingId}
                canDelete={props.canDelete}
                onToggle={() => props.onToggleMobile(row.key)}
                onDelete={props.onDelete}
                onImageUpload={props.onImageUpload}
              />
            ))}
          </div>
        </>
      )}
    </section>
  );
}

function InventoryTable(props: Parameters<typeof InventoryGroupSection>[0]) {
  const { group } = props;
  if (group.key === "finished_goods") {
    return <FinishedGoodsTable {...props} />;
  }
  return (
    <table className="min-w-full text-xs">
      <thead className="bg-zinc-50 text-[11px] uppercase tracking-wider text-zinc-500">
        <tr>
          <SortableTh label="Item" sortKey="item" sort={props.sort} onSort={props.onSort} />
          <Th>Category</Th>
          <SortableTh label="Size" sortKey="size" sort={props.sort} onSort={props.onSort} />
          <SortableTh label="Stock" sortKey="stock" sort={props.sort} onSort={props.onSort} />
          <Th>Suggested Reorder</Th>
          <Th>Details</Th>
          <SortableTh label="Status" sortKey="status" sort={props.sort} onSort={props.onSort} />
          <Th><span className="sr-only">Actions</span></Th>
        </tr>
      </thead>
      <tbody>
        {group.rows.map((row) => (
          <tr key={row.key} className="border-t border-zinc-100">
            <td className={`border-l-[3px] px-3 py-2 font-semibold text-zinc-950 ${statusBar(row.status)}`}>{row.item}</td>
            <td className="whitespace-nowrap px-3 py-2 text-zinc-600">{groupLabel(row.source)}</td>
            <td className="whitespace-nowrap px-3 py-2 text-zinc-700">{row.size}</td>
            <td className="whitespace-nowrap px-3 py-2 font-semibold text-zinc-950">{formatNumber(row.quantity)} {row.unit}</td>
            <td className={`whitespace-nowrap px-3 py-2 font-bold ${reorderTone(row.status)}`} title="Estimated from the current low-stock threshold.">
              {row.status === "In Stock" ? "-" : formatNumber(computeReorder(row.quantity, row.source.stock_type))}
            </td>
            <td className="whitespace-nowrap px-3 py-2 text-zinc-600">{detailSummary(row)}</td>
            <td className="whitespace-nowrap px-3 py-2"><StatusBadge status={row.status} /></td>
            <td className="px-3 py-2"><RowActions {...props} row={row} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function FinishedGoodsTable(props: Parameters<typeof InventoryGroupSection>[0]) {
  return (
    <table className="min-w-full text-xs">
      <thead className="bg-zinc-50 text-[11px] uppercase tracking-wider text-zinc-500">
        <tr>
          <SortableTh label="Size" sortKey="size" sort={props.sort} onSort={props.onSort} />
          <SortableTh label="Item" sortKey="item" sort={props.sort} onSort={props.onSort} />
          <Th>Details</Th>
          <SortableTh label="Stock" sortKey="stock" sort={props.sort} onSort={props.onSort} />
          <SortableTh label="Status" sortKey="status" sort={props.sort} onSort={props.onSort} />
          <Th>Suggested Reorder</Th>
          <Th><span className="sr-only">Actions</span></Th>
        </tr>
      </thead>
      <tbody>
        {props.group.rows.map((row) => (
          <tr key={row.key} className="border-t border-zinc-100 align-top">
            <td className={`whitespace-nowrap border-l-[3px] px-3 py-2 font-bold text-zinc-950 ${statusBar(row.status)}`}>{row.size || "-"}</td>
            <td className="min-w-32 px-3 py-2 font-semibold text-zinc-950">{row.item || "-"}</td>
            <td className="min-w-64 px-3 py-2 text-zinc-600">{finishedGoodsDetails(row)}</td>
            <td className="min-w-36 px-3 py-2 font-semibold text-zinc-950">{finishedGoodsStock(row)}</td>
            <td className="whitespace-nowrap px-3 py-2"><StatusBadge status={row.status} /></td>
            <td className={`whitespace-nowrap px-3 py-2 font-bold ${reorderTone(row.status)}`} title="Estimated from the current low-stock threshold.">
              {row.status === "In Stock" ? "-" : `${formatNumber(computeReorder(row.quantity, row.source.stock_type))} boxes`}
            </td>
            <td className="px-3 py-2"><RowActions {...props} row={row} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function MobileInventoryRow(props: {
  row: InventoryDisplayRow;
  expanded: boolean;
  uploadingId: number | null;
  canDelete: boolean;
  onToggle: () => void;
  onDelete: (row: InventoryDisplayRow) => void;
  onImageUpload: (productId: number, file: File) => Promise<void>;
}) {
  const isFinishedGoods = bucketFor(props.row.source) === "finished_goods";
  return (
    <div className={`border-l-[3px] ${statusBar(props.row.status)}`}>
      <button className="w-full px-3 py-3 text-left" type="button" onClick={props.onToggle}>
        <span className="flex items-start justify-between gap-2">
          <span className="min-w-0">
            {isFinishedGoods ? <span className="block text-xs font-bold uppercase tracking-wide text-brand-700">{props.row.size || "-"}</span> : null}
            <span className="block truncate text-sm font-semibold text-zinc-950">{props.row.item || "-"}</span>
            <span className="mt-1 block text-xs text-zinc-500">
              {formatNumber(props.row.quantity)} {props.row.unit}
              {props.row.status === "In Stock" ? "" : ` · suggested reorder ${computeReorder(props.row.quantity, props.row.source.stock_type)}`}
            </span>
          </span>
          <StatusBadge status={props.row.status} />
        </span>
      </button>
      {props.expanded ? (
        <div className="bg-zinc-50 px-3 pb-3 pt-2">
          <dl className="grid grid-cols-2 gap-2 text-xs">
            <Detail label="Size" value={props.row.size} />
            <Detail label="Item" value={props.row.item || "-"} />
            <Detail label="Details" value={isFinishedGoods ? finishedGoodsDetails(props.row) : detailSummary(props.row)} />
            <Detail label="Stock" value={isFinishedGoods ? finishedGoodsStock(props.row) : `${formatNumber(props.row.quantity)} ${props.row.unit}`} />
          </dl>
          <div className="mt-3 flex gap-2">
            <Link className="inline-flex h-9 items-center gap-1 rounded-md border border-zinc-200 bg-white px-3 text-xs font-semibold text-zinc-700" to="/onboarding">
              <Edit3 className="h-4 w-4" /> Manage
            </Link>
            {bucketFor(props.row.source) === "finished_goods" && props.row.source.product_id ? (
              <ImageUploadButton row={props.row} uploadingId={props.uploadingId} onImageUpload={props.onImageUpload} />
            ) : null}
            {props.canDelete ? (
              <button className="inline-flex h-9 items-center gap-1 rounded-md border border-red-200 bg-white px-3 text-xs font-semibold text-red-700" type="button" onClick={() => props.onDelete(props.row)}>
                <Trash2 className="h-4 w-4" /> Delete
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function RowActions(props: Parameters<typeof InventoryGroupSection>[0] & { row: InventoryDisplayRow }) {
  return (
    <div className="flex items-center justify-end gap-1">
      <Link className="grid h-8 w-8 place-items-center rounded-md text-zinc-600 hover:bg-zinc-100" title="Manage item" to="/onboarding"><Edit3 className="h-4 w-4" /></Link>
      {bucketFor(props.row.source) === "finished_goods" && props.row.source.product_id ? (
        <ImageUploadButton row={props.row} uploadingId={props.uploadingId} onImageUpload={props.onImageUpload} iconOnly />
      ) : null}
      {props.canDelete ? (
        <button className="grid h-8 w-8 place-items-center rounded-md text-red-600 hover:bg-red-50" title="Delete item" type="button" onClick={() => props.onDelete(props.row)}>
          <Trash2 className="h-4 w-4" />
        </button>
      ) : null}
    </div>
  );
}

function ImageUploadButton(props: {
  row: InventoryDisplayRow;
  uploadingId: number | null;
  onImageUpload: (productId: number, file: File) => Promise<void>;
  iconOnly?: boolean;
}) {
  const productId = Number(props.row.source.product_id);
  const inputId = `inventory-image-${props.row.key.replace(/[^a-zA-Z0-9-]/g, "-")}`;
  return (
    <>
      <button
        className={props.iconOnly ? "grid h-8 w-8 place-items-center rounded-md text-brand-700 hover:bg-brand-50" : "inline-flex h-9 items-center gap-1 rounded-md border border-zinc-200 bg-white px-3 text-xs font-semibold text-brand-700"}
        disabled={props.uploadingId === productId}
        title="Upload image"
        type="button"
        onClick={() => document.getElementById(inputId)?.click()}
      >
        {props.uploadingId === productId ? <Loader2 className="h-4 w-4 animate-spin" /> : <Camera className="h-4 w-4" />}
        {props.iconOnly ? null : "Image"}
      </button>
      <input
        id={inputId}
        className="hidden"
        accept="image/*"
        type="file"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void props.onImageUpload(productId, file);
          event.target.value = "";
        }}
      />
    </>
  );
}

function buildGroups(
  rows: InventoryDisplayRow[],
  filter: InventoryFilter,
  search: string,
  sorts: Partial<Record<GroupKey, SortState>>
): InventoryGroup[] {
  const searched = rows.filter((row) => matchesSearch(row.source, search));
  const filtered = searched.filter((row) => matchesFilter(row, filter));
  const sourceGroups: InventoryGroup[] = [
    { key: "cup_blanks", title: "Raw Materials / Cup Blanks", rows: [] },
    { key: "bottom_reels", title: "Raw Materials / Bottom Reels", rows: [] },
    { key: "finished_goods", title: "Finished Goods", rows: [] },
    { key: "polybags_packing", title: "Packaging", rows: [] },
    { key: "boxes", title: "Boxes", rows: [] },
    { key: "raw_other", title: "Other Inventory", rows: [] },
    { key: "needs_mapping_review", title: "Needs Mapping Review", rows: [] }
  ];
  const groupMap = new Map(sourceGroups.map((group) => [group.key, group]));
  filtered.forEach((row) => groupMap.get(bucketFor(row.source))?.rows.push(row));

  const urgentRows = filtered
    .filter((row) => row.status !== "In Stock")
    .sort((a, b) => statusRank(a.status) - statusRank(b.status) || a.quantity - b.quantity);
  const groups: InventoryGroup[] = [
    ...sourceGroups,
    { key: "critical_low", title: "Critical & Low Stock", rows: urgentRows }
  ];
  return groups
    .map((group) => ({ ...group, rows: sortRows(group.rows, sorts[group.key] || null) }))
    .filter((group) => group.key === "critical_low" || group.key === "needs_mapping_review" || group.rows.length > 0);
}

function toDisplayRow(source: LiveStockRow): InventoryDisplayRow {
  const bucket = bucketFor(source);
  const quantity = Number(source.quantity || source.current_quantity || 0);
  return {
    key: `${source.stock_type}-${source.id}`,
    item: variantName(source, bucket),
    size: sizeLabel(source, bucket),
    quantity,
    unit: unitLabel(source.unit),
    status: statusFor(quantity, bucket),
    source
  };
}

function matchesSearch(row: LiveStockRow, query: string) {
  if (!query) return true;
  return [
    row.item_name,
    row.variety,
    row.product_size_ml,
    row.size_ml,
    row.size_mm,
    row.variant_name,
    row.packaging_size_name,
    row.packaging_size
  ].some((value) => String(value ?? "").toLowerCase().includes(query));
}

function matchesFilter(row: InventoryDisplayRow, filter: InventoryFilter) {
  if (filter === "all") return true;
  if (filter === "low") return row.status === "Low Stock";
  if (filter === "critical") return row.status === "Out of Stock";
  if (filter === "raw") return ["cup_blanks", "bottom_reels", "raw_other"].includes(bucketFor(row.source));
  if (filter === "finished") return bucketFor(row.source) === "finished_goods";
  return bucketFor(row.source) === "polybags_packing";
}

function riskCategories(rows: InventoryDisplayRow[]) {
  const groups: Array<{ label: string; buckets: InventoryBucket[] }> = [
    { label: "Raw", buckets: ["cup_blanks", "bottom_reels", "raw_other"] },
    { label: "Finished", buckets: ["finished_goods"] },
    { label: "Packaging", buckets: ["polybags_packing"] },
    { label: "Boxes", buckets: ["boxes"] },
    { label: "Other", buckets: ["needs_mapping_review"] },
    { label: "All", buckets: ["cup_blanks", "bottom_reels", "raw_other", "finished_goods", "polybags_packing", "boxes", "needs_mapping_review"] }
  ];
  return groups.map(({ label, buckets }) => {
    const categoryRows = rows.filter((row) => buckets.includes(bucketFor(row.source)));
    return {
      label,
      total: categoryRows.length,
      atRisk: categoryRows.filter((row) => row.status !== "In Stock").length
    };
  });
}

function sortRows(rows: InventoryDisplayRow[], sort: SortState) {
  if (!sort) return rows;
  const direction = sort.direction === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    if (sort.key === "stock") return (a.quantity - b.quantity) * direction;
    if (sort.key === "status") return (statusRank(a.status) - statusRank(b.status)) * direction;
    const left = sort.key === "size" ? a.size : a.item;
    const right = sort.key === "size" ? b.size : b.item;
    return left.localeCompare(right, undefined, { numeric: true }) * direction;
  });
}

function SortableTh(props: { label: string; sortKey: SortKey; sort: SortState; onSort: (key: SortKey) => void }) {
  const active = props.sort?.key === props.sortKey;
  return (
    <th className="whitespace-nowrap px-3 py-2 text-left font-semibold">
      <button className="inline-flex items-center gap-1 hover:text-zinc-900" type="button" onClick={() => props.onSort(props.sortKey)}>
        {props.label} {active ? (props.sort?.direction === "asc" ? "▲" : "▼") : null}
      </button>
    </th>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return <th className="whitespace-nowrap px-3 py-2 text-left font-semibold">{children}</th>;
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-zinc-500">{label}</dt><dd className="mt-0.5 font-semibold text-zinc-900">{value}</dd></div>;
}

function StatusBadge({ status }: { status: StockStatus }) {
  const classes = {
    "In Stock": "bg-zinc-100 text-zinc-700",
    "Low Stock": "bg-amber-100 text-amber-800",
    "Out of Stock": "bg-red-100 text-red-700"
  };
  return <span className={`inline-flex shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${classes[status]}`}>{status}</span>;
}

function bucketFor(row: LiveStockRow): InventoryBucket {
  const allowed: InventoryBucket[] = [
    "cup_blanks",
    "bottom_reels",
    "boxes",
    "polybags_packing",
    "finished_goods",
    "raw_other",
    "needs_mapping_review"
  ];
  return row.bucket && allowed.includes(row.bucket) ? row.bucket : "needs_mapping_review";
}

function groupLabel(row: LiveStockRow) {
  const labels: Record<InventoryBucket, string> = {
    finished_goods: "Finished",
    cup_blanks: "Blank",
    bottom_reels: "Bottom",
    boxes: "Box",
    polybags_packing: "Packing",
    raw_other: "Other",
    needs_mapping_review: "Review"
  };
  return labels[bucketFor(row)];
}

function variantName(row: LiveStockRow, bucket: InventoryBucket) {
  if (bucket === "finished_goods") return `${row.variety || "Plain White"} Cup`;
  if (bucket === "bottom_reels") return row.item_name || "Cup Bottom";
  if (bucket === "cup_blanks") return row.item_name || "Cup Blank";
  if (bucket === "boxes") return row.box_type || row.packaging_size_name || row.packaging_size || "Box";
  return row.item_name || row.packaging_size || "Inventory Item";
}

function sizeLabel(row: LiveStockRow, bucket: InventoryBucket) {
  if (bucket === "finished_goods") return row.product_size_ml ? `${row.product_size_ml}ml` : "-";
  if (bucket === "bottom_reels") return row.size_mm ? `${row.size_mm}mm` : "-";
  if (bucket === "cup_blanks") return row.size_ml ? `${row.size_ml}ml` : "-";
  return row.cup_size_ml ? `${row.cup_size_ml}ml` : row.packaging_size_name || row.packaging_size || "-";
}

function detailSummary(row: InventoryDisplayRow) {
  const source = row.source;
  const bucket = bucketFor(source);
  if (bucket === "finished_goods") return `${source.pieces_per_packet || "-"} pcs/pkt · ${source.packets_per_box_limit || source.packets_per_box || "-"} pkt/box`;
  if (bucket === "cup_blanks") return source.kg_per_sack ? `${source.kg_per_sack} kg/sack` : "-";
  if (bucket === "bottom_reels") return `${source.total_rolls || 0} rolls · ${source.total_weight_kg || row.quantity} kg`;
  if (bucket === "boxes") return source.price_per_box || source.price_per_unit ? `Rs ${source.price_per_box || source.price_per_unit}/box` : "-";
  if (bucket === "polybags_packing") return `${source.total_boras || 0} boras · ${source.weight_per_bora_kg || 0} kg/bora`;
  return source.variant_name || "-";
}

function finishedGoodsDetails(row: InventoryDisplayRow) {
  const source = row.source;
  const variety = source.variety || source.variant_name || "-";
  const packaging = source.packaging_size_name || source.packaging_size || "-";
  const piecesPerPacket = positiveNumberOrNull(source.pieces_per_packet);
  const packetsPerBox = positiveNumberOrNull(source.packets_per_box_limit ?? source.packets_per_box);
  const loosePackets = nonNegativeNumberOrNull(source.loose_packets);
  const looseSummary = loosePackets ? ` · ${loosePackets} loose pkt` : "";
  return `${variety} · ${packaging} · ${piecesPerPacket ?? "-"} pcs/pkt · ${packetsPerBox ?? "-"} pkt/box${looseSummary}`;
}

function finishedGoodsStock(row: InventoryDisplayRow) {
  const source = row.source;
  const boxes = nonNegativeNumberOrNull(source.total_boxes) ?? nonNegativeNumberOrNull(row.quantity);
  const loosePackets = nonNegativeNumberOrNull(source.loose_packets) ?? 0;
  const piecesPerPacket = positiveNumberOrNull(source.pieces_per_packet);
  const packetsPerBox = positiveNumberOrNull(source.packets_per_box_limit ?? source.packets_per_box);
  const totalPieces = boxes !== null && piecesPerPacket !== null && packetsPerBox !== null
    ? (boxes * packetsPerBox + loosePackets) * piecesPerPacket
    : null;
  return `${boxes ?? "-"} boxes · ${loosePackets} loose pkt${totalPieces === null ? "" : ` · ${formatNumber(totalPieces)} pcs`}`;
}

function positiveNumberOrNull(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function nonNegativeNumberOrNull(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function statusFor(quantity: number, bucket: InventoryBucket): StockStatus {
  if (quantity <= 0) return "Out of Stock";
  const threshold = bucket === "finished_goods" || bucket === "boxes" ? 10 : 25;
  return quantity <= threshold ? "Low Stock" : "In Stock";
}

function statusRank(status: StockStatus) {
  return status === "Out of Stock" ? 0 : status === "Low Stock" ? 1 : 2;
}

function computeReorder(quantity: number, stockType: LiveStockRow["stock_type"]) {
  const threshold = ["Final Product", "Carton Box", "Box"].includes(stockType) ? 10 : 25;
  const target = Math.max(threshold * 2, Math.ceil(quantity * 1.5));
  return Math.max(target - quantity, 0);
}

function statusBar(status: StockStatus) {
  if (status === "Out of Stock") return "border-l-red-600";
  if (status === "Low Stock") return "border-l-amber-500";
  return "border-l-transparent";
}

function reorderTone(status: StockStatus) {
  if (status === "Out of Stock") return "text-red-700";
  if (status === "Low Stock") return "text-amber-700";
  return "text-zinc-400";
}

function relativeTime(date: Date) {
  const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  return `${minutes} min ago`;
}

function formatNumber(value: number) {
  return Number(value || 0).toLocaleString("en-IN");
}

function unitLabel(unit: string) {
  if (unit === "boxes") return "boxes";
  if (unit === "pcs") return "pcs";
  if (unit === "kg") return "kg";
  return unit || "units";
}
