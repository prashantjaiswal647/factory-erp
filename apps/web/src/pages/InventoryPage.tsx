import { Camera, ChevronDown, Edit3, Filter, Loader2, Package, PackagePlus, RefreshCw, Trash2 } from "lucide-react";
import { API_BASE_URL } from "../lib/api";
import axios from "axios";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { getInventory, deleteOnboardingItem } from "../lib/api";
import type { LiveStockRow } from "../lib/api";

type InventoryFilter = "all" | "raw" | "wip" | "finished" | "packing" | "low";
type StockStatus = "In Stock" | "Low Stock" | "Out of Stock";

type InventoryCategory = {
  key: string;
  title: string;
  tone: string;
  rows: InventoryDisplayRow[];
};

type InventoryDisplayRow = {
  key: string;
  variant: string;
  size: string;
  quantity: number;
  quantityLabel: string;
  unitType: string;
  perBox: string;
  totalPieces: string;
  location: string;
  status: StockStatus;
  source: LiveStockRow;
  image_url?: string | null;
  variant_name?: string | null;
};

const filters: Array<{ key: InventoryFilter; label: string }> = [
  { key: "all", label: "All Items" },
  { key: "raw", label: "Raw Materials" },
  { key: "wip", label: "Work In Progress" },
  { key: "finished", label: "Finished Goods" },
  { key: "packing", label: "Packing Materials" },
  { key: "low", label: "Low Stock" }
];

