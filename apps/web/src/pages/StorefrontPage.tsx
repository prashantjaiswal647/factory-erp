import { Lock, Minus, Package, Plus, ShoppingCart } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import LoadingState from "../components/LoadingState";
import { api } from "../lib/api";
import { asNumber, formatCurrency } from "../lib/format";

type StorefrontProduct = {
  product_id: number;
  cup_size_ml: number;
  packaging_profile_name: string;
  availability_status: "In Stock" | "Low Stock" | "Out of Stock";
  base_price: string;
  image_url?: string | null;
  print_design_name?: string | null;
};

type Storefront = {
  customer_id: number;
  customer_name: string;
  contact_number: string | null;
  advance_discount_pct: number;
  terms_and_conditions: string;
  products: StorefrontProduct[];
};

type CheckoutResponse = {
  order_id: number;
  status: string;
  total_amount: string;
  previous_balance: string;
  new_total_balance: string;
};

const fallbackPrints = [
  "linear-gradient(135deg, #6D28D9, #4C1D95)",
  "linear-gradient(135deg, #b45309, #f59e0b)",
  "linear-gradient(135deg, #F3E8FF, #6D28D9)",
  "linear-gradient(135deg, #be123c, #fb7185)"
];

export default function StorefrontPage() {
  const { storeToken } = useParams();
  const navigate = useNavigate();
  const [storefront, setStorefront] = useState<Storefront | null>(null);
  const [quantities, setQuantities] = useState<Record<number, number>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [isOrdering, setIsOrdering] = useState(false);
  const [accessDenied, setAccessDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadStorefront() {
      if (!storeToken) {
        setAccessDenied(true);
        setIsLoading(false);
        return;
      }

      setIsLoading(true);
      setAccessDenied(false);
      setError(null);
      try {
        const response = await api.get<Storefront>(`/api/storefront/${storeToken}`);
        setStorefront(response.data);
      } catch {
        setAccessDenied(true);
      } finally {
        setIsLoading(false);
      }
    }

    void loadStorefront();
  }, [storeToken]);

  const selectedItems = useMemo(() => {
    return (
      storefront?.products
        .map((product) => ({ ...product, quantity: quantities[product.product_id] ?? 0 }))
        .filter((product) => product.quantity > 0) ?? []
    );
  }, [quantities, storefront]);

  const cartTotal = selectedItems.reduce(
    (total, product) => total + asNumber(product.base_price) * product.quantity,
    0
  );

  function updateQuantity(product: StorefrontProduct, nextQuantity: number) {
    if (product.availability_status === "Out of Stock") {
      return;
    }
    setQuantities((current) => ({
      ...current,
      [product.product_id]: Math.min(Math.max(nextQuantity, 0), 999)
    }));
  }

  async function placeOrder() {
    if (!storeToken || selectedItems.length === 0) {
      return;
    }

    setIsOrdering(true);
    setError(null);
    try {
      const response = await api.post<CheckoutResponse>(`/api/storefront/${storeToken}/order`, {
        payment_method: "Normal_Credit",
        terms_accepted: true,
        items: selectedItems.map((item) => ({
          product_id: item.product_id,
          quantity: item.quantity
        }))
      });
      navigate(`/storefront/${storeToken}/success`, { state: response.data });
    } catch {
      setError("Order could not be placed. Please reduce quantity or contact the factory.");
    } finally {
      setIsOrdering(false);
    }
  }

  if (isLoading) {
    return (
      <main className="min-h-screen bg-zinc-50 px-4 py-10">
        <LoadingState label="Opening storefront..." />
      </main>
    );
  }

  if (accessDenied || !storefront) {
    return (
      <main className="grid min-h-screen place-items-center bg-zinc-50 px-4">
        <section className="w-full max-w-sm rounded-md border border-zinc-200 bg-white p-6 text-center shadow-sm">
          <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-md bg-red-50 text-red-600">
            <Lock className="h-6 w-6" />
          </div>
          <h1 className="text-xl font-semibold text-zinc-950">Access Denied</h1>
          <p className="mt-2 text-sm text-zinc-500">This private ordering link is invalid or not approved.</p>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-zinc-50 text-zinc-950">
      <header className="sticky top-0 z-10 border-b border-zinc-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-4">
          <div>
            <p className="text-xs font-semibold uppercase text-brand-700">Private B2B Store</p>
            <h1 className="text-lg font-semibold">{storefront.customer_name}</h1>
          </div>
          <div className="text-right">
            <p className="text-xs text-zinc-500">Cart</p>
            <p className="font-semibold">{formatCurrency(cartTotal)}</p>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-5xl px-4 py-5">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {storefront.products.map((product, index) => {
            const quantity = quantities[product.product_id] ?? 0;
            const isOut = product.availability_status === "Out of Stock";
            return (
              <article key={product.product_id} className="overflow-hidden rounded-md border border-zinc-200 bg-white shadow-sm">
                {product.image_url ? (
                  <img className="h-36 w-full object-cover" src={product.image_url} alt={product.packaging_profile_name} />
                ) : (
                  <div className="grid h-36 place-items-center text-white" style={{ background: fallbackPrints[index % fallbackPrints.length] }}>
                    <Package className="h-12 w-12" />
                  </div>
                )}

                <div className="space-y-4 p-4">
                  <div>
                    <div className="flex items-start justify-between gap-3">
                      <h2 className="font-semibold">{product.packaging_profile_name}</h2>
                      <span className={availabilityClass(product.availability_status)}>
                        {product.availability_status}
                      </span>
                    </div>
                    <p className="mt-1 text-sm text-zinc-500">
                      {product.print_design_name || `${product.cup_size_ml}ml Paper Cup`}
                    </p>
                  </div>

                  <div className="flex items-center justify-between">
                    <p className="text-lg font-semibold">{formatCurrency(product.base_price)}</p>
                    <div className="flex h-10 items-center rounded-md border border-zinc-200 bg-zinc-50 p-1">
                      <button
                        type="button"
                        className="grid h-8 w-8 place-items-center rounded-md text-zinc-600 disabled:text-zinc-300"
                        disabled={quantity === 0}
                        onClick={() => updateQuantity(product, quantity - 1)}
                        aria-label="Reduce quantity"
                      >
                        <Minus className="h-4 w-4" />
                      </button>
                      <span className="w-9 text-center text-sm font-semibold">{quantity}</span>
                      <button
                        type="button"
                        className="grid h-8 w-8 place-items-center rounded-md text-zinc-600 disabled:text-zinc-300"
                        disabled={isOut}
                        onClick={() => updateQuantity(product, quantity + 1)}
                        aria-label="Add quantity"
                      >
                        <Plus className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                </div>
              </article>
            );
          })}
        </div>

        {error ? <p className="mt-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p> : null}

        <div className="sticky bottom-0 mt-6 border-t border-zinc-200 bg-zinc-50 py-4">
          <button
            type="button"
            disabled={selectedItems.length === 0 || isOrdering}
            onClick={placeOrder}
            className="flex h-12 w-full items-center justify-center gap-2 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white shadow-sm hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-zinc-300"
          >
            <ShoppingCart className="h-4 w-4" />
            {isOrdering ? "Placing Order..." : "Place Order"}
          </button>
        </div>
      </div>
    </main>
  );
}

function availabilityClass(status: StorefrontProduct["availability_status"]) {
  if (status === "Out of Stock") {
    return "rounded-full bg-red-50 px-2 py-1 text-xs font-semibold text-red-700";
  }
  if (status === "Low Stock") {
    return "rounded-full bg-amber-50 px-2 py-1 text-xs font-semibold text-amber-700";
  }
  return "rounded-full bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-700";
}
