import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockBootstrap = vi.fn();
const mockValidate = vi.fn();
const mockClear = vi.fn();

vi.mock("@/lib/server/alerts-session", () => ({
  bootstrapAlertSession: () => mockBootstrap(),
  validateExistingSession: () => mockValidate(),
}));

vi.mock("@/lib/server/session", () => ({
  clearAlertSession: () => mockClear(),
}));

vi.mock("@/lib/server/csrf", () => ({
  assertSameOrigin: vi.fn().mockResolvedValue(undefined),
}));

describe("session route handlers", () => {
  beforeEach(() => {
    mockBootstrap.mockReset();
    mockValidate.mockReset();
    mockClear.mockReset();
  });

  afterEach(() => {
    vi.resetModules();
  });

  it("GET returns inactive without cookie session", async () => {
    mockValidate.mockResolvedValue({ active: false });
    const { GET } = await import("@/app/api/alerts/session/route");
    const res = await GET();
    const body = await res.json();
    expect(body.active).toBe(false);
  });

  it("POST bootstrap reuses session without created flag", async () => {
    mockBootstrap.mockResolvedValue({
      active: true,
      subscriber_id: "sub-1",
      created: false,
    });
    const { POST } = await import("@/app/api/alerts/session/route");
    const res = await POST();
    const body = await res.json();
    expect(body.subscriber_id).toBe("sub-1");
    expect(body.created).toBe(false);
    expect(mockBootstrap).toHaveBeenCalledTimes(1);
  });
});