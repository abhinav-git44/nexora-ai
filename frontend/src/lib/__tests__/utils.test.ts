import { describe, expect, it } from "vitest";
import { cn, fmtBytes, fmtCompact, fmtPct, fmtUSD, initials, titleCase } from "../utils";

describe("formatting utilities", () => {
  it("merges tailwind classes with later wins", () => { expect(cn("px-2", "px-4", false && "hidden")).toBe("px-4"); });
  it("formats money, percents and sizes", () => {
    expect(fmtUSD(1234.5)).toBe("$1,234.50");
    expect(fmtUSD(null)).toBe("—");
    expect(fmtPct(0.256)).toBe("26%");
    expect(fmtBytes(2048)).toBe("2.0 KB");
    expect(fmtCompact(15300)).toBe("15.3K");
  });
  it("derives initials and title case", () => {
    expect(initials("Priya Sharma")).toBe("PS");
    expect(initials(undefined)).toBe("?");
    expect(titleCase("workflow_runs")).toBe("Workflow Runs");
  });
});
