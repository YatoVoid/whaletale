import { describe, expect, it } from "vitest";
import { addDays, dwell, pct } from "./format";

describe("format", () => {
  it("pct shows one decimal and an em dash for null", () => {
    expect(pct(0.4612)).toBe("46.1%");
    expect(pct(null)).toBe("—");
  });

  it("dwell reads as minutes and seconds past a minute", () => {
    expect(dwell(42)).toBe("42s");
    expect(dwell(125)).toBe("2m 05s");
  });

  it("addDays walks the ISO date", () => {
    expect(addDays("2026-06-30", 1)).toBe("2026-07-01");
    expect(addDays("2026-06-01", -7)).toBe("2026-05-25");
  });
});
