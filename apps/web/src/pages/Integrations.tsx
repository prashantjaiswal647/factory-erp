import { Bot, CheckCircle2, KeyRound, Loader2, Send } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

import { getTelegramIntegration, saveTelegramIntegration } from "../lib/api";

export default function Integrations() {
  const [telegramToken, setTelegramToken] = useState("");
  const [isConfigured, setIsConfigured] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    getTelegramIntegration()
      .then((response) => {
        if (!isMounted) return;
        setTelegramToken(response.data.telegram_bot_token || "");
        setIsConfigured(response.data.is_configured);
      })
      .catch(() => {
        if (!isMounted) return;
        setError("Could not load Telegram settings.");
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSaving(true);
    setMessage(null);
    setError(null);

    try {
      const response = await saveTelegramIntegration({ telegram_bot_token: telegramToken });
      setTelegramToken(response.data.telegram_bot_token || "");
      setIsConfigured(response.data.is_configured);
      setMessage(response.data.is_configured ? "Telegram bot token saved." : "Telegram bot token removed.");
    } catch {
      setError("Could not save Telegram settings.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold text-zinc-950">Integrations</h1>
        <p className="mt-1 text-sm text-zinc-500">Connect factory communication channels and automation tools.</p>
      </header>

      <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <form className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm sm:p-6" onSubmit={handleSubmit}>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex min-w-0 gap-3">
              <div className="grid h-11 w-11 shrink-0 place-items-center rounded-md bg-sky-50 text-sky-700">
                <Send className="h-5 w-5" aria-hidden="true" />
              </div>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-lg font-semibold text-zinc-950">Telegram Integration</h2>
                  {isConfigured ? (
                    <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700">
                      <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                      Active
                    </span>
                  ) : null}
                </div>
                <p className="mt-1 text-sm text-zinc-500">Get your token from @BotFather on Telegram.</p>
              </div>
            </div>
          </div>

          <div className="mt-6 space-y-2">
            <label className="text-sm font-medium text-zinc-700" htmlFor="telegram-token">
              Bot Token
            </label>
            <div className="relative">
              <KeyRound className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
              <input
                id="telegram-token"
                className="h-11 w-full rounded-md border border-zinc-200 bg-zinc-50 pl-9 pr-3 text-sm outline-none transition placeholder:text-zinc-400 focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-100"
                placeholder="1234567890:AA..."
                type="password"
                value={telegramToken}
                onChange={(event) => setTelegramToken(event.target.value)}
                disabled={isLoading || isSaving}
              />
            </div>
          </div>

          {message ? <p className="mt-4 text-sm font-medium text-emerald-700">{message}</p> : null}
          {error ? <p className="mt-4 text-sm font-medium text-red-600">{error}</p> : null}

          <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-end">
            <button
              className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
              type="submit"
              disabled={isLoading || isSaving}
            >
              {isSaving ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Bot className="h-4 w-4" aria-hidden="true" />}
              Save & Activate
            </button>
          </div>
        </form>

        <aside className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm sm:p-6">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">Webhook Flow</h3>
          <div className="mt-4 space-y-3 text-sm text-zinc-600">
            <p>Telegram messages can be routed through n8n to the backend AI endpoint.</p>
            <div className="rounded-md bg-zinc-50 p-3 font-mono text-xs text-zinc-700">POST /api/ai/n8n-webhook</div>
            <p>The backend uses the factory ID to load tenant-specific ERP context before asking Groq for a supervisor reply.</p>
          </div>
        </aside>
      </section>
    </div>
  );
}
