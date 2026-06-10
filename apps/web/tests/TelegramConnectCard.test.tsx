import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import TelegramConnectCard from "../src/components/TelegramConnectCard";
import * as api from "../src/lib/api";

vi.mock("../src/lib/api", async () => {
  const actual = await vi.importActual("../src/lib/api");
  return {
    ...actual,
    createTelegramConnectCode: vi.fn(),
    getTelegramConnectionStatus: vi.fn(),
    disconnectTelegramIntegration: vi.fn(),
    sendTelegramTestMessage: vi.fn(),
  };
});

vi.mock("../src/context/AuthContext", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/context/AuthContext")>();
  return {
    ...actual,
    useAuth: () => ({
      user: { role: "Owner", factory_id: 1, telegram_chat_id: null },
    }),
  };
});

const mockStatus = (overrides: Partial<api.TelegramConnectionStatus>) => ({
  connected: false,
  role: "Owner" as const,
  chat_id_verified: false,
  ...overrides,
});

function renderCard() {
  return render(
    <MemoryRouter>
      <TelegramConnectCard />
    </MemoryRouter>
  );
}

describe("TelegramConnectCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("shows a Connect Telegram button for an unconnected owner", async () => {
    vi.mocked(api.getTelegramConnectionStatus).mockResolvedValue({
      data: mockStatus({ connected: false }),
      status: 200,
      statusText: "OK",
      headers: {},
      config: {} as any,
    });

    renderCard();
    expect(await screen.findByTestId("telegram-connect-button")).toBeInTheDocument();
  });

  it("renders connected state with username and connected_at when already bound", async () => {
    vi.mocked(api.getTelegramConnectionStatus).mockResolvedValue({
      data: mockStatus({
        connected: true,
        telegram_username: "owner_factory",
        telegram_first_name: "Ramesh",
        connected_at: "2026-06-08T18:30:00Z",
        welcome_sent_at: "2026-06-08T18:30:05Z",
        last_message_at: "2026-06-08T18:30:07Z",
        last_message_status: "sent",
      }),
      status: 200,
      statusText: "OK",
      headers: {} as any,
      config: {} as any,
    });

    renderCard();
    expect(await screen.findByTestId("telegram-connected-panel")).toBeInTheDocument();
    expect(screen.getByText(/Ramesh/i)).toBeInTheDocument();
    expect(screen.getByText(/@owner_factory/i)).toBeInTheDocument();
  });

  it("generates a 6-char code, shows it, and auto-opens the deep link", async () => {
    vi.mocked(api.getTelegramConnectionStatus).mockResolvedValue({
      data: mockStatus({ connected: false }),
      status: 200,
      statusText: "OK",
      headers: {} as any,
      config: {} as any,
    });
    vi.mocked(api.createTelegramConnectCode).mockResolvedValue({
      data: {
        code: "A7K9P2",
        deep_link: "https://t.me/MunshiHermesAi_Bot?start=bind_A7K9P2",
        bot_username: "MunshiHermesAi_Bot",
        expires_at: "2026-06-08T19:00:00Z",
      },
      status: 200,
      statusText: "OK",
      headers: {} as any,
      config: {} as any,
    });

    const opened = vi.fn();
    vi.stubGlobal("open", opened);

    renderCard();
    fireEvent.click(await screen.findByTestId("telegram-connect-button"));

    const codeEl = await screen.findByTestId("telegram-code");
    expect(codeEl.textContent?.replace(/\s/g, "")).toBe("A7K9P2");
    expect(opened).toHaveBeenCalledWith(
      "https://t.me/MunshiHermesAi_Bot?start=bind_A7K9P2",
      "_blank",
      "noopener,noreferrer"
    );
  });

  it("polls status every 2s and switches to connected view when binding lands", async () => {
    let connected = false;
    vi.mocked(api.getTelegramConnectionStatus).mockImplementation(async () => ({
      data: mockStatus({
        connected,
        telegram_username: connected ? "polling_user" : undefined,
      }),
      status: 200,
      statusText: "OK",
      headers: {} as any,
      config: {} as any,
    }));
    vi.mocked(api.createTelegramConnectCode).mockResolvedValue({
      data: {
        code: "B7L9P3",
        deep_link: "https://t.me/MunshiHermesAi_Bot?start=bind_B7L9P3",
        bot_username: "MunshiHermesAi_Bot",
        expires_at: "2026-06-08T19:00:00Z",
      },
      status: 200,
      statusText: "OK",
      headers: {} as any,
      config: {} as any,
    });

    renderCard();
    fireEvent.click(await screen.findByTestId("telegram-connect-button"));
    await screen.findByTestId("telegram-code-panel");

    // Simulate the user landing in the bot and the webhook binding successfully.
    await act(async () => {
      connected = true;
      vi.advanceTimersByTime(2_500);
    });

    await waitFor(() => {
      expect(screen.getByTestId("telegram-connected-panel")).toBeInTheDocument();
    });
  });

  it("shows an error when connect-code fails", async () => {
    vi.mocked(api.getTelegramConnectionStatus).mockResolvedValue({
      data: mockStatus({ connected: false }),
      status: 200,
      statusText: "OK",
      headers: {} as any,
      config: {} as any,
    });
    vi.mocked(api.createTelegramConnectCode).mockRejectedValue(new Error("boom"));

    renderCard();
    fireEvent.click(await screen.findByTestId("telegram-connect-button"));

    expect(await screen.findByRole("alert")).toHaveTextContent(/connect nahi ho paya/i);
  });
});
