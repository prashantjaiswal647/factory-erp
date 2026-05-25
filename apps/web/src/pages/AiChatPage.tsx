import axios from "axios";
import { AlertCircle, Bot, CheckCircle2, SendHorizontal, Sparkles, UserRound } from "lucide-react";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { useDataRefresh } from "../context/DataRefreshContext";
import { api, getBillCustomers, getCustomerOrders, sendBillNotification } from "../lib/api";
import type { BillCustomerOption, BillOrderOption } from "../lib/api";

type ChatRole = "assistant" | "user" | "error";

type ChatMessage = {
  id: string;
  role: ChatRole;
  text: string;
  status?: string;
  actionTaken?: string;
};

type ChatHistoryMessage = {
  role: "user" | "assistant";
  content: string;
};

type AskAIResponse = {
  ai_reply: string;
  action_taken: string;
  status: string;
  error?: string | null;
};

type StoredUser = {
  factory_id?: number;
};

const actionableIntents = new Set(["production_entry", "sales_entry", "expense_entry"]);
const invoiceDraftAction = "invoice_draft";
const chatMessagesStorageKey = "ai-erp-chat-messages";
const welcomeMessage: ChatMessage = {
  id: "welcome",
  role: "assistant",
  text: "I am your Factory Supervisor AI. I can use real-time inventory and production data to answer stock, production, and wastage questions."
};
const supervisorSystemPrompt = "You are a Factory Supervisor AI. You have access to real-time inventory and production data. Use it to give precise numbers.";

function createId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function getSessionId() {
  const storageKey = "ai-erp-chat-session-id";
  const existingSessionId = window.localStorage.getItem(storageKey);

  if (existingSessionId) {
    return existingSessionId;
  }

  const newSessionId = crypto.randomUUID();
  window.localStorage.setItem(storageKey, newSessionId);
  return newSessionId;
}

