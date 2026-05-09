import { CheckCircle2, Landmark, QrCode, ShoppingBag } from "lucide-react";
import { Link, useLocation, useParams } from "react-router-dom";

import { asNumber } from "../lib/format";

type CheckoutResult = {
  message: string;
  order_id: number;
  payment_method: "Normal_Credit" | "Full_Advance_UPI" | "Full_Advance_Doorstep";
  discount_amount: string;
  total_amount: string;
  upi_payment_details?: {
    bank_name: string;
    account_name: string;
    account_number: string;
    ifsc: string;
    upi_id: string;
  } | null;
};

const qrPlaceholder =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='220' height='220' viewBox='0 0 220 220'%3E%3Crect width='220' height='220' fill='white'/%3E%3Cg fill='%23171717'%3E%3Cpath d='M20 20h60v60H20zM35 35v30h30V35zM140 20h60v60h-60zM155 35v30h30V35zM20 140h60v60H20zM35 155v30h30v-30zM100 20h20v20h-20zM100 60h20v20h-20zM120 40h20v20h-20zM100 100h20v20h-20zM140 100h20v20h-20zM180 100h20v20h-20zM120 120h20v20h-20zM160 120h20v20h-20zM100 160h20v40h-20zM120 140h40v20h-40zM160 160h40v20h-40zM140 180h20v20h-20zM180 180h20v20h-20z'/%3E%3C/g%3E%3Ctext x='110' y='113' text-anchor='middle' font-family='Arial' font-size='11' fill='%231f9d8a'%3EUPI DEMO%3C/text%3E%3C/svg%3E";

function formatStoreCurrency(value: number | string | null | undefined) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(asNumber(value));
}

export default function StorefrontSuccessPage() {
  const { storeToken } = useParams();
  const location = useLocation();
  const result = location.state as CheckoutResult | null;

  if (!result) {
    return (
      <main className="min-h-screen bg-zinc-100 px-4 py-10 text-zinc-950">
        <section className="mx-auto max-w-xl rounded-md border border-zinc-200 bg-white p-6 text-center shadow-sm">
          <ShoppingBag className="mx-auto h-10 w-10 text-zinc-500" />
          <h1 className="mt-4 text-xl font-semibold">Order details unavailable</h1>
          <p className="mt-2 text-sm text-zinc-600">Open your store link and place the order again if needed.</p>
          <Link
            className="mt-5 inline-flex h-10 items-center rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700"
            to={storeToken ? `/store/${storeToken}` : "/"}
          >
            Back to store
          </Link>
        </section>
      </main>
    );
  }

  const isUpi = result.payment_method === "Full_Advance_UPI";

  return (
    <main className="min-h-screen bg-zinc-100 px-4 py-8 text-zinc-950">
      <section className="mx-auto max-w-5xl">
        <div className="rounded-md border border-zinc-200 bg-white p-6 shadow-sm">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              <div className="grid h-11 w-11 place-items-center rounded-md bg-emerald-50 text-emerald-700">
                <CheckCircle2 className="h-6 w-6" />
              </div>
              <div>
                <h1 className="text-2xl font-semibold tracking-normal">Order confirmed</h1>
                <p className="mt-1 text-sm text-zinc-600">Order #{result.order_id} is pending factory approval.</p>
              </div>
            </div>
            <div className="rounded-md bg-zinc-50 px-4 py-3 text-right">
              <p className="text-xs font-medium uppercase text-zinc-500">Payable amount</p>
              <p className="text-2xl font-semibold">{formatStoreCurrency(result.total_amount)}</p>
            </div>
          </div>

          {isUpi ? (
            <div className="mt-6 grid gap-6 lg:grid-cols-[260px_1fr]">
              <div className="rounded-md border border-zinc-200 bg-zinc-50 p-5 text-center">
                <img
                  alt="Dummy UPI QR code"
                  className="mx-auto h-56 w-56 rounded-md border border-zinc-200 bg-white p-3"
                  src={qrPlaceholder}
                />
                <p className="mt-3 text-sm font-medium text-zinc-700">Scan to pay</p>
              </div>

              <div className="rounded-md border border-zinc-200 p-5">
                <div className="flex items-center gap-2">
                  <Landmark className="h-5 w-5 text-brand-700" />
                  <h2 className="text-lg font-semibold">Bank account details</h2>
                </div>
                <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="text-zinc-500">Bank</dt>
                    <dd className="font-medium">{result.upi_payment_details?.bank_name}</dd>
                  </div>
                  <div>
                    <dt className="text-zinc-500">Account name</dt>
                    <dd className="font-medium">{result.upi_payment_details?.account_name}</dd>
                  </div>
                  <div>
                    <dt className="text-zinc-500">Account number</dt>
                    <dd className="font-medium">{result.upi_payment_details?.account_number}</dd>
                  </div>
                  <div>
                    <dt className="text-zinc-500">IFSC</dt>
                    <dd className="font-medium">{result.upi_payment_details?.ifsc}</dd>
                  </div>
                  <div className="sm:col-span-2">
                    <dt className="text-zinc-500">UPI ID</dt>
                    <dd className="font-medium">{result.upi_payment_details?.upi_id}</dd>
                  </div>
                </dl>
              </div>
            </div>
          ) : (
            <div className="mt-6 rounded-md border border-emerald-200 bg-emerald-50 p-5">
              <div className="flex items-center gap-2 text-emerald-800">
                <QrCode className="h-5 w-5" />
                <h2 className="text-lg font-semibold">Standard order confirmed</h2>
              </div>
              <p className="mt-2 text-sm text-emerald-900">
                The factory team will review this order and confirm dispatch/payment terms.
              </p>
            </div>
          )}

          <div className="mt-6 flex justify-end">
            <Link
              className="inline-flex h-10 items-center rounded-md border border-zinc-200 bg-white px-4 text-sm font-semibold text-zinc-700 hover:bg-zinc-50"
              to={storeToken ? `/store/${storeToken}` : "/"}
            >
              Back to store
            </Link>
          </div>
        </div>
      </section>
    </main>
  );
}
