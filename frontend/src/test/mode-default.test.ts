import { describe, expect, it } from "vitest";
import { DEFAULT_DATA_MODE } from "@/api/mode-default";
// Standalone export: live FastAPI backend by default (tests run with VITE_DATA_MODE=fixture via vitest.config.ts).
describe("default data mode", () => {
  it("is live in the standalone export", () => expect(DEFAULT_DATA_MODE).toBe("live"));
  it("tests run with explicit fixture override", () => expect(import.meta.env.VITE_DATA_MODE).toBe("fixture"));
});
