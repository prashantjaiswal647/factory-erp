import {
  AlertTriangle,
  Check,
  CreditCard,
  Minus,
  Package,
  Plus,
  QrCode,
  Truck
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import EmptyState from "../components/EmptyState";
import LoadingState from "../components/LoadingState";
import { api } from "../lib/api";
import { asNumber, formatNumber } from "../lib/format";

type PaymentMethod = "Normal_Credit" | "Full_Advance_UPI" | "Full_Advance_Doorstep";

type StorefrontProduct = {
  product_id: number;
  cup_size_ml: number;
  packaging_profile_name: string;
  boxes_available: number;
  base_price: string;
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
  message: string;
  order_id: number;
  status: string;
  payment_method: PaymentMethod;
  discount_pct: string;
  discount_amount: string;
  total_amount: string;
  upi_payment_details?: {
    bank_name: string;
    account_name: string;
    account_number: string;
    ifsc: string;
    upi_id: string;
  } | null;
  items: Array<{
    product_id: number;
    packaging_profile_name: string;
    quantity: number;
    base_rate: string;
    final_rate: string;
    line_total: string;
  }>;
};

const paymentOptions: Array<{
  method: PaymentMethod;
  title: string;
  icon: typeof CreditCard;
  tone: string;
}> = [
  {
    method: "Normal_Credit",
    title: "Normal Credit (Standard Rates)",
    icon: CreditCard,
    tone: "border-zinc-200 bg-white text-zinc-700"
  },
  {
    method: "Full_Advance_UPI",
    title: "Pay Now via UPI (Get X% Discount!)",
    icon: QrCode,
    tone: "border-brand-100 bg-brand-50 text-brand-700"
  },
  {
    method: "Full_Advance_Doorstep",
    title: "100% Cash at Doorstep (Get X% Discount!)",
    icon: Truck,
    tone: "border-amber-200 bg-amber-50 text-amber-900"
  }
];

function getPaymentLabel(method: PaymentMethod, discountPct: number) {
  const discount = `${formatNumber(discountPct, 2)}%`;
  if (method === "Full_Advance_UPI") {
    return `Pay Now via UPI (Get ${discount} Discount!)`;
  }
  if (method === "Full_Advance_Doorstep") {
    return `100% Cash at Doorstep (Get ${discount} Discount!)`;
  }
  return "Normal Credit (Standard Rates)";
}

function formatStoreCurrency(value: number | string | null | undefined) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(asNumber(value));
}

