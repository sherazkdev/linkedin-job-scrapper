import { expect, test } from "@playwright/test";

const enabled = process.env.E2E_PILOT_READY === "1";
const origin = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:13010";

test.describe.configure({ mode: "serial" });

test.beforeAll(() => {
  test.skip(!enabled, "Set E2E_PILOT_READY=1 and tunnel to staging");
});

async function bootstrap(page: import("@playwright/test").Page) {
  const res = await page.request.post("/api/alerts/session", {
    headers: { Origin: origin, "sec-fetch-site": "same-origin" },
  });
  expect(res.ok()).toBeTruthy();
  return res.json() as Promise<{ subscriber_id: string | null; created: boolean }>;
}

test("1-3 registration, returning subscriber, reload preserves session", async ({ page }) => {
  const first = await bootstrap(page);
  const second = await bootstrap(page);
  expect(second.created).toBe(false);
  if (first.subscriber_id && second.subscriber_id) {
    expect(second.subscriber_id).toBe(first.subscriber_id);
  }
  await page.goto("/saved-searches");
  await page.reload();
  const third = await bootstrap(page);
  expect(third.created).toBe(false);
});

test("4-7 saved search CRUD and enable/disable", async ({ page }) => {
  await bootstrap(page);
  await page.goto("/saved-searches");
  await page.waitForLoadState("networkidle");
  const keyword = `E2E-${Date.now()}`;
  await page.getByPlaceholder("Keyword").fill(keyword);
  await page.getByPlaceholder("Country (PK)").fill("PK");
  await page.getByPlaceholder("City").fill("Islamabad");
  await page.getByRole("button", { name: "Save search" }).click();
  await expect(page.getByText(keyword, { exact: false })).toBeVisible({ timeout: 25_000 });
  await page.getByRole("button", { name: "Edit" }).first().click();
  await page.locator('input[name="city"]').fill("Rawalpindi");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Rawalpindi")).toBeVisible();
  await page.getByRole("button", { name: "Disable alerts" }).click();
  await expect(page.getByText("Alerts off")).toBeVisible();
  await page.getByRole("button", { name: "Enable alerts" }).click();
  await expect(page.getByText("Alerts on")).toBeVisible();
  await page.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByText(keyword)).not.toBeVisible({ timeout: 10_000 });
});

test("8-11 job search, filters, pagination, detail", async ({ page }) => {
  await bootstrap(page);
  await page.goto("/");
  await page.getByPlaceholder("e.g. Software Engineer").fill("Software Engineer");
  await page.getByPlaceholder("PK").fill("PK");
  await page.locator('select[name="employment_type"]').selectOption("full_time");
  await page.getByRole("button", { name: "Search jobs" }).click();
  await expect(page.getByText(/results/)).toBeVisible({ timeout: 25_000 });
  const next = page.getByRole("button", { name: "Next" });
  if (await next.isEnabled()) {
    await next.click();
    await expect(page.getByText(/page 2/)).toBeVisible();
  }
  await page.getByRole("link", { name: /Software Engineer/i }).first().click();
  await expect(page.getByRole("link", { name: "← Back" })).toBeVisible();
});

test("12-14 notifications list, read, dismiss", async ({ page }) => {
  await bootstrap(page);
  const list = await page.request.get("/api/alerts/notifications?page_size=5");
  const body = await list.json();
  const items = body.items ?? [];
  test.skip(items.length === 0, "No pilot notifications to exercise read/dismiss");
  await page.goto("/notifications");
  await expect(page.locator("ul li").first()).toBeVisible();
  const mark = page.getByRole("button", { name: "Mark read" }).first();
  if (await mark.isVisible()) await mark.click();
  const dismiss = page.getByRole("button", { name: "Dismiss" }).first();
  if (await dismiss.isVisible()) await dismiss.click();
  const unread = await page.request.get("/api/alerts/notifications/unread-count");
  expect(unread.ok()).toBeTruthy();
});

test("15-16 digest without re-registration and preview", async ({ page }) => {
  await bootstrap(page);
  const before = await bootstrap(page);
  await page.goto("/preferences");
  await page.getByRole("button", { name: "Save digest settings" }).click();
  await expect(page.getByText(/saved/i)).toBeVisible({ timeout: 15_000 });
  const after = await bootstrap(page);
  if (before.subscriber_id && after.subscriber_id) {
    expect(after.subscriber_id).toBe(before.subscriber_id);
  }
  await page.getByRole("button", { name: "Run digest preview" }).click();
  await expect(page.locator("pre")).toBeVisible({ timeout: 20_000 });
});

test("17 sign out clears session", async ({ page }) => {
  await bootstrap(page);
  await page.goto("/preferences");
  await page.getByRole("button", { name: "Sign out alerts" }).click();
  const state = await page.request.get("/api/alerts/session");
  const body = await state.json();
  expect(body.active).toBeFalsy();
});

test("18 cross-origin rejected", async ({ request }) => {
  const res = await request.post("/api/alerts/searches", {
    headers: {
      Origin: "https://evil.example",
      "sec-fetch-site": "cross-site",
      "Content-Type": "application/json",
    },
    data: { q: "x", alerts_enabled: true },
  });
  expect(res.status()).toBe(403);
});

test("19 invalid session returns 401 on protected route", async ({ page }) => {
  await page.request.delete("/api/alerts/session", {
    headers: { Origin: origin, "sec-fetch-site": "same-origin" },
  });
  const res = await page.request.get("/api/alerts/searches");
  expect(res.status()).toBe(401);
});

test("20 jobs API outage surfaces safe error", async ({ page }) => {
  await page.route("**/api/jobs?**", (route) => route.abort("failed"));
  await page.goto("/");
  await page.getByPlaceholder("e.g. Software Engineer").fill("Engineer");
  await page.getByRole("button", { name: "Search jobs" }).click();
  await expect(page.getByRole("alert")).toBeVisible({ timeout: 10_000 });
});