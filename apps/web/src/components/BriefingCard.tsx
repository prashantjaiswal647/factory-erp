import { AlertTriangle, Sunrise, Sparkles, ChevronDown, ChevronUp, CheckCircle2 } from "lucide-react";
import { useEffect, useState } from "react";

import { getMorningBriefing } from "../lib/api";
import type { MorningBriefingResponse } from "../lib/api";


export default function BriefingCard() {
  const [briefing, setBriefing] = useState<MorningBriefingResponse | null>(null);
  const [error, setError] = useState("");
  const [showObs, setShowObs] = useState(false);

  useEffect(() => {
    void getMorningBriefing()
      .then(setBriefing)
      .catch(() => setError("Morning briefing is not available right now."));
  }, []);

  return (
    <>
      <section className="rounded-xl border border-brand-200 bg-brand-50 p-4 shadow-sm" aria-label="Morning briefing">
        <div className="flex items-start gap-3">
          <Sunrise className="mt-0.5 h-5 w-5 shrink-0 text-brand-700" />
          <div className="min-w-0 flex-1">
            <h2 className="text-sm font-bold text-zinc-950">Morning Briefing</h2>
            <p className="text-xs text-zinc-600">Deterministic snapshot from yesterday&apos;s factory records.</p>
            {error ? <p className="mt-3 text-sm font-medium text-red-700">{error}</p> : null}
            {!error && !briefing ? <p className="mt-3 text-sm text-zinc-500">Loading briefing...</p> : null}
            {briefing ? (
              <>
                <pre className="mt-3 whitespace-pre-wrap font-sans text-sm leading-6 text-zinc-800">{briefing.message_text}</pre>
                {briefing.missing_data.length ? (
                  <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>Missing data: {briefing.missing_data.join(", ")}</span>
                  </div>
                ) : null}
              </>
            ) : null}
          </div>
        </div>
      </section>

      {briefing?.ai_explanation ? (
        <section className="mt-3 rounded-xl border border-indigo-100 bg-gradient-to-br from-indigo-50/60 to-violet-50/60 p-5 shadow-sm transition-all duration-300 hover:shadow-md" aria-label="AI Insight">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-indigo-100 p-2 text-indigo-700">
              <Sparkles className="h-5 w-5" />
            </div>
            <div className="min-w-0 flex-1">
              <h2 className="text-sm font-bold text-zinc-950 flex items-center gap-1.5">
                ✨ Munshi AI Insight
              </h2>
              <p className="text-xs text-zinc-500">AI-generated explanations and actionable steps for your factory.</p>
              
              <div className="mt-4 space-y-3">
                {briefing.ai_explanation.cost_explanation && (
                  <div>
                    <h3 className="text-xs font-bold text-indigo-950">Cost Analysis</h3>
                    <p className="text-xs text-zinc-700 mt-0.5 leading-relaxed">{briefing.ai_explanation.cost_explanation}</p>
                  </div>
                )}
                
                {briefing.ai_explanation.health_explanation && (
                  <div>
                    <h3 className="text-xs font-bold text-indigo-950">Factory Health</h3>
                    <p className="text-xs text-zinc-700 mt-0.5 leading-relaxed">{briefing.ai_explanation.health_explanation}</p>
                  </div>
                )}
                
                {briefing.ai_explanation.wastage_explanation && (
                  <div>
                    <h3 className="text-xs font-bold text-indigo-950">Wastage Audit</h3>
                    <p className="text-xs text-zinc-700 mt-0.5 leading-relaxed">{briefing.ai_explanation.wastage_explanation}</p>
                  </div>
                )}
                
                {briefing.ai_explanation.profit_explanation && (
                  <div>
                    <h3 className="text-xs font-bold text-indigo-950">Profitability</h3>
                    <p className="text-xs text-zinc-700 mt-0.5 leading-relaxed">{briefing.ai_explanation.profit_explanation}</p>
                  </div>
                )}
                
                {briefing.ai_explanation.per_size_explanation && (
                  <div>
                    <h3 className="text-xs font-bold text-indigo-950">Size Performance</h3>
                    <p className="text-xs text-zinc-700 mt-0.5 leading-relaxed">{briefing.ai_explanation.per_size_explanation}</p>
                  </div>
                )}
              </div>
              
              {briefing.ai_explanation.action_items && briefing.ai_explanation.action_items.length > 0 && (
                <div className="mt-4 pt-4 border-t border-indigo-100/50">
                  <h3 className="text-xs font-bold text-indigo-950 flex items-center gap-1.5">
                    <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
                    Recommended Actions
                  </h3>
                  <ul className="mt-2 space-y-1.5">
                    {briefing.ai_explanation.action_items.slice(0, 3).map((item, idx) => (
                      <li key={idx} className="text-xs text-zinc-700 flex items-start gap-2">
                        <span className="font-bold text-indigo-600 shrink-0">{idx + 1}.</span>
                        <span className="leading-relaxed">{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              
              {briefing.ai_observability && (
                <div className="mt-4 pt-3 border-t border-indigo-100/30">
                  <button
                    onClick={() => setShowObs(!showObs)}
                    className="inline-flex items-center gap-1 text-[11px] font-semibold text-indigo-700 hover:text-indigo-800 focus:outline-none"
                  >
                    {showObs ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                    AI Observability Metrics
                  </button>
                  {showObs && (
                    <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-2 rounded-lg bg-zinc-900/5 p-3 text-[10px] font-medium text-zinc-600">
                      <div><span className="font-semibold">Model Name:</span> {briefing.ai_observability.model_name || "N/A"}</div>
                      <div><span className="font-semibold">Cache Status:</span> {briefing.ai_observability.cache_hit ? "HIT (No LLM Cost)" : "MISS"}</div>
                      <div><span className="font-semibold">Generation Time:</span> {briefing.ai_observability.generation_time}s</div>
                      <div><span className="font-semibold">Token Usage:</span> {briefing.ai_observability.token_usage}</div>
                      {briefing.ai_observability.fallback_reason && (
                        <div className="col-span-2 text-red-600"><span className="font-semibold">Fallback Reason:</span> {briefing.ai_observability.fallback_reason}</div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </section>
      ) : null}
    </>
  );
}
