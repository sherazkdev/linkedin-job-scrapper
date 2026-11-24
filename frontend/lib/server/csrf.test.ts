import { describe, expect, it } from "vitest";

import { getAppUrl } from "@/lib/config";

describe("config", () => {
  it("defaults app url for local dev", () => {
    expect(getAppUrl()).toContain("localhost");
  });
});