export default function AiChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>(() => loadStoredMessages());
  const [inputValue, setInputValue] = useState("");
  const [isThinking, setIsThinking] = useState(false);
  const [toast, setToast] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [billingCustomers, setBillingCustomers] = useState<BillCustomerOption[]>([]);
  const [billingOrders, setBillingOrders] = useState<BillOrderOption[]>([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState("");
  const [selectedOrderId, setSelectedOrderId] = useState("");
  const [isBillingLoading, setIsBillingLoading] = useState(false);
  const [isBillSending, setIsBillSending] = useState(false);
  const { triggerDataRefresh } = useDataRefresh();
  const sessionId = useMemo(getSessionId, []);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isThinking]);

  useEffect(() => {
    window.localStorage.setItem(chatMessagesStorageKey, JSON.stringify(messages));
  }, [messages]);

  useEffect(() => {
    void loadBillingCustomers();
  }, []);

  useEffect(() => {
    if (!selectedCustomerId) {
      setBillingOrders([]);
      setSelectedOrderId("");
      return;
    }
    void loadCustomerOrders(Number(selectedCustomerId));
  }, [selectedCustomerId]);

  async function loadBillingCustomers() {
    setIsBillingLoading(true);
    try {
      const response = await getBillCustomers();
      setBillingCustomers(response.data);
    } finally {
      setIsBillingLoading(false);
    }
  }

  async function loadCustomerOrders(customerId: number) {
    setIsBillingLoading(true);
    try {
      const response = await getCustomerOrders(customerId);
      setBillingOrders(response.data);
      setSelectedOrderId(response.data[0]?.id ? String(response.data[0].id) : "");
    } finally {
      setIsBillingLoading(false);
    }
  }

  async function handleSendBill() {
    if (!selectedCustomerId || !selectedOrderId || isBillSending) {
      return;
    }

    setIsBillSending(true);
    try {
      const response = await sendBillNotification({
        customer_id: Number(selectedCustomerId),
        order_id: Number(selectedOrderId)
      });
      const successMessage = response.data.message || "Bill successfully sent to Owner and Customer via Telegram/WhatsApp.";
      setToast({ type: "success", message: successMessage });
      setMessages((currentMessages) => [
        ...currentMessages,
        {
          id: createId(),
          role: "assistant",
          text: successMessage
        }
      ]);
    } catch (error) {
      let errorMessage = "Unable to send bill notification.";
      if (axios.isAxiosError(error)) {
        const detail = error.response?.data?.detail;
        errorMessage = typeof detail === "string" ? detail : error.message || errorMessage;
      }
      setToast({ type: "error", message: errorMessage });
      setMessages((currentMessages) => [...currentMessages, { id: createId(), role: "error", text: errorMessage }]);
    } finally {
      setIsBillSending(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const messageText = inputValue.trim();
    if (!messageText || isThinking) {
      return;
    }

    const chatHistory = toChatHistory(messages).slice(-10);

    setInputValue("");
    setMessages((currentMessages) => [
      ...currentMessages,
      {
        id: createId(),
        role: "user",
        text: messageText
      }
    ]);
    setIsThinking(true);

    try {
      const response = await api.post<AskAIResponse>("/ask-ai", {
        message: messageText,
        session_id: sessionId,
        chat_history: chatHistory,
        factory_id: getStoredFactoryId(),
        system_prompt: supervisorSystemPrompt
      });

      const aiResponse = response.data;
      const normalizedResponse = normalizeAskAIResponse(aiResponse);
      setMessages((currentMessages) => [
        ...currentMessages,
        {
          id: createId(),
          role: normalizedResponse.status === "validation_error" ? "error" : "assistant",
          text: normalizedResponse.ai_reply,
          status: normalizedResponse.status,
          actionTaken: normalizedResponse.action_taken
        }
      ]);
      if (normalizedResponse.status !== "success" && normalizedResponse.error) {
        setToast({ type: "error", message: normalizedResponse.error });
      }

      if (normalizedResponse.status === "success" && actionableIntents.has(normalizedResponse.action_taken)) {
        setToast({ type: "success", message: "ERP updated" });
        triggerDataRefresh();
      }
    } catch (error) {
      let errorMessage = "Unable to reach the AI backend. Please check that the API container is running.";

      if (axios.isAxiosError(error)) {
        const detail = error.response?.data?.detail;
        if (typeof detail === "string") {
          errorMessage = detail;
        } else if (error.message) {
          errorMessage = error.message;
        }
      }

      setMessages((currentMessages) => [
        ...currentMessages,
        {
          id: createId(),
          role: "error",
          text: errorMessage
        }
      ]);
      setToast({ type: "error", message: errorMessage });
    } finally {
      setIsThinking(false);
    }
  }

  return (
    <div className="flex h-[calc(100vh-7.5rem)] min-h-[560px] flex-col overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm">
      {toast ? <Toast type={toast.type} message={toast.message} onClose={() => setToast(null)} /> : null}
      <div className="flex items-center justify-between gap-3 border-b border-zinc-200 px-5 py-4">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-md bg-brand-50 text-brand-700">
            <Sparkles className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-zinc-950">AI Supervisor</h1>
            <p className="text-sm text-zinc-500">Posts production, sales, and expenses to the ERP</p>
          </div>
        </div>
        <div className="hidden rounded-md border border-zinc-200 px-3 py-1.5 text-xs text-zinc-500 sm:block">
          Session active
        </div>
      </div>

      <div className="border-b border-zinc-200 bg-white px-5 py-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-zinc-950">Operations / Billing</h2>
            <p className="text-xs text-zinc-500">Generate and send a storefront order bill.</p>
          </div>
          {isBillingLoading ? <span className="text-xs font-medium text-zinc-400">Loading...</span> : null}
        </div>
        <div className="grid gap-3 lg:grid-cols-[1fr_1fr_auto]">
          <label className="block text-sm">
            <span className="font-medium text-zinc-700">Customer</span>
            <select
              className="mt-1 h-10 w-full rounded-md border border-zinc-200 bg-white px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
              value={selectedCustomerId}
              onChange={(event) => setSelectedCustomerId(event.target.value)}
            >
              <option value="">Select customer</option>
              {billingCustomers.map((customer) => (
                <option key={customer.id} value={customer.id}>
                  {customer.name} {customer.phone_number ? `- ${customer.phone_number}` : ""}
                </option>
              ))}
            </select>
          </label>

          <label className="block text-sm">
            <span className="font-medium text-zinc-700">Recent Order</span>
            <select
              className="mt-1 h-10 w-full rounded-md border border-zinc-200 bg-white px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 disabled:bg-zinc-50"
              value={selectedOrderId}
              onChange={(event) => setSelectedOrderId(event.target.value)}
              disabled={!selectedCustomerId || billingOrders.length === 0}
            >
              <option value="">Select order</option>
              {billingOrders.map((order) => (
                <option key={order.id} value={order.id}>
                  #{order.id} - Rs {order.total_amount} - {order.status}
                </option>
              ))}
            </select>
          </label>

          <button
            className="mt-auto inline-flex h-10 items-center justify-center rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 disabled:bg-zinc-300"
            type="button"
            disabled={!selectedCustomerId || !selectedOrderId || isBillSending}
            onClick={handleSendBill}
          >
            {isBillSending ? "Sending..." : "Generate & Send Bill"}
          </button>
        </div>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto bg-zinc-50 px-5 py-6">
        {messages.map((message) => (
          <ChatBubble key={message.id} message={message} />
        ))}

        {isThinking ? <ThinkingIndicator /> : null}
        <div ref={messagesEndRef} />
      </div>

      <form className="flex gap-3 border-t border-zinc-200 bg-white p-4" onSubmit={handleSubmit}>
        <input
          className="h-11 flex-1 rounded-md border border-zinc-200 bg-zinc-50 px-4 text-sm outline-none transition placeholder:text-zinc-400 focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-100 disabled:cursor-not-allowed disabled:opacity-70"
          placeholder="Example: Aaj 10 box bane 65ml ke Premium Packing me"
          type="text"
          value={inputValue}
          onChange={(event) => setInputValue(event.target.value)}
          disabled={isThinking}
        />
        <button
          className="inline-flex h-11 items-center justify-center gap-2 rounded-md bg-brand-600 px-4 text-sm font-medium text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
          type="submit"
          disabled={isThinking || !inputValue.trim()}
        >
          <SendHorizontal className="h-4 w-4" aria-hidden="true" />
          Send
        </button>
      </form>
    </div>
  );
}

function Toast({ type, message, onClose }: { type: "success" | "error"; message: string; onClose: () => void }) {
  return (
    <button
      className={`fixed right-5 top-20 z-50 rounded-md px-4 py-3 text-sm font-semibold text-white shadow-lg ${type === "success" ? "bg-[#16A34A]" : "bg-[#DC2626]"}`}
      type="button"
      onClick={onClose}
    >
      {message}
    </button>
  );
}

function getStoredFactoryId() {
  const savedUser = window.localStorage.getItem("ai_erp_user");
  if (!savedUser) {
    return undefined;
  }
  try {
    return (JSON.parse(savedUser) as StoredUser).factory_id;
  } catch {
    return undefined;
  }
}

function loadStoredMessages() {
  const storedMessages = window.localStorage.getItem(chatMessagesStorageKey);
  if (!storedMessages) {
    return [welcomeMessage];
  }

  try {
    const parsedMessages = JSON.parse(storedMessages) as ChatMessage[];
    if (!Array.isArray(parsedMessages) || parsedMessages.length === 0) {
      return [welcomeMessage];
    }
    return parsedMessages;
  } catch {
    return [welcomeMessage];
  }
}

function toChatHistory(messages: ChatMessage[]): ChatHistoryMessage[] {
  return messages
    .filter((message): message is ChatMessage & { role: "user" | "assistant" } => (
      (message.role === "user" || message.role === "assistant") && message.id !== "welcome"
    ))
    .map((message) => ({
      role: message.role,
      content: message.text
    }));
}

function normalizeAskAIResponse(response: AskAIResponse): AskAIResponse {
  return {
    ai_reply: response.ai_reply || "",
    action_taken: response.action_taken || "general_qa",
    status: response.status || "success",
    error: response.error ?? null
  };
}

function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const isError = message.role === "error";
  const invoiceDraft = getInvoiceDraft(message);

  return (
    <div className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser ? (
        <div
          className={`mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-md ${
            isError ? "bg-red-50 text-red-600" : "bg-brand-50 text-brand-700"
          }`}
        >
          {isError ? <AlertCircle className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
        </div>
      ) : null}

      <div className="max-w-2xl">
        <div
          className={[
            "rounded-lg px-4 py-3 text-sm leading-6 shadow-sm",
            isUser
              ? "bg-brand-600 text-white"
              : isError
                ? "border border-red-200 bg-red-50 text-red-700"
                : "border border-zinc-200 bg-white text-zinc-700"
          ].join(" ")}
        >
          <div className="whitespace-pre-wrap">{message.text}</div>
        </div>

        {invoiceDraft ? <InvoiceActions invoice={invoiceDraft} /> : null}

        {message.status === "success" && message.actionTaken && actionableIntents.has(message.actionTaken) ? (
          <div className="mt-2 flex items-center gap-1.5 text-xs font-medium text-emerald-700">
            <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
            ERP updated. Dashboard and tables are refreshing.
          </div>
        ) : null}
      </div>

      {isUser ? (
        <div className="mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-md bg-zinc-900 text-white">
          <UserRound className="h-4 w-4" />
        </div>
      ) : null}
    </div>
  );
}

