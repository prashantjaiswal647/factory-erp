import { describe, expect, it } from "vitest";

import { formatMoneyValue, toNumber } from "./format";


describe("numeric formatting", () => {
  it("handles Decimal strings without throwing", () => {
    expect(toNumber("0.00")).toBe(0);
    expect(toNumber("1500.50")).toBe(1500.5);
    expect(formatMoneyValue("0.00")).toBe("0.00");
    expect(formatMoneyValue("1500.50")).toBe("1500.50");
  });

  it("uses the requested fallback for invalid values", () => {
    expect(toNumber("not-a-number", 12)).toBe(12);
    expect(formatMoneyValue(undefined, 5)).toBe("5.00");
  });
});