export default function InventoryPage() {
  const { user } = useAuth();
  const canDelete = user?.role === "Owner";
  const [rows, setRows] = useState<LiveStockRow[]>([]);
  const [activeFilter, setActiveFilter] = useState<InventoryFilter>("all");
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [uploadingId, setUploadingId] = useState<number | null>(null);

  async function handleImageUpload(productId: number, file: File) {
    const formData = new FormData();
    formData.append("file", file);

    setUploadingId(productId);
    try {
      const token = localStorage.getItem("token") || localStorage.getItem("ai_erp_token");
      await axios.post(`${API_BASE_URL}/api/inventory/final-stock/${productId}/image`, formData, {
        headers: {
          "Content-Type": "multipart/form-data",
          Authorization: `Bearer ${token}`
        }
      });
      await load();
    } catch (caught: any) {
      const message = caught.response?.data?.detail || caught.message || "Failed to upload image";
      alert(message);
    } finally {
      setUploadingId(null);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    setIsLoading(true);
    setError("");
    try {
      const response = await getInventory();
      setRows(Array.isArray(response.data) ? response.data : []);
    } catch (caught) {
      const message = axios.isAxiosError(caught) ? caught.response?.data?.detail || caught.message : "Inventory load failed";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }

  async function handleDelete(row: InventoryDisplayRow) {
    if (!canDelete) {
      alert("Access Denied: Only the Factory Owner is authorized to delete entries.");
      return;
    }
    if (!window.confirm("Are you sure you want to remove this entry?")) {
      return;
    }
    try {
      const entryId = row.source.id;
      const type = row.source.stock_type;
      
      let actualId = entryId;
      let actualType: string = type;

      if (typeof entryId === "string") {
        if (entryId.startsWith("blank-")) {
          actualId = entryId.replace("blank-", "");
          actualType = "blankstock";
        } else if (entryId.startsWith("bottom-")) {
          actualId = entryId.replace("bottom-", "");
          actualType = "bottomstock";
        } else if (entryId.startsWith("box-")) {
          actualId = entryId.replace("box-", "");
          actualType = "boxstock";
        } else if (entryId.startsWith("plastic-")) {
          actualId = entryId.replace("plastic-", "");
          actualType = "plasticstock";
        } else if (entryId.startsWith("polybag-")) {
          actualId = entryId.replace("polybag-", "");
          actualType = "polybagstock";
        } else if (entryId.startsWith("final-")) {
          actualId = entryId.replace("final-", "");
          actualType = "final";
        }
      } else {
        if (String(type) === "Carton Box" || String(type) === "Packaging") {
          actualType = "boxstock";
        }
      }

      await deleteOnboardingItem(Number(actualId), actualType);
      await load();
    } catch (caught) {
      const message = axios.isAxiosError(caught) ? caught.response?.data?.detail || caught.message : "Failed to delete entry";
      alert(message);
    }
  }


  const categories = useMemo(() => buildInventoryCategories(rows, activeFilter), [rows, activeFilter]);
  const totalVariants = categories.reduce((sum, category) => sum + category.rows.length, 0);
  const lowStockCount = categories.flatMap((category) => category.rows).filter((row) => row.status !== "In Stock").length;

  return (
    <div className="min-w-0 space-y-5 overflow-x-hidden">
      <header className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-950">Inventory</h1>
          <p className="mt-1 text-sm text-zinc-500">Manage raw materials, work in progress, packing stock, and finished goods.</p>
          <p className="mt-2 text-xs font-medium text-zinc-500">{totalVariants} variants tracked · {lowStockCount} attention items</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button className="inline-flex h-10 items-center gap-2 rounded-lg border border-zinc-200 bg-white px-4 text-sm font-semibold text-zinc-700 hover:bg-zinc-50" type="button">
            <Filter className="h-4 w-4" />
            Filters
          </button>
          <Link className="inline-flex h-10 items-center gap-2 rounded-lg bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700" to="/onboarding">
            <PackagePlus className="h-4 w-4" />
            Add Item
          </Link>
          <button className="inline-flex h-10 items-center gap-2 rounded-lg border border-zinc-200 bg-white px-4 text-sm font-semibold text-zinc-700 hover:bg-brand-50" type="button" onClick={load}>
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
        </div>
      </header>

      <nav className="flex gap-2 overflow-x-auto border-b border-zinc-200 pb-1">
        {filters.map((filter) => (
          <button
            key={filter.key}
            className={`shrink-0 border-b-2 px-3 py-3 text-sm font-semibold transition ${
              activeFilter === filter.key ? "border-brand-600 text-brand-700" : "border-transparent text-zinc-500 hover:text-zinc-900"
            }`}
            type="button"
            onClick={() => setActiveFilter(filter.key)}
          >
            {filter.label}
          </button>
        ))}
      </nav>

      {error ? <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm font-medium text-red-700">{error}</div> : null}

      {isLoading ? (
        <div className="rounded-xl border border-zinc-200 bg-white p-8 text-sm text-zinc-500">Loading categorized inventory...</div>
      ) : categories.every((category) => category.rows.length === 0) ? (
        <div className="rounded-xl border border-dashed border-zinc-300 bg-white p-8 text-center text-sm text-zinc-500">
          No inventory rows found for this filter.
        </div>
      ) : (
        <section className="space-y-5">
          {categories.map((category) => (
            <CategoryCard
              key={category.key}
              category={category}
              isCollapsed={Boolean(collapsed[category.key])}
              onToggle={() => setCollapsed((current) => ({ ...current, [category.key]: !current[category.key] }))}
              onDelete={handleDelete}
              canDelete={canDelete}
              onImageUpload={handleImageUpload}
              uploadingId={uploadingId}
            />
          ))}
        </section>
      )}

      <footer className="flex items-center gap-2 border-t border-zinc-200 pt-4 text-xs text-zinc-500">
        <span className="grid h-5 w-5 place-items-center rounded-full bg-brand-50 text-brand-700">i</span>
        Stock data is updated from the live PostgreSQL inventory API. Last refreshed from this browser session.
      </footer>
    </div>
  );
}

function getFallbackGradient(key: string) {
  const gradients = [
    "linear-gradient(135deg, #4f46e5, #06b6d4)", // indigo to cyan
    "linear-gradient(135deg, #f59e0b, #e11d48)", // amber to rose
    "linear-gradient(135deg, #10b981, #3b82f6)", // emerald to blue
    "linear-gradient(135deg, #8b5cf6, #ec4899)", // violet to pink
    "linear-gradient(135deg, #64748b, #475569)"  // slate
  ];
  let hash = 0;
  for (let i = 0; i < key.length; i++) {
    hash = key.charCodeAt(i) + ((hash << 5) - hash);
  }
  return gradients[Math.abs(hash) % gradients.length];
}

function CategoryCard({
  category,
  isCollapsed,
  onToggle,
  onDelete,
  canDelete,
  onImageUpload,
  uploadingId
}: {
  category: InventoryCategory;
  isCollapsed: boolean;
  onToggle: () => void;
  onDelete: (row: InventoryDisplayRow) => void;
  canDelete: boolean;
  onImageUpload: (productId: number, file: File) => Promise<void>;
  uploadingId: number | null;
}) {
  return (
    <section className="min-w-0 rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm sm:p-5">
      <header className="flex items-center justify-between gap-3 border-b border-zinc-100 pb-3">
        <div className="flex min-w-0 items-center gap-3">
          <h2 className="truncate text-base font-semibold text-zinc-950 sm:text-lg">{category.title}</h2>
          <span className="shrink-0 rounded-full bg-brand-50 px-2.5 py-1 text-xs font-semibold text-brand-700">
            {category.rows.length} {category.rows.length === 1 ? "Variant" : "Variants"}
          </span>
        </div>
        <button className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-zinc-200 text-brand-700 hover:bg-brand-50" type="button" onClick={onToggle}>
          <ChevronDown className={`h-4 w-4 transition ${isCollapsed ? "-rotate-90" : ""}`} />
        </button>
      </header>
 
      {isCollapsed ? null : category.rows.length === 0 ? (
        <div className="mt-4 rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-6 text-sm text-zinc-500">
          No {category.title.toLowerCase()} rows found.
        </div>
      ) : (
        <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
          {category.rows.map((row) => {
            const isFinalProduct = row.source.stock_type === "Final Product" || row.source.product_id != null;
            const productId = row.source.product_id;
            const fileInputId = `image-upload-${productId}`;

            return (
              <div
                key={row.key}
                className="group relative overflow-hidden rounded-2xl border border-zinc-200 bg-white p-0 shadow-sm transition-all duration-300 hover:shadow-md hover:border-zinc-300 flex flex-col"
              >
                {/* Image layout window box profile element */}
                <div className="relative h-44 w-full overflow-hidden bg-zinc-100 border-b border-zinc-100 flex-shrink-0">
                  {row.image_url ? (
                    <img
                      src={row.image_url.startsWith("http") ? row.image_url : `${API_BASE_URL}${row.image_url}`}
                      alt={row.variant}
                      className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
                      onError={(e) => {
                        (e.target as HTMLElement).style.display = 'none';
                        const sibling = (e.target as HTMLElement).nextElementSibling;
                        if (sibling) (sibling as HTMLElement).style.display = 'flex';
                      }}
                    />
                  ) : null}
                  
                  {/* Fallback placeholder layout configurations */}
                  <div
                    className="absolute inset-0 flex flex-col items-center justify-center p-4 text-white text-center gap-2 select-none"
                    style={{
                      display: row.image_url ? 'none' : 'flex',
                      background: getFallbackGradient(row.key)
                    }}
                  >
                    <span className="rounded-full bg-white/20 p-2.5 backdrop-blur-md">
                      <Package className="h-6 w-6 text-white" />
                    </span>
                    <div>
                      <p className="text-xs font-bold uppercase tracking-wider opacity-90">{row.source.stock_type || "Stock"}</p>
                      <p className="text-[10px] opacity-75 mt-0.5">{row.size}</p>
                    </div>
                  </div>

                  {/* Status badge floating on the image */}
                  <div className="absolute top-3 right-3 z-10">
                    <StatusBadge status={row.status} />
                  </div>

                  {/* Hover overlays for actions */}
                  <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-center justify-center gap-2.5 z-20">
                    {isFinalProduct && productId ? (
                      <>
                        <button
                          type="button"
                          disabled={uploadingId === productId}
                          onClick={() => document.getElementById(fileInputId)?.click()}
                          className="grid h-10 w-10 place-items-center rounded-xl bg-white text-zinc-800 shadow-md hover:bg-zinc-50 hover:scale-105 active:scale-95 transition-all"
                          title="Upload stock image"
                        >
                          {uploadingId === productId ? (
                            <Loader2 className="h-5 w-5 animate-spin text-brand-600" />
                          ) : (
                            <Camera className="h-5 w-5 text-brand-600" />
                          )}
                        </button>
                        <input
                          id={fileInputId}
                          type="file"
                          accept="image/*"
                          className="hidden"
                          onChange={(e) => {
                            const file = e.target.files?.[0];
                            if (file) {
                              void onImageUpload(productId, file);
                            }
                          }}
                        />
                      </>
                    ) : null}
                    
                    <ActionButtons row={row} onDelete={onDelete} canDelete={canDelete} />
                  </div>
                </div>

                {/* Content Area */}
                <div className="p-4 flex flex-col flex-grow justify-between gap-3">
                  <div className="space-y-1 text-left">
                    <h3 className="font-bold text-zinc-900 group-hover:text-brand-700 transition-colors text-sm line-clamp-1">
                      {row.variant}
                    </h3>
                    
                    {row.source.variant_name ? (
                      <span className="inline-block rounded-md bg-zinc-100 px-2 py-0.5 text-[10px] font-semibold text-zinc-600">
                        Code: {row.source.variant_name}
                      </span>
                    ) : null}
                    
                    <p className="text-xs text-zinc-500 line-clamp-1">
                      Size: {row.size} · Location: {row.location}
                    </p>
                  </div>

                  {/* Metric info grid */}
                  <div className="grid grid-cols-2 gap-3 border-t border-zinc-100 pt-3 text-left">
                    <div>
                      <p className="text-[10px] font-medium uppercase tracking-wider text-zinc-400">Available Stock</p>
                      <p className="mt-0.5 text-xs font-bold text-zinc-800">{row.quantityLabel}</p>
                    </div>
                    <div>
                      <p className="text-[10px] font-medium uppercase tracking-wider text-zinc-400">Unit / Capacity</p>
                      <p className="mt-0.5 text-xs font-semibold text-zinc-700">{row.perBox}</p>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

function buildInventoryCategories(rows: LiveStockRow[], activeFilter: InventoryFilter): InventoryCategory[] {
  const base: InventoryCategory[] = [
    { key: "finished", title: "Finished Paper Cups", tone: "brand", rows: [] },
    { key: "bottom", title: "Cup Bottom", tone: "blue", rows: [] },
    { key: "blank", title: "Cup Blank", tone: "amber", rows: [] },
    { key: "boxes", title: "Corrugated Boxes", tone: "green", rows: [] },
    { key: "raw", title: "Raw Materials", tone: "zinc", rows: [] },
    { key: "packing", title: "Packing Materials", tone: "purple", rows: [] },
    { key: "other", title: "Other Consumables", tone: "zinc", rows: [] }
  ];

  const categoryMap = new Map(base.map((category) => [category.key, category]));
  rows.forEach((row) => {
    const displayRow = toDisplayRow(row);
    categoryMap.get(categoryKeyFor(row))?.rows.push(displayRow);
  });

  return base
    .map((category) => ({ ...category, rows: filterRows(category.key, category.rows, activeFilter) }))
    .filter((category) => activeFilter === "all" || category.rows.length > 0 || ["finished", "bottom", "blank", "boxes"].includes(category.key));
}

function filterRows(categoryKey: string, rows: InventoryDisplayRow[], activeFilter: InventoryFilter) {
  if (activeFilter === "all") return rows;
  if (activeFilter === "low") return rows.filter((row) => row.status !== "In Stock");
  if (activeFilter === "finished") return categoryKey === "finished" ? rows : [];
  if (activeFilter === "packing") return ["boxes", "packing"].includes(categoryKey) ? rows : [];
  if (activeFilter === "raw") return ["blank", "bottom", "raw"].includes(categoryKey) ? rows : [];
  if (activeFilter === "wip") return ["blank", "bottom"].includes(categoryKey) ? rows : [];
  return rows;
}

function toDisplayRow(row: LiveStockRow): InventoryDisplayRow {
  const type = normalizedType(row);
  const quantity = Number(row.quantity || row.current_quantity || 0);
  const piecesPerPacket = Number(row.pieces_per_packet || 0);
  const packetsPerBox = Number(row.packets_per_box_limit || row.packets_per_box || 0);
  const piecesPerBox = type === "Final Product" ? piecesPerPacket * packetsPerBox : 0;
  return {
    key: `${row.stock_type}-${row.id}`,
    variant: variantName(row, type),
    size: sizeLabel(row, type),
    quantity,
    quantityLabel: `${formatNumber(quantity)} ${unitLabel(row.unit)}`,
    unitType: unitLabel(row.unit),
    perBox: piecesPerBox > 0 ? `${formatNumber(piecesPerBox)} pcs` : perBundleLabel(row, type),
    totalPieces: piecesPerBox > 0 ? `${formatNumber(quantity * piecesPerBox)} pcs` : totalPiecesFallback(row, type),
    location: locationFor(type),
    status: statusFor(quantity, type),
    source: row,
    image_url: row.image_url,
    variant_name: row.variant_name
  };
}

function categoryKeyFor(row: LiveStockRow) {
  const type = normalizedType(row);
  if (type === "Final Product") return "finished";
  if (type === "Bottom") return "bottom";
  if (type === "Blank") return "blank";
  if (type === "Carton Box") return "boxes";
  if (type === "Polybag") return "packing";
  if (type === "Inventory") return "raw";
  return "other";
}

function normalizedType(row: LiveStockRow): string {
  const raw = `${row.stock_type || ""} ${row.category || ""} ${row.item_name || ""}`.toLowerCase();
  if (raw.includes("final")) return "Final Product";
  if (raw.includes("bottom")) return "Bottom";
  if (raw.includes("blank")) return "Blank";
  if (raw.includes("carton") || raw.includes("box")) return "Carton Box";
  if (raw.includes("poly") || raw.includes("plastic") || raw.includes("packing")) return "Polybag";
  if (raw.includes("inventory") || raw.includes("raw")) return "Inventory";
  return "Other";
}

function variantName(row: LiveStockRow, type: string) {
  if (type === "Final Product") return `${row.variety || "Plain White"} Cup`;
  if (type === "Bottom") return row.item_name || "Bottom";
  if (type === "Blank") return row.item_name || "Blank";
  if (type === "Carton Box") return row.packaging_size_name || row.packaging_size || "Box";
  return row.item_name || "Inventory Item";
}

function sizeLabel(row: LiveStockRow, type: string) {
  if (type === "Final Product") return row.product_size_ml ? `${row.product_size_ml}ml` : "-";
  if (type === "Bottom") return row.size_mm ? `${row.size_mm}mm` : "All Sizes";
  if (type === "Blank") {
    const match = String(row.item_name || "").match(/(\d+)\s*ml/i);
    return match ? `${match[1]}ml` : "All Sizes";
  }
  return row.packaging_size_name || row.packaging_size || "Standard";
}

function perBundleLabel(row: LiveStockRow, type: string) {
  if (type === "Bottom" && row.total_rolls) return `${formatNumber(row.total_rolls)} rolls`;
  if (type === "Blank") return "kg stock";
  if (type === "Carton Box") return "1 pc";
  return "-";
}

function totalPiecesFallback(row: LiveStockRow, type: string) {
  if (type === "Bottom" && row.total_rolls) return `${formatNumber(row.total_rolls)} rolls`;
  if (type === "Carton Box") return `${formatNumber(Number(row.quantity || 0))} pcs`;
  return "-";
}

function statusFor(quantity: number, type: string): StockStatus {
  if (quantity <= 0) return "Out of Stock";
  const lowThreshold = type === "Final Product" || type === "Carton Box" ? 10 : 25;
  return quantity <= lowThreshold ? "Low Stock" : "In Stock";
}

function locationFor(type: string) {
  if (type === "Carton Box" || type === "Polybag") return "Store Room";
  if (type === "Inventory" || type === "Other") return "Raw Store";
  return "Main Warehouse";
}

function ActionButtons({ row, onDelete, canDelete }: { row: InventoryDisplayRow; onDelete: (row: InventoryDisplayRow) => void; canDelete: boolean }) {
  return (
    <div className="flex items-center gap-1.5">
      <Link className="grid h-8 w-8 place-items-center rounded-lg text-brand-700 hover:bg-brand-50" title="Edit item" to="/onboarding">
        <Edit3 className="h-4 w-4" />
      </Link>
      {canDelete ? (
        <button
          className="grid h-8 w-8 place-items-center rounded-lg text-red-600 hover:bg-red-50"
          title="Delete item"
          type="button"
          onClick={() => onDelete(row)}
        >
          <Trash2 className="h-4 w-4" />
        </button>
      ) : null}
    </div>
  );
}

function StatusBadge({ status }: { status: StockStatus }) {
  const classes = {
    "In Stock": "bg-emerald-100 text-emerald-700",
    "Low Stock": "bg-amber-100 text-amber-800",
    "Out of Stock": "bg-red-100 text-red-700"
  };
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${classes[status]}`}>{status}</span>;
}

function Th({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <th className={`px-3 py-3 text-left font-semibold ${className}`}>{children}</th>;
}

function Td({ children, strong = false }: { children: ReactNode; strong?: boolean }) {
  return <td className={`truncate px-3 py-3 ${strong ? "font-semibold text-zinc-950" : "text-zinc-700"}`}>{children}</td>;
}

function MobileMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-zinc-500">{label}</p>
      <p className="mt-1 font-semibold text-zinc-900">{value}</p>
    </div>
  );
}

function formatNumber(value: number) {
  return Number(value || 0).toLocaleString("en-IN");
}

function unitLabel(unit: string) {
  if (unit === "boxes") return "Boxes";
  if (unit === "pcs") return "Pcs";
  if (unit === "kg") return "Kg";
  return unit || "Units";
}