type InvoiceTableRow = {
  product: string;
  volume: string;
  packaging: string;
  boxes: string;
  piecesPerBox: string;
  totalPackets: string;
  rate: string;
  taxable: string;
  gst: string;
  lineTotal: string;
};

type ParsedInvoiceDraft = {
  title: string;
  rows: InvoiceTableRow[];
  subtotal: string;
  gst: string;
  grandTotal: string;
  rawText: string;
};

function getInvoiceDraft(message: ChatMessage): ParsedInvoiceDraft | null {
  if (message.role !== "assistant") {
    return null;
  }
  const isInvoiceDraft =
    message.actionTaken === invoiceDraftAction ||
    (message.status === "needs_confirmation" &&
      message.text.includes("Invoice Draft") &&
      message.text.includes("Type CONFIRM"));

  if (!isInvoiceDraft) {
    return null;
  }
  return parseInvoiceDraftMarkdown(message.text);
}

function parseInvoiceDraftMarkdown(text: string): ParsedInvoiceDraft {
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const title = lines.find((line) => line.startsWith("### "))?.replace(/^###\s+/, "") || "Invoice Draft";
  const tableRows = lines
    .filter((line) => line.startsWith("|") && !line.includes("---") && !line.includes("Product | Volume"))
    .map((line) => line.split("|").map((cell) => cell.trim()).filter(Boolean))
    .filter((cells) => cells.length >= 10)
    .map((cells) => ({
      product: cells[0],
      volume: cells[1],
      packaging: cells[2],
      boxes: cells[3],
      piecesPerBox: cells[4],
      totalPackets: cells[5],
      rate: cells[6],
      taxable: cells[7],
      gst: cells[8],
      lineTotal: cells[9]
    }));

  return {
    title,
    rows: tableRows,
    subtotal: extractSummaryValue(text, "Subtotal"),
    gst: extractSummaryValue(text, "GST"),
    grandTotal: extractSummaryValue(text, "Grand Total"),
    rawText: text
  };
}

function extractSummaryValue(text: string, label: string) {
  const escapedLabel = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = text.match(new RegExp(`\\*\\*${escapedLabel}(?: \\([^)]*\\))?:\\*\\*\\s*([^\\n]+)`, "i"));
  return match?.[1]?.trim() || "-";
}

function InvoiceActions({ invoice }: { invoice: ParsedInvoiceDraft }) {
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      <button
        className="inline-flex h-9 items-center justify-center rounded-md border border-zinc-300 bg-white px-3 text-xs font-semibold text-zinc-800 shadow-sm hover:bg-zinc-50"
        type="button"
        onClick={() => openInvoicePrintWindow(invoice, "print")}
      >
        🖨️ Direct Print Invoice
      </button>
      <button
        className="inline-flex h-9 items-center justify-center rounded-md border border-brand-200 bg-brand-50 px-3 text-xs font-semibold text-brand-800 shadow-sm hover:bg-brand-100"
        type="button"
        onClick={() => openInvoicePrintWindow(invoice, "pdf")}
      >
        📥 Download Invoice PDF
      </button>
    </div>
  );
}

