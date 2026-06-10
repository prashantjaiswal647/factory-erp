import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import {
  AlertCircle,
  CheckCircle2,
  Clipboard,
  Copy,
  Loader2,
  Send,
  Unplug,
} from "lucide-react";

import {
  createTelegramConnectCode,
  disconnectTelegramIntegration,
  getTelegramConnectionStatus,
  sendTelegramTestMessage,
} from "../lib/api";
import type {
  TelegramConnectionStatus,
  TelegramConnectCode,
} from "../lib/api";
import { useAuth } from "../context/AuthContext";

type ViewState = "loading" | "idle" | "code" | "connected" | "error";

const POLL_INTERVAL_MS = 2_000;
const POLL_DEADLINE_MS = 60_000;
const CODE_TTL_SECONDS = 10 * 60;

function formatRelative(iso?: string | null): string {
  if (!iso) return "-";
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return "-";
  return new Date(ts).toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatRemaining(totalSeconds: number): string {
  const safe = Math.max(0, totalSeconds);
  const m = Math.floor(safe / 60);
  const s = safe % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export default function TelegramConnectCard() {
  const { user } = useAuth();
  const [status, setStatus] = useState<TelegramConnectionStatus | null>(null);
  const [viewState, setViewState] = useState<ViewState>("loading");
  const [code, setCode] = useState<TelegramConnectCode | null>(null);
  const [secondsLeft, setSecondsLeft] = useState(CODE_TTL_SECONDS);
  const [errorMessage, setErrorMessage] = useState("");
  const [infoMessage, setInfoMessage] = useState("");
  const [isActionLoading, setIsActionLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const pollTimer = useRef<number | null>(null);
  const pollDeadline = useRef(0);
  const autoOpenedRef = useRef(false);

  const stopPolling = useCallback(() => {
    if (pollTimer.current !== null) {
      window.clearTimeout(pollTimer.current);
      pollTimer.current = null;
    }
  }, []);

  const refreshStatus = useCallback(async (): Promise<TelegramConnectionStatus | null> => {
    try {
      const response = await getTelegramConnectionStatus();
      const next = response.data;
      setStatus(next);
      setViewState(next.connected ? "connected" : viewState === "code" ? "code" : "idle");
      return next;
    } catch (err) {
      if (viewState === "loading") {
        setViewState("error");
        setErrorMessage("Telegram status load nahi ho paya. Dobara try karein.");
      }
      return null;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void refreshStatus();
    return stopPolling;
  }, [refreshStatus, stopPolling]);

  // Code TTL countdown.
  useEffect(() => {
    if (viewState !== "code" || !code) return;
    const startedAt = Date.now();
    setSecondsLeft(CODE_TTL_SECONDS);
    const tick = window.setInterval(() => {
      const elapsed = Math.floor((Date.now() - startedAt) / 1000);
      const remaining = CODE_TTL_SECONDS - elapsed;
      if (remaining <= 0) {
        window.clearInterval(tick);
        setSecondsLeft(0);
        setErrorMessage("Code expire ho gaya. Naya code generate karein.");
        setViewState("idle");
        setCode(null);
      } else {
        setSecondsLeft(remaining);
      }
    }, 1000);
    return () => window.clearInterval(tick);
  }, [code, viewState]);

  // Status polling while waiting for the user to send the code.
  const scheduleStatusPoll = useCallback(() => {
    stopPolling();
    const tick = async () => {
      const next = await getTelegramConnectionStatus()
        .then((res) => res.data)
        .catch(() => null);
      if (next?.connected) {
        setStatus(next);
        setViewState("connected");
        setInfoMessage("Telegram successfully connect ho gaya.");
        setCode(null);
        stopPolling();
        return;
      }
      if (Date.now() >= pollDeadline.current) {
        setInfoMessage("Telegram me Start dabane ke baad status update ho jayega.");
        stopPolling();
        return;
      }
      pollTimer.current = window.setTimeout(tick, POLL_INTERVAL_MS);
    };
    pollTimer.current = window.setTimeout(tick, POLL_INTERVAL_MS);
  }, [stopPolling]);

  const openTelegramDeepLink = useCallback((deepLink: string) => {
    try {
      const popup = window.open(deepLink, "_blank", "noopener,noreferrer");
      if (!popup) {
        window.location.assign(deepLink);
      }
    } catch {
      window.location.assign(deepLink);
    }
  }, []);

  const handleStart = useCallback(async () => {
    setIsActionLoading(true);
    setErrorMessage("");
    setInfoMessage("");
    setCopied(false);
    try {
      const response = await createTelegramConnectCode();
      const next = response.data;
      setCode(next);
      setViewState("code");
      setSecondsLeft(CODE_TTL_SECONDS);

      // Best-effort clipboard copy so the user can paste if the auto-open
      // fails (e.g. desktop browsers without the t.me handler).
      try {
        if (navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(next.code);
          setCopied(true);
        }
      } catch {
        setCopied(false);
      }

      // Auto-open the deep link once per code.
      if (!autoOpenedRef.current) {
        autoOpenedRef.current = true;
        openTelegramDeepLink(next.deep_link);
      }
      pollDeadline.current = Date.now() + POLL_DEADLINE_MS;
      scheduleStatusPoll();
    } catch (err) {
      setViewState("error");
      setErrorMessage("Telegram connect nahi ho paya. Dobara try karein.");
    } finally {
      setIsActionLoading(false);
    }
  }, [openTelegramDeepLink, scheduleStatusPoll]);

  const handleCopyCode = useCallback(async () => {
    if (!code) return;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(code.code);
        setCopied(true);
        setInfoMessage("Code clipboard par copy ho gaya.");
        window.setTimeout(() => setCopied(false), 2_000);
      } else {
        setInfoMessage("Clipboard supported nahi hai. Code manually type karein.");
      }
    } catch {
      setErrorMessage("Clipboard copy fail ho gaya. Code manually type karein.");
    }
  }, [code]);

  const handleOpenBot = useCallback(() => {
    if (!code) return;
    openTelegramDeepLink(code.deep_link);
  }, [code, openTelegramDeepLink]);

  const handleTestMessage = useCallback(async () => {
    setIsActionLoading(true);
    setErrorMessage("");
    setInfoMessage("");
    try {
      await sendTelegramTestMessage();
      setInfoMessage("Test message Telegram par bhej diya gaya.");
      await refreshStatus();
    } catch (err) {
      const detail = axios.isAxiosError(err)
        ? err.response?.data?.detail || err.message
        : "Test message send nahi ho paya.";
      setErrorMessage(String(detail));
    } finally {
      setIsActionLoading(false);
    }
  }, [refreshStatus]);

  const handleDisconnect = useCallback(async () => {
    if (!window.confirm("Telegram disconnect karna hai? Morning briefing band ho jayegi.")) {
      return;
    }
    setIsActionLoading(true);
    setErrorMessage("");
    setInfoMessage("");
    try {
      await disconnectTelegramIntegration();
      stopPolling();
      autoOpenedRef.current = false;
      setStatus(null);
      setCode(null);
      setViewState("idle");
      setInfoMessage("Telegram disconnect ho gaya.");
    } catch {
      setErrorMessage("Telegram disconnect nahi ho paya.");
    } finally {
      setIsActionLoading(false);
    }
  }, [stopPolling]);

  const connectedDisplay = useMemo(() => {
    if (!status) return null;
    const username = status.telegram_username ? `@${status.telegram_username}` : null;
    const firstName = status.telegram_first_name || null;
    const label = firstName && username
      ? `${firstName} (${username})`
      : firstName || username || "Connected account";
    return {
      label,
      connectedAt: formatRelative(status.connected_at),
      lastMessageAt: formatRelative(status.last_message_at),
      lastStatus: status.last_message_status || "-",
      welcomeSent: Boolean(status.welcome_sent_at),
    };
  }, [status]);

  return (
    <section
      className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm sm:p-6"
      data-testid="telegram-connect-card"
    >
      <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-zinc-950">Telegram Integration</h2>
          <p className="mt-1 max-w-xl text-sm leading-6 text-zinc-500">
            Daily morning briefing aur important alerts directly Telegram par receive karein.
          </p>
        </div>
        <ConnectionBadge state={viewState} />
      </header>

      {viewState === "loading" ? (
        <div className="mt-6 flex items-center gap-3 rounded-lg bg-zinc-50 px-4 py-4 text-sm font-medium text-zinc-700">
          <Loader2 className="h-5 w-5 animate-spin text-sky-600" />
          Telegram status load ho raha hai...
        </div>
      ) : null}

      {viewState === "code" && code ? (
        <div className="mt-6 space-y-4" data-testid="telegram-code-panel">
          <p className="text-sm text-zinc-600">
            1. Neeche ka 6-character code Telegram bot par bhejein.
            <br />
            2. Bot ne aapko welcome message bhej diya hoga. Uske baad status yahan update ho jayega.
          </p>
          <div className="flex flex-col items-center gap-2 rounded-xl border border-sky-200 bg-sky-50 px-4 py-6">
            <span className="text-xs font-semibold uppercase tracking-wider text-sky-700">
              Aapka binding code
            </span>
            <span
              className="font-mono text-3xl font-bold tracking-[0.4em] text-sky-900"
              data-testid="telegram-code"
            >
              {code.code}
            </span>
            <span className="text-xs text-sky-700">
              Code expires in {formatRemaining(secondsLeft)}
            </span>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <button
              className="inline-flex h-10 flex-1 items-center justify-center gap-2 rounded-lg bg-sky-600 px-4 text-sm font-semibold text-white hover:bg-sky-700 disabled:opacity-60"
              disabled={isActionLoading}
              type="button"
              onClick={handleOpenBot}
            >
              <Send className="h-4 w-4" />
              Open Bot
            </button>
            <button
              className="inline-flex h-10 flex-1 items-center justify-center gap-2 rounded-lg border border-zinc-200 bg-white px-4 text-sm font-semibold text-zinc-700 hover:bg-zinc-50 disabled:opacity-60"
              disabled={isActionLoading}
              type="button"
              onClick={handleCopyCode}
            >
              {copied ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : <Copy className="h-4 w-4" />}
              {copied ? "Code copied" : "Copy Code"}
            </button>
          </div>
          <p className="text-xs text-zinc-500">
            Bot: <span className="font-mono">@{code.bot_username}</span>. Agar bot khul nahi raha, upar
            "Open Bot" dabayein ya code manually type karein.
          </p>
        </div>
      ) : null}

      {viewState === "connected" && connectedDisplay ? (
        <div
          className="mt-6 grid gap-3 sm:grid-cols-2"
          data-testid="telegram-connected-panel"
        >
          <Info label="Telegram Account" value={connectedDisplay.label} />
          <Info label="Connected At" value={connectedDisplay.connectedAt} />
          <Info
            label="Welcome Message"
            value={connectedDisplay.welcomeSent ? "Sent" : "Pending"}
          />
          <Info label="Last Delivery" value={connectedDisplay.lastMessageAt} />
          <Info
            label="Last Status"
            value={connectedDisplay.lastStatus}
            tone={connectedDisplay.lastStatus === "failed" ? "red" : "neutral"}
          />
        </div>
      ) : null}

      {errorMessage ? (
        <p className="mt-4 text-sm font-medium text-red-700" role="alert">
          {errorMessage}
        </p>
      ) : null}
      {infoMessage ? (
        <p className="mt-4 text-sm font-medium text-zinc-600">{infoMessage}</p>
      ) : null}

      <div className="mt-6 flex flex-col gap-3 sm:flex-row">
        {viewState === "idle" || viewState === "error" ? (
          <button
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-sky-600 px-4 text-sm font-semibold text-white hover:bg-sky-700 disabled:opacity-60"
            disabled={isActionLoading}
            type="button"
            onClick={handleStart}
            data-testid="telegram-connect-button"
          >
            {isActionLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            {viewState === "error" ? "Retry" : "Connect Telegram"}
          </button>
        ) : null}
        {viewState === "code" ? (
          <button
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-zinc-200 bg-white px-4 text-sm font-semibold text-zinc-700 hover:bg-zinc-50"
            type="button"
            onClick={handleStart}
            disabled={isActionLoading}
          >
            Regenerate Code
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
              {isActionLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
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

      {user?.telegram_chat_id && viewState === "connected" ? (
        <p className="mt-3 text-xs text-zinc-500">
          Chat ID: <span className="font-mono">{user.telegram_chat_id}</span>
        </p>
      ) : null}
    </section>
  );
}

function ConnectionBadge({ state }: { state: ViewState }) {
  if (state === "connected") {
    return (
      <span
        className="inline-flex w-fit items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700"
        data-testid="telegram-badge-connected"
      >
        <CheckCircle2 className="h-4 w-4" /> Telegram Connected
      </span>
    );
  }
  if (state === "code") {
    return (
      <span className="inline-flex w-fit items-center gap-1.5 rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-700">
        <Clipboard className="h-4 w-4" /> Waiting for Bot
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
  return (
    <span className="inline-flex w-fit rounded-full bg-zinc-100 px-3 py-1 text-xs font-semibold text-zinc-600">
      Not Connected
    </span>
  );
}

function Info({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "neutral" | "red";
}) {
  const toneClass =
    tone === "red" ? "text-red-700" : "text-zinc-900";
  return (
    <div className="min-w-0 rounded-lg bg-zinc-50 px-4 py-3">
      <p className="text-xs font-medium text-zinc-500">{label}</p>
      <p className={`mt-1 break-words text-sm font-semibold ${toneClass}`}>{value}</p>
    </div>
  );
}
