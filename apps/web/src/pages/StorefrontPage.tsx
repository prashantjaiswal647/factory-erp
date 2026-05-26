import { Lock, Minus, Package, Plus, ShoppingCart } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import LoadingState from "../components/LoadingState";
import { api, verifyStorefrontCustomer } from "../lib/api";
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
  const [paymentMethod, setPaymentMethod] = useState<"Normal_Credit" | "Full_Advance_UPI">("Normal_Credit");
  const [showUpiModal, setShowUpiModal] = useState(false);
  const [utrValue, setUtrValue] = useState("");
  const [isVerified, setIsVerified] = useState(() => {
    return sessionStorage.getItem(`distributor_verified_${storeToken}`) === "true";
  });
  const [phoneGateVal, setPhoneGateVal] = useState("");
  const [isVerifying, setIsVerifying] = useState(false);
  const [gateError, setGateError] = useState<string | null>(null);

  async function verifyPhoneGate(e: React.FormEvent) {
    e.preventDefault();
    if (!storeToken || !phoneGateVal.trim()) {
      setGateError("Please enter a valid mobile number.");
      return;
    }
    setIsVerifying(true);
    setGateError(null);
    try {
      const response = await verifyStorefrontCustomer(storeToken, phoneGateVal.trim());
      if (response.data.status === "success") {
        sessionStorage.setItem(`distributor_verified_${storeToken}`, "true");
        setIsVerified(true);
      } else {
        setGateError("Verification failed. Please double check your number.");
      }
    } catch (caught: any) {
      if (caught.response?.data?.detail) {
        setGateError(caught.response.data.detail);
      } else {
        setGateError("Distributor verification failed. Mobile number not registered.");
      }
    } finally {
      setIsVerifying(false);
    }
  }

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

    if (paymentMethod === "Full_Advance_UPI") {
      setShowUpiModal(true);
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
      navigate(`/storefront/${storeToken}/success`, { state: { ...response.data, payment_method: "Normal_Credit" } });
    } catch {
      setError("Order could not be placed. Please reduce quantity or contact the factory.");
    } finally {
      setIsOrdering(false);
    }
  }

  async function executeUpiOrder() {
    if (!storeToken || selectedItems.length === 0 || !utrValue.trim()) {
      alert("Please enter a valid Transaction UTR reference number.");
      return;
    }

    setIsOrdering(true);
    setError(null);
    try {
      const response = await api.post<CheckoutResponse>(`/api/storefront/${storeToken}/order`, {
        payment_method: "Full_Advance_UPI",
        terms_accepted: true,
        utr_transaction_id: utrValue.trim(),
        items: selectedItems.map((item) => ({
          product_id: item.product_id,
          quantity: item.quantity
        }))
      });
      setShowUpiModal(false);
      navigate(`/storefront/${storeToken}/success`, { 
        state: { 
          ...response.data, 
          payment_method: "Full_Advance_UPI",
          upi_payment_details: {
            bank_name: "HDFC Bank Ltd",
            account_name: "Cosmic Yog Enterprise",
            account_number: "50200087654321",
            ifsc: "HDFC0001234",
            upi_id: "cosmicyog@ybl"
          }
        } 
      });
    } catch {
      setError("Order checkout failed under UPI advance. Please try later or use Credit checkout.");
      setShowUpiModal(false);
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

  if (!isVerified) {
    return (
      <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-zinc-950 px-4">
        <div className="absolute top-1/4 left-1/4 h-72 w-72 rounded-full bg-brand-500/10 blur-[80px]" />
        <div className="absolute bottom-1/4 right-1/4 h-80 w-80 rounded-full bg-purple-500/10 blur-[100px]" />
        <section className="relative w-full max-w-md overflow-hidden rounded-2xl border border-white/10 bg-white/5 p-8 text-center backdrop-blur-xl shadow-2xl transition-all duration-300">
          <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-xl bg-brand-500/10 text-brand-400 border border-brand-500/20 shadow-[0_0_20px_rgba(99,102,241,0.15)]">
            <Lock className="h-6 w-6 animate-pulse" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white">B2B Private Store Login</h1>
          <p className="mt-2 text-sm text-zinc-400">
            For factory security and verified trade, enter your registered customer mobile number to enter the ordering portal.
          </p>
          <form onSubmit={verifyPhoneGate} className="mt-8 space-y-4 text-left">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-zinc-300 mb-2">
                Registered Mobile Number
              </label>
              <input
                type="tel"
                placeholder="e.g. +91 98765 43210"
                value={phoneGateVal}
                onChange={(e) => setPhoneGateVal(e.target.value)}
                required
                className="h-12 w-full rounded-lg border border-white/10 bg-white/5 px-4 text-sm font-medium text-white placeholder-zinc-500 outline-none transition duration-200 focus:border-brand-500 focus:bg-white/10 focus:ring-4 focus:ring-brand-500/10"
              />
            </div>
            {gateError && (
              <p className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-2.5 text-xs font-medium text-red-400 text-center">
                {gateError}
              </p>
            )}
            <button
              type="submit"
              disabled={isVerifying}
              className="relative flex h-12 w-full items-center justify-center gap-2 overflow-hidden rounded-lg bg-gradient-to-r from-brand-500 to-purple-600 px-4 text-sm font-semibold text-white shadow-lg hover:from-brand-600 hover:to-purple-700 active:scale-[0.98] transition-all disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none"
            >
              {isVerifying ? (
                <span>Securing Connection...</span>
              ) : (
                <span>Verify and Open Portal</span>
              )}
            </button>
          </form>
        </section>
      </main>
    );
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

        <div className="sticky bottom-0 mt-6 border-t border-zinc-200 bg-zinc-50 py-4 space-y-4">
          {/* Payment Method Selector */}
          {selectedItems.length > 0 && (
            <div className="bg-white p-3 rounded-lg border border-zinc-200 space-y-2">
              <p className="text-xs font-semibold text-zinc-600 uppercase tracking-wider">Select Payment Method</p>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setPaymentMethod("Normal_Credit")}
                  className={`p-3 rounded-lg border text-left flex flex-col justify-between transition-all ${
                    paymentMethod === "Normal_Credit" 
                      ? "border-brand-600 bg-brand-50/30 text-brand-900 ring-2 ring-brand-100" 
                      : "border-zinc-200 hover:bg-zinc-50 text-zinc-700"
                  }`}
                >
                  <span className="text-xs font-bold">Normal Credit</span>
                  <span className="text-[10px] text-zinc-500 mt-1">Net-30 post-delivery billing</span>
                </button>
                <button
                  type="button"
                  onClick={() => setPaymentMethod("Full_Advance_UPI")}
                  className={`p-3 rounded-lg border text-left flex flex-col justify-between transition-all ${
                    paymentMethod === "Full_Advance_UPI" 
                      ? "border-brand-600 bg-brand-50/30 text-brand-900 ring-2 ring-brand-100" 
                      : "border-zinc-200 hover:bg-zinc-50 text-zinc-700"
                  }`}
                >
                  <span className="text-xs font-bold text-emerald-700">UPI / QR Advance</span>
                  <span className="text-[10px] text-zinc-500 mt-1">Get {storefront.advance_discount_pct}% instant discount on total</span>
                </button>
              </div>

              {paymentMethod === "Full_Advance_UPI" && (
                <div className="bg-emerald-50 border border-emerald-100 p-2 rounded text-xs font-semibold text-emerald-800 flex justify-between">
                  <span>Advance UPI Discount ({storefront.advance_discount_pct}%):</span>
                  <span>- {formatCurrency(cartTotal * (storefront.advance_discount_pct / 100))}</span>
                </div>
              )}
            </div>
          )}

          <button
            type="button"
            disabled={selectedItems.length === 0 || isOrdering}
            onClick={placeOrder}
            className="flex h-12 w-full items-center justify-center gap-2 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white shadow-sm hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-zinc-300"
          >
            <ShoppingCart className="h-4 w-4" />
            {isOrdering ? "Placing Order..." : paymentMethod === "Full_Advance_UPI" ? "Proceed to UPI Pay" : "Place Order"}
          </button>
        </div>
      </div>

      {showUpiModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-xl border border-zinc-200 bg-white p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-zinc-100 pb-3">
              <h2 className="text-lg font-bold text-zinc-950">UPI Secure Instant Pay</h2>
              <button 
                type="button" 
                onClick={() => setShowUpiModal(false)}
                className="text-zinc-400 hover:text-zinc-600 font-semibold text-lg"
              >
                ✕
              </button>
            </div>

            <div className="text-center bg-zinc-50 p-4 rounded-lg border border-zinc-100">
              <p className="text-xs text-zinc-500 font-medium uppercase">Payable Total (with {storefront.advance_discount_pct}% Disc.)</p>
              <p className="text-2xl font-bold text-zinc-950 mt-1">{formatCurrency(cartTotal * (1 - storefront.advance_discount_pct / 100))}</p>
            </div>

            <div className="flex flex-col items-center py-2">
              <img
                alt="UPI Pay QR"
                className="h-40 w-40 rounded-lg border border-zinc-200 p-2 bg-white"
                src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='220' height='220' viewBox='0 0 220 220'%3E%3Crect width='220' height='220' fill='white'/%3E%3Cg fill='%23171717'%3E%3Cpath d='M20 20h60v60H20zM35 35v30h30V35zM140 20h60v60h-60zM155 35v30h30V35zM20 140h60v60H20zM35 155v30h30v-30zM100 20h20v20h-20zM100 60h20v20h-20zM120 40h20v20h-20zM100 100h20v20h-20zM140 100h20v20h-20zM180 100h20v20h-20zM120 120h20v20h-20zM160 120h20v20h-20zM100 160h20v40h-20zM120 140h40v20h-40zM160 160h40v20h-40zM140 180h20v20h-20zM180 180h20v20h-20z'/%3E%3C/g%3E%3Ctext x='110' y='113' text-anchor='middle' font-family='Arial' font-size='11' fill='%231f9d8a'%3EUPI DEMO%3C/text%3E%3C/svg%3E"
              />
              <p className="text-[10px] text-zinc-500 font-semibold mt-2 text-center">Scan QR code using any UPI App (GPay, PhonePe, Paytm)</p>
            </div>

            <div className="space-y-3">
              <div className="text-xs bg-zinc-50 p-3 rounded-lg border border-zinc-100 space-y-1 text-zinc-600">
                <div className="flex justify-between"><span>VPA ID:</span><span className="font-semibold text-zinc-900">cosmicyog@ybl</span></div>
                <div className="flex justify-between"><span>Account Name:</span><span className="font-semibold text-zinc-900">Cosmic Yog Enterprise</span></div>
                <div className="flex justify-between"><span>Bank:</span><span className="font-semibold text-zinc-900">HDFC Bank Ltd</span></div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-zinc-700 mb-1">
                  Enter UTR / Transaction Reference ID <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g. 432109876543 (12-digit number)"
                  value={utrValue}
                  onChange={(e) => setUtrValue(e.target.value.replace(/\D/g, "").slice(0, 12))}
                  className="h-10 w-full rounded border border-zinc-200 px-3 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 font-medium text-zinc-800"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 border-t border-zinc-100 pt-4">
              <button
                type="button"
                onClick={() => setShowUpiModal(false)}
                className="h-10 w-full rounded border border-zinc-200 text-xs font-semibold text-zinc-700 hover:bg-zinc-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={utrValue.length < 8 || isOrdering}
                onClick={executeUpiOrder}
                className="h-10 w-full rounded bg-emerald-600 hover:bg-emerald-700 disabled:bg-zinc-300 text-xs font-semibold text-white shadow-sm flex items-center justify-center gap-1.5"
              >
                {isOrdering ? "Confirming..." : "Verify & Complete Order"}
              </button>
            </div>
          </div>
        </div>
      )}
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
