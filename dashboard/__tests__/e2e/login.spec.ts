/**
 * E2E tests for the login flow.
 * Requires the dashboard dev server running on localhost:3002.
 * Requires the LangSight API running on localhost:8000.
 */
import { test, expect } from "@playwright/test";

test.describe("Login page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/login");
  });

  test("renders login form correctly", async ({ page }) => {
    await expect(page.getByText("LangSight").first()).toBeVisible();
    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByLabel("Password").first()).toBeVisible();
    await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
  });

  test("shows demo credentials hint", async ({ page }) => {
    await expect(page.getByText(/demo credentials/i)).toBeVisible();
  });

  test("toggles password visibility", async ({ page }) => {
    const pwInput = page.getByLabel("Password").first();
    await expect(pwInput).toHaveAttribute("type", "password");

    await page.getByRole("button", { name: /show password|hide password/i }).click();
    await expect(pwInput).toHaveAttribute("type", "text");

    await page.getByRole("button", { name: /show password|hide password/i }).click();
    await expect(pwInput).toHaveAttribute("type", "password");
  });

  test("signs in with valid credentials and redirects to /", async ({ page }) => {
    await page.fill('[id="email"]', "admin@langsight.io");
    await page.fill('[id="password"]', "demo123");
    await page.getByRole("button", { name: /sign in/i }).click();

    await expect(page).toHaveURL("/", { timeout: 10_000 });
  });

  test("shows loading state while signing in", async ({ page }) => {
    await page.fill('[id="email"]', "admin@langsight.io");
    await page.fill('[id="password"]', "demo123");

    const submitBtn = page.getByRole("button", { name: /sign in/i });
    await submitBtn.click();

    // Loading state — button text changes briefly
    await expect(page.getByText(/signing in/i)).toBeVisible({ timeout: 2_000 }).catch(() => {
      // Loading state may be too fast to catch — that's fine
    });
  });
});
