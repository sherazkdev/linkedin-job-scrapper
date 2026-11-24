import { describe, expect, it } from "vitest";

import { evaluateTrustedBrowserRequest } from "@/lib/server/csrf";

const APP = "http://localhost:3000";

describe("evaluateTrustedBrowserRequest", () => {
  it("allows GET without origin", () => {
    expect(
      evaluateTrustedBrowserRequest({
        appUrl: APP,
        origin: null,
        referer: null,
        secFetchSite: null,
        method: "GET",
      }).ok,
    ).toBe(true);
  });

  it("rejects cross-site POST", () => {
    const r = evaluateTrustedBrowserRequest({
      appUrl: APP,
      origin: "https://evil.example",
      referer: null,
      secFetchSite: "cross-site",
      method: "POST",
    });
    expect(r.ok).toBe(false);
  });

  it("accepts matching origin on POST", () => {
    const r = evaluateTrustedBrowserRequest({
      appUrl: APP,
      origin: "http://localhost:3000",
      referer: null,
      secFetchSite: "same-origin",
      method: "POST",
    });
    expect(r.ok).toBe(true);
  });

  it("rejects origin with wrong port", () => {
    const r = evaluateTrustedBrowserRequest({
      appUrl: APP,
      origin: "http://localhost:4000",
      referer: null,
      secFetchSite: "same-origin",
      method: "POST",
    });
    expect(r.ok).toBe(false);
  });

  it("accepts same-origin without origin when sec-fetch-site is same-origin", () => {
    const r = evaluateTrustedBrowserRequest({
      appUrl: APP,
      origin: null,
      referer: null,
      secFetchSite: "same-origin",
      method: "POST",
    });
    expect(r.ok).toBe(true);
  });

  it("rejects POST with missing origin and referer", () => {
    const r = evaluateTrustedBrowserRequest({
      appUrl: APP,
      origin: null,
      referer: null,
      secFetchSite: null,
      method: "POST",
    });
    expect(r.ok).toBe(false);
  });
});