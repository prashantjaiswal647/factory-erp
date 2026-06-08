import { AlertCircle, CheckCircle2, ExternalLink, Loader2, Send, Unplug } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  createTelegramConnectLink,
  disconnectTelegramIntegration,
  getTelegramConnectionStatus,
  sendTelegramTestMessage,
} from "../lib/api";
import type { TelegramConnectionStatus } from "../lib/api";

type ViewState = "loading" | "idle" | "connecting" | "connected" | "error";

export default function Integrations() {
  const [status, setStatus] = useState<TelegramConnectionStatus | null>(null);
  const [viewState, setViewState] = useState<ViewState>("loading");
  const [message, setMessage] = useState("");
  const [isActionLoading, setIsActionLoading] = useState(false);
  const pollTimer = useRef<number | null>(null);
  const pollDeadline = useRef(0);

  useEffect(() => {
    void refreshStatus();
    return stopPolling;
  }, []);

  function stopPolling() {
    if (pollTimer.current !== null) {
      window.clearTimeout(pollTimer.current);
      pollTimer.current = null;
    }
  }

  async function refreshStatus() {
    try {
      const response = await getTelegramConnectionStatus();
      setStatus(response.data);
      setViewState(response.data.connected ? "connected" : "idle");
      return response.data;
    } catch {
      setViewState("error");
      setMessage("Telegram status load nahi ho paya. Dobara try karein.");
      return null;
    }
  }

  function scheduleStatusPoll() {
    stopPolling();
    const poll = async () => {
      const nextStatus = await getTelegramConnectionStatus()
        .then((response) => response.data)
        .catch(() => null);
      if (nextStatus?.connected) {
        setStatus(nextStatus);
        setViewState("connected");
        setMessage("Telegram successfully connect ho gaya.");
        stopPolling();
        return;
      }
      if (Date.now() >= pollDeadline.current) {
        setViewState("idle");
        setMessage("Telegram me Start dabane ke baad status update ho jayega.");
        stopPolling();
        return;
      }
      pollTimer.current = window.setTimeout(poll, 3000);
    };
    pollTimer.current = window.setTimeout(poll, 3000);
  }

  async function handleConnect() {
    setViewState("connecting");
    setMessage("Secure Telegram link generate ho raha hai...");
    try {
      const response = await createTelegramConnectLink();
      const popup = window.open(response.data.telegram_url, "_blank", "noopener,noreferrer");
      if (!popup) window.location.assign(response.data.telegram_url);
      pollDeadline.current = Date.now() + 60_000;
      scheduleStatusPoll();
    } catch {
      setViewState("error");
      setMessage("Telegram connect nahi ho paya. Dobara try karein.");
    }
  }

  async function handleTestMessage() {
    setIsActionLoading(true);
    setMessage("");
    try {
      await sendTelegramTestMessage();
      setMessage("Test message Telegram par bhej diya gaya.");
      await refreshStatus();
    } catch {
      setMessage("Test message send nahi ho paya. Dobara try karein.");
    } finally {
      setIsActionLoading(false);
    }
  }

  async function handleDisconnect() {
    setIsActionLoading(true);
    setMessage("");
    try {
      await disconnectTelegramIntegration();
      stopPolling();
      setStatus(null);
      setViewState("idle");
      setMessage("Telegram disconnect ho gaya.");
    } catch {
      setMessage("Telegram disconnect nahi ho paya.");
    } finally {
      setIsActionLoading(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6 overflow-x-hidden">
      <header>
        <h1 className="text-2xl font-semibold text-zinc-950">Integrations</h1>
        <p className="mt-1 text-sm text-zinc-500">Factory alerts aur daily briefing channels manage karein.</p>
      </header>

      <section className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm sm:p-6">
        <div className="flex min-w-0 flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex min-w-0 gap-3">
            <div className="grid h-11 w-11 shrink-0 place-items-center rounded-lg bg-sky-50 text-sky-600">
              <Send className="h-5 w-5" aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <h2 className="text-lg font-semibold text-zinc-950">Telegram Integration</h2>
              <p className="mt-1 max-w-xl text-sm leading-6 text-zinc-500">
                Daily morning briefing aur important alerts directly Telegram par receive karein.
              </p>
            </div>
          </div>
          <ConnectionBadge state={viewState} />
        </div>

        {viewState === "loading" || viewState === "connecting" ? (
          <div className="mt-6 flex items-center gap-3 rounded-lg bg-zinc-50 px-4 py-4 text-sm font-medium text-zinc-700">
            <Loader2 className="h-5 w-5 animate-spin text-sky-600" />
            {viewState === "connecting" ? "Secure Telegram link generate ho raha hai..." : "Telegram status load ho raha hai..."}
          </div>
        ) : null}

        {viewState === "connected" ? (
          <div className="mt-6 grid gap-3 sm:grid-cols-2">
            <Info label="Telegram Account" value={status?.telegram_username ? `@${status.telegram_username}` : "Connected account"} />
            <Info label="Chat ID" value={status?.chat_id_verified ? "Verified" : "-"} />
            <Info label="Last message" value={formatDateTime(status?.last_message_at)} />
            <Info label="Last test status" value={status?.last_message_status || "-"} />
          </div>
        ) : null}

        {message ? (
          <p className={`mt-4 text-sm font-medium ${viewState === "error" ? "text-red-700" : "text-zinc-600"}`}>
            {message}
          </p>
        ) : null}

        <div className="mt-6 flex flex-col gap-3 sm:flex-row">
          {viewState === "idle" || viewState === "error" ? (
            <button
              className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-sky-600 px-4 text-sm font-semibold text-white hover:bg-sky-700"
              type="button"
              onClick={handleConnect}
            >
              <ExternalLink className="h-4 w-4" />
              {viewState === "error" ? "Retry" : "Connect Telegram"}
            </button>
          ) : null}
          {viewState === "connected" ? (
            <>
              <button
                className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-sky-600 px-4 text-sm font-semibold text-white hover:bg-sky-700 disabled:opacity-60"
                type="button"
                disabled={isActionLoading}
                onClick={handleTestMessage}
              >
                {isActionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                Send Test Message
              </button>
              <button
                className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-red-200 px-4 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-60"
                type="button"
                disabled={isActionLoading}
                onClick={handleDisconnect}
              >
                <Unplug className="h-4 w-4" />
                Disconnect
              </button>
            </>
          ) : null}
        </div>
      </section>
    </div>
  );
}

function ConnectionBadge({ state }: { state: ViewState }) {
  if (state === "connected") {
    return (
      <span className="inline-flex w-fit items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
        <CheckCircle2 className="h-4 w-4" /> Telegram Connected
      </span>
    );
  }
  if (state === "error") {
    return (
      <span className="inline-flex w-fit items-center gap-1.5 rounded-full bg-red-50 px-3 py-1 text-xs font-semibold text-red-700">
        <AlertCircle className="h-4 w-4" /> Connection Error
      </span>
    );
  }
  return <span className="inline-flex w-fit rounded-full bg-zinc-100 px-3 py-1 text-xs font-semibold text-zinc-600">Not Connected</span>;
}

function Info({ label, value }: { label: string; value: string }) {
  return <div className="min-w-0 rounded-lg bg-zinc-50 px-4 py-3"><p className="text-xs font-medium text-zinc-500">{label}</p><p className="mt-1 break-words text-sm font-semibold text-zinc-900">{value || "-"}</p></div>;
}

function formatDateTime(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "-" : date.toLocaleString("en-IN");
}