export default function CustomerStorefrontPage() {
  const { storeToken } = useParams();
  const navigate = useNavigate();
  const [storefront, setStorefront] = useState<Storefront | null>(null);
  const [quantities, setQuantities] = useState<Record<number, number>>({});
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>("Normal_Credit");
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isCheckingOut, setIsCheckingOut] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadStorefront() {
      if (!storeToken) {
        setError("Store link is missing.");
        setIsLoading(false);
        return;
      }

      setIsLoading(true);
      setError(null);
      try {
        const response = await api.get<Storefront>(`/api/store/${storeToken}`);
        setStorefront(response.data);
      } catch {
        setError("Storefront is unavailable or the link is invalid.");
      } finally {
        setIsLoading(false);
      }
    }

    void loadStorefront();
  }, [storeToken]);

  const selectedItems = useMemo(() => {
    return (
      storefront?.products
        .map((product) => ({
          ...product,
          quantity: quantities[product.product_id] ?? 0
        }))
        .filter((product) => product.quantity > 0) ?? []
    );
  }, [quantities, storefront]);

  const baseTotal = useMemo(() => {
    return selectedItems.reduce((total, product) => {
      return total + asNumber(product.base_price) * product.quantity;
    }, 0);
  }, [selectedItems]);

  const discountPct = storefront?.advance_discount_pct ?? 0;
  const isDiscounted = paymentMethod === "Full_Advance_UPI" || paymentMethod === "Full_Advance_Doorstep";
  const discountAmount = isDiscounted ? baseTotal * (discountPct / 100) : 0;
  const cartTotal = Math.max(baseTotal - discountAmount, 0);

  function updateQuantity(product: StorefrontProduct, nextQuantity: number) {
    const boundedQuantity = Math.min(Math.max(nextQuantity, 0), product.boxes_available);
    setQuantities((current) => ({
      ...current,
      [product.product_id]: boundedQuantity
    }));
  }

  async function checkout() {
    if (!storeToken || selectedItems.length === 0 || !termsAccepted) {
      return;
    }

    setIsCheckingOut(true);
    setError(null);
    try {
      const response = await api.post<CheckoutResponse>(`/api/store/${storeToken}/checkout`, {
        payment_method: paymentMethod,
        terms_accepted: termsAccepted,
        items: selectedItems.map((item) => ({
          product_id: item.product_id,
          quantity: item.quantity
        }))
      });

      navigate(`/store/${storeToken}/success`, { state: response.data });
    } catch {
      setError("Unable to place this order. Please check available stock and try again.");
    } finally {
      setIsCheckingOut(false);
    }
  }

  if (isLoading) {
    return (
      <main className="min-h-screen bg-zinc-100 px-4 py-10">
        <LoadingState label="Loading customer store..." />
      </main>
    );
  }

  if (error && !storefront) {
    return (
      <main className="min-h-screen bg-zinc-100 px-4 py-10">
        <EmptyState title="Store unavailable" message={error} />
      </main>
    );
  }

  if (!storefront) {
    return null;
  }

  const canCheckout = selectedItems.length > 0 && termsAccepted && !isCheckingOut;

  return (
    <main className="min-h-screen bg-zinc-100 text-zinc-950">
      <header className="border-b border-zinc-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-5 sm:flex-row sm:items-center sm:justify-between lg:px-8">
          <div>
            <p className="text-sm font-medium text-brand-700">B2B Magic Storefront</p>
            <h1 className="mt-1 text-2xl font-semibold tracking-normal">{storefront.customer_name}</h1>
          </div>
          <div className="rounded-md border border-zinc-200 bg-zinc-50 px-4 py-3">
            <p className="text-xs font-medium uppercase text-zinc-500">Advance discount</p>
            <p className="text-xl font-semibold text-brand-700">{formatNumber(discountPct, 2)}%</p>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-7xl gap-6 px-4 py-6 lg:grid-cols-[1fr_380px] lg:px-8">
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Available finished goods</h2>
            <p className="text-sm text-zinc-500">{storefront.products.length} products</p>
          </div>

          {storefront.products.length === 0 ? (
            <EmptyState title="No stock available" message="Finished goods will appear here once stock is available." />
          ) : (
            <div className="grid gap-3">
              {storefront.products.map((product) => {
                const quantity = quantities[product.product_id] ?? 0;
                return (
                  <article
                    className="rounded-md border border-zinc-200 bg-white p-4 shadow-sm"
                    key={product.product_id}
                  >
                    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                      <div className="flex items-start gap-3">
                        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-zinc-100 text-zinc-700">
                          <Package className="h-5 w-5" />
                        </div>
                        <div>
                          <h3 className="font-semibold">{product.packaging_profile_name}</h3>
                          <p className="mt-1 text-sm text-zinc-500">
                            {product.cup_size_ml}ml · {formatNumber(product.boxes_available)} boxes available
                          </p>
                        </div>
                      </div>

                      <div className="flex flex-col gap-3 sm:items-end">
                        <p className="text-lg font-semibold">{formatStoreCurrency(product.base_price)}</p>
                        <div className="flex h-10 w-32 items-center justify-between rounded-md border border-zinc-200 bg-zinc-50 p-1">
                          <button
                            aria-label={`Reduce ${product.packaging_profile_name}`}
                            className="grid h-8 w-8 place-items-center rounded-md text-zinc-600 hover:bg-white disabled:text-zinc-300"
                            disabled={quantity === 0}
                            onClick={() => updateQuantity(product, quantity - 1)}
                            title="Reduce quantity"
                            type="button"
                          >
                            <Minus className="h-4 w-4" />
                          </button>
                          <span className="w-10 text-center text-sm font-semibold">{quantity}</span>
                          <button
                            aria-label={`Add ${product.packaging_profile_name}`}
                            className="grid h-8 w-8 place-items-center rounded-md text-zinc-600 hover:bg-white disabled:text-zinc-300"
                            disabled={quantity >= product.boxes_available}
                            onClick={() => updateQuantity(product, quantity + 1)}
                            title="Add quantity"
                            type="button"
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
          )}
        </section>

        <aside className="space-y-4">
          <section className="rounded-md border border-zinc-200 bg-white p-4 shadow-sm">
            <h2 className="text-lg font-semibold">Payment option</h2>
            <div className="mt-4 grid gap-3">
              {paymentOptions.map((option) => {
                const isSelected = option.method === paymentMethod;
                const Icon = option.icon;
                return (
                  <button
                    className={[
                      "rounded-md border p-4 text-left transition",
                      isSelected ? "ring-2 ring-brand-500" : "hover:border-zinc-300",
                      option.tone
                    ].join(" ")}
                    key={option.method}
                    onClick={() => setPaymentMethod(option.method)}
                    type="button"
                  >
                    <span className="flex items-start gap-3">
                      <span
                        className={[
                          "mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full border",
                          isSelected ? "border-brand-600 bg-brand-600 text-white" : "border-zinc-300 bg-white"
                        ].join(" ")}
                      >
                        {isSelected ? <Check className="h-3 w-3" /> : null}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-2 text-sm font-semibold">
                          <Icon className="h-4 w-4 shrink-0" />
                          {getPaymentLabel(option.method, discountPct)}
                        </span>
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>

            {paymentMethod === "Full_Advance_Doorstep" ? (
              <div className="mt-4 flex gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm font-semibold text-red-700">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <p>Note: If full payment is not made at delivery, the discount will be cancelled and standard rates will apply.</p>
              </div>
            ) : null}
          </section>

          <section className="rounded-md border border-zinc-200 bg-white p-4 shadow-sm">
            <h2 className="text-lg font-semibold">Cart total</h2>
            <div className="mt-4 space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-zinc-500">Standard total</span>
                <span className="font-medium">{formatStoreCurrency(baseTotal)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className={isDiscounted ? "text-emerald-700" : "text-zinc-500"}>Discount</span>
                <span className={isDiscounted ? "font-semibold text-emerald-700" : "font-medium text-zinc-500"}>
                  -{formatStoreCurrency(discountAmount)}
                </span>
              </div>
              <div className="border-t border-zinc-200 pt-3">
                <div className="flex items-center justify-between">
                  <span className="font-semibold">Payable total</span>
                  <span className="text-2xl font-semibold">{formatStoreCurrency(cartTotal)}</span>
                </div>
              </div>
            </div>

            <label className="mt-5 flex items-start gap-3 rounded-md border border-zinc-200 bg-zinc-50 p-3 text-sm">
              <input
                checked={termsAccepted}
                className="mt-1 h-4 w-4 rounded border-zinc-300 text-brand-600 focus:ring-brand-500"
                onChange={(event) => setTermsAccepted(event.target.checked)}
                type="checkbox"
              />
              <span className="text-zinc-700">{storefront.terms_and_conditions}</span>
            </label>

            {error ? <p className="mt-3 text-sm font-medium text-red-600">{error}</p> : null}

            <button
              className="mt-5 flex h-11 w-full items-center justify-center rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-zinc-300"
              disabled={!canCheckout}
              onClick={checkout}
              type="button"
            >
              {isCheckingOut ? "Placing order..." : "Place order"}
            </button>
          </section>
        </aside>
      </div>
    </main>
  );
}
