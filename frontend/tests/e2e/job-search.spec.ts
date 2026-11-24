import { expect, test } from "@playwright/test";

const pilotOk = !!process.env.E2E_PILOT_READY;

test.describe("job search", () => {
  test.skip(!pilotOk, "Set E2E_PILOT_READY=1 with pilot API tunnel");

  test("search PK Software Engineer jobs", async ({ page }) => {
    await page.goto("/");
    await page.getByPlaceholder("e.g. Software Engineer").fill("Software Engineer");
    await page.getByPlaceholder("PK").fill("PK");
    await page.getByRole("button", { name: "Search jobs" }).click();
    await expect(page.getByText(/results/)).toBeVisible({ timeout: 20_000 });
    const link = page.getByRole("link", { name: /Software Engineer/i }).first();
    await expect(link).toBeVisible();
    await link.click();
    await expect(page.getByRole("link", { name: "← Back" })).toBeVisible();
  });
});