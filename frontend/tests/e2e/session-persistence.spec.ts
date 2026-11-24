import { expect, test } from "@playwright/test";

const pilotOk = !!process.env.E2E_PILOT_READY;

test.describe("alert session", () => {
  test.skip(!pilotOk, "Set E2E_PILOT_READY=1 with pilot API tunnel");

  test("bootstrap and preserve session across reload", async ({ page }) => {
    await page.goto("/saved-searches");
    await page.getByPlaceholder("Keyword").fill("Software Engineer");
    await page.getByPlaceholder("Country (PK)").fill("PK");
    await page.getByRole("button", { name: "Save search" }).click();
    await expect(page.getByText(/Software Engineer/)).toBeVisible({ timeout: 15_000 });

    const session1 = await page.request.post("/api/alerts/session");
    const body1 = await session1.json();
    expect(body1.active).toBeTruthy();

    await page.reload();
    const session2 = await page.request.post("/api/alerts/session");
    const body2 = await session2.json();
    expect(body2.created).toBe(false);
    expect(body2.subscriber_id).toBe(body1.subscriber_id);
  });

  test("preferences save does not rotate session", async ({ page }) => {
    await page.goto("/preferences");
    await page.getByRole("button", { name: "Save digest settings" }).click();
    const session = await page.request.get("/api/alerts/session");
    const body = await session.json();
    expect(body.active).toBe(true);
  });
});