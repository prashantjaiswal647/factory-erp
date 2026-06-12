import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  api,
  getAuthTokenFromResponse,
  getInventory,
  getStoredAuthToken,
  getUserSubscription,
  searchCustomers,
  storeAuthToken,
} from "../src/lib/api";

describe("protected API authentication", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it.each([
    [{ access_token: "access-value" }, "access-value"],
    [{ token: "token-value" }, "token-value"],
    [{ jwt: "jwt-value" }, "jwt-value"],
  ])("extracts supported login token response keys", (response, expected) => {
    expect(getAuthTokenFromResponse(response)).toBe(expected);
  });

  it.each(["access-token", "legacy-token"])(
    "attaches the persisted bearer token to protected requests",
    async (token) => {
      storeAuthToken(token);
      const adapter = vi.fn(async (config) => ({
        data: {},
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      }));
      api.defaults.adapter = adapter;

      await getUserSubscription();
      await getInventory();
      await searchCustomers("paper");

      expect(getStoredAuthToken()).toBe(token);
      expect(adapter).toHaveBeenCalledTimes(3);
      for (const [config] of adapter.mock.calls) {
        expect(config.headers.Authorization).toBe(`Bearer ${token}`);
      }
    },
  );

  it("does not send an Authorization header when no token exists", async () => {
    const adapter = vi.fn(async (config) => ({
      data: {},
      status: 200,
      statusText: "OK",
      headers: {},
      config,
    }));
    api.defaults.adapter = adapter;

    await getUserSubscription();

    expect(adapter.mock.calls[0][0].headers.Authorization).toBeUndefined();
  });
});