function openInvoicePrintWindow(invoice: ParsedInvoiceDraft, mode: "print" | "pdf") {
  const printWindow = window.open("", "_blank", "width=960,height=720");
  if (!printWindow) {
    return;
  }

  printWindow.document.open();
  printWindow.document.write(buildInvoicePrintHtml(invoice, mode));
  printWindow.document.close();
  printWindow.focus();
  window.setTimeout(() => {
    printWindow.print();
  }, 250);
}

function buildInvoicePrintHtml(invoice: ParsedInvoiceDraft, mode: "print" | "pdf") {
  const rows = invoice.rows.length
    ? invoice.rows
        .map(
          (row, index) => `
            <tr>
              <td>${index + 1}</td>
              <td>${escapeHtml(row.product)}</td>
              <td>${escapeHtml(row.volume)}</td>
              <td>${escapeHtml(row.packaging)}</td>
              <td class="num">${escapeHtml(row.boxes)}</td>
              <td class="num">${escapeHtml(row.piecesPerBox)}</td>
              <td class="num">${escapeHtml(row.totalPackets)}</td>
              <td class="num">${escapeHtml(row.rate)}</td>
              <td class="num">${escapeHtml(row.taxable)}</td>
              <td class="num">${escapeHtml(row.gst)}</td>
              <td class="num">${escapeHtml(row.lineTotal)}</td>
            </tr>`
        )
        .join("")
    : `<tr><td colspan="11"><pre>${escapeHtml(invoice.rawText)}</pre></td></tr>`;

  return `<!doctype html>
    <html>
      <head>
        <title>${escapeHtml(invoice.title)}</title>
        <style>
          * { box-sizing: border-box; }
          body { margin: 0; padding: 32px; color: #111827; font-family: Arial, sans-serif; }
          .invoice { max-width: 960px; margin: 0 auto; }
          .header { display: flex; justify-content: space-between; gap: 24px; border-bottom: 2px solid #111827; padding-bottom: 18px; margin-bottom: 24px; }
          h1 { margin: 0; font-size: 24px; }
          .muted { color: #6B7280; font-size: 12px; }
          table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 12px; }
          th, td { border: 1px solid #D1D5DB; padding: 8px; text-align: left; vertical-align: top; }
          th { background: #F3F4F6; font-weight: 700; }
          .num { text-align: right; white-space: nowrap; }
          .summary { margin-left: auto; margin-top: 20px; width: 320px; border: 1px solid #D1D5DB; }
          .summary-row { display: flex; justify-content: space-between; padding: 10px 12px; border-bottom: 1px solid #E5E7EB; }
          .summary-row:last-child { border-bottom: 0; font-weight: 700; background: #F9FAFB; }
          .pdf-note { margin-top: 16px; color: #6B7280; font-size: 12px; }
          pre { white-space: pre-wrap; font-family: Arial, sans-serif; }
          @media print {
            body { padding: 18px; }
            .pdf-note { display: none; }
          }
        </style>
      </head>
      <body>
        <main class="invoice">
          <section class="header">
            <div>
              <h1>Munshi AI Invoice</h1>
              <div class="muted">${escapeHtml(invoice.title)}</div>
            </div>
            <div class="muted">Generated from AI Supervisor<br />${new Date().toLocaleString()}</div>
          </section>
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Product</th>
                <th>Volume</th>
                <th>Packaging</th>
                <th>Boxes</th>
                <th>Pieces/Box</th>
                <th>Total Packets</th>
                <th>Rate</th>
                <th>Taxable</th>
                <th>GST</th>
                <th>Line Total</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
          <section class="summary">
            <div class="summary-row"><span>Subtotal</span><span>${escapeHtml(invoice.subtotal)}</span></div>
            <div class="summary-row"><span>GST</span><span>${escapeHtml(invoice.gst)}</span></div>
            <div class="summary-row"><span>Grand Total</span><span>${escapeHtml(invoice.grandTotal)}</span></div>
          </section>
          ${mode === "pdf" ? '<p class="pdf-note">Print dialog me destination "Save as PDF" select karke invoice download karein.</p>' : ""}
        </main>
      </body>
    </html>`;
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function ThinkingIndicator() {
  return (
    <div className="flex justify-start gap-3">
      <div className="mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-md bg-brand-50 text-brand-700">
        <Bot className="h-4 w-4" />
      </div>
      <div className="rounded-lg border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-500 shadow-sm">
        <span className="mr-2">Thinking</span>
        <span className="inline-flex items-center gap-1 align-middle">
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400 [animation-delay:-0.2s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400 [animation-delay:-0.1s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400" />
        </span>
      </div>
    </div>
  );
}
