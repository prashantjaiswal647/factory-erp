import { CalendarRange } from "lucide-react";
import { useEffect, useState } from "react";

import { getLatestWeeklyDigest, type WeeklyDigestResponse } from "../lib/api";

const formatNumber = (value: number | undefined | null) => {
  if (value == null) return "0";
  return Number(value).toLocaleString("en-IN");
};

export default function WeeklyDigestCard() {
  const [digest, setDigest] = useState<WeeklyDigestResponse | null>(null);

  useEffect(() => {
    void getLatestWeeklyDigest().then(setDigest).catch(() => setDigest(null));
  }, []);

  if (!digest) return null;

  const rev = digest.revenue != null ? Number(digest.revenue) : 0;
  const prof = digest.profit != null ? Number(digest.profit) : 0;
  const marg = digest.margin;
  const hscore = digest.health_score;

  const metrics = [
    ["Revenue", `₹${formatNumber(rev)}`],
    ["Profit", `₹${formatNumber(prof)}`],
    ["Margin", marg == null ? "Not available" : `${Number(marg).toFixed(1)}%`],
    ["Health", hscore == null ? "Not available" : `${Number(hscore)}/100`],
    ["Best Day", digest.best_day || "N/A"],
    ["Worst Day", digest.worst_day || "N/A"],
  ];

  return (
    <section className="rounded-xl border border-indigo-200 bg-indigo-50 p-4 shadow-sm" aria-label="Weekly profit digest">
      <div className="flex items-start gap-3">
        <CalendarRange className="mt-0.5 h-5 w-5 shrink-0 text-indigo-700" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-sm font-bold text-zinc-950">Weekly Factory Review</h2>
              <p className="text-xs text-zinc-600">{digest.week_start || "N/A"} to {digest.week_end || "N/A"}</p>
            </div>
            <span className="rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-indigo-700">{digest.days_available || 0}/7 days</span>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            {metrics.map(([label, value]) => (
              <div key={label} className="rounded-md bg-white px-2.5 py-2">
                <p className="text-[10px] font-semibold text-zinc-500">{label}</p>
                <p className="mt-1 truncate text-sm font-bold text-zinc-900">{value}</p>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-zinc-700"><span className="font-semibold">Largest Risk:</span> {digest.largest_risk || "None"}</p>
        </div>
      </div>
    </section>
  );
}

