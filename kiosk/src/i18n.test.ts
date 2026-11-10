import { describe, expect, it } from "vitest";

import { STRINGS, formatDate, inr } from "./i18n";

describe("i18n", () => {
  it("has every English key in Hindi", () => {
    expect(Object.keys(STRINGS.hi).sort()).toEqual(Object.keys(STRINGS.en).sort());
  });

  it("formats rupees the Indian way", () => {
    expect(inr("2400.00")).toBe("₹2,400");
    expect(inr(125000)).toBe("₹1,25,000");
    expect(inr("874.99")).toBe("₹874.99");
  });

  it("formats business dates without timezone drift", () => {
    expect(formatDate("2026-11-16", "en", { weekday: undefined })).toContain("16");
  });
});
