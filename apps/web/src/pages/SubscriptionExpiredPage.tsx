import { LockKeyhole } from "lucide-react";

export default function SubscriptionExpiredPage() {
  return (
    <div className="mx-auto max-w-xl rounded-lg border border-amber-200 bg-amber-50 p-8 text-center">
      <div className="mx-auto grid h-14 w-14 place-items-center rounded-md bg-amber-100 text-amber-700">
        <LockKeyhole className="h-7 w-7" />
      </div>
      <h1 className="mt-5 text-2xl font-semibold text-amber-950">Factory Subscription Expired</h1>
      <p className="mt-2 text-sm leading-6 text-amber-800">
        Is factory ka Munshi AI plan expire ho gaya hai. Access restore karne ke liye owner se renewal karwane ko bolein.
      </p>
    </div>
  );
}
