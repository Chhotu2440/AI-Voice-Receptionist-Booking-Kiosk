import { describe, expect, it } from "vitest";

import { addDays, ago, money, titleCase, todayIST, usd } from "./format";

describe("format", () => {
  it("formats rupees without paise and survives bad input", () => {
    expect(money("2400.00")).toBe("₹2,400");
    expect(money("120000")).toBe("₹1,20,000");
    expect(money("abc")).toBe("₹0");
  });

  it("uses the IST business date, not the browser's", () => {
    // 20:00 UTC on 10 Nov is 01:30 IST on 11 Nov.
    expect(todayIST(new Date("2026-11-10T20:00:00Z"))).toBe("2026-11-11");
    expect(addDays("2026-11-30", 1)).toBe("2026-12-01");
  });

  it("small helpers", () => {
    expect(usd("0.0916", 3)).toBe("$0.092");
    expect(titleCase("NO_SHOW")).toBe("No Show");
    expect(ago("2026-11-11T10:00:00Z", new Date("2026-11-11T10:05:00Z"))).toBe("5 min ago");
    expect(ago(null)).toBe("never");
  });
});
