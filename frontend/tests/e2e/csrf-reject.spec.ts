import { expect, test } from "@playwright/test";

test("rejects cross-origin saved-search create", async ({ request }) => {
  const res = await request.post("/api/alerts/searches", {
    headers: {
      Origin: "https://attacker.example",
      "Content-Type": "application/json",
      "sec-fetch-site": "cross-site",
    },
    data: { q: "test", alerts_enabled: true },
  });
  expect(res.status()).toBe(403);
});