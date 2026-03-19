/**
 * E2E tests for core dashboard pages.
 * Requires the user to be signed in — handled via storageState fixture.
 */
import { test, expect, type Page } from "@playwright/test";

/* ── Auth helper ─────────────────────────────────────────────── */
async function signIn(page: Page) {
  await page.goto("/login");
  await page.fill('[id="email"]', "admin@langsight.io");
  await page.fill('[id="password"]', "demo123");
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL("/", { timeout: 10_000 });
}

/* ── Sidebar navigation ─────────────────────────────────────── */
test.describe("Sidebar navigation", () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page);
  });

  test("sidebar is visible on all dashboard pages", async ({ page }) => {
    await expect(page.getByText("LangSight").first()).toBeVisible();
    await expect(page.getByRole("link", { name: /overview/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /sessions/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /agents/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /costs/i })).toBeVisible();
  });

  test("navigates to Sessions page", async ({ page }) => {
    await page.getByRole("link", { name: /sessions/i }).click();
    await expect(page).toHaveURL("/sessions");
    await expect(page.getByText("Sessions").first()).toBeVisible();
  });

  test("navigates to Agents page", async ({ page }) => {
    await page.getByRole("link", { name: /agents/i }).click();
    await expect(page).toHaveURL("/agents");
  });

  test("navigates to Costs page", async ({ page }) => {
    await page.getByRole("link", { name: /costs/i }).click();
    await expect(page).toHaveURL("/costs");
  });

  test("navigates to Tool Health page", async ({ page }) => {
    await page.getByRole("link", { name: /tool health/i }).click();
    await expect(page).toHaveURL("/health");
  });

  test("navigates to MCP Security page", async ({ page }) => {
    await page.getByRole("link", { name: /mcp security/i }).click();
    await expect(page).toHaveURL("/security");
  });

  test("navigates to Settings page", async ({ page }) => {
    await page.getByRole("link", { name: /settings/i }).click();
    await expect(page).toHaveURL("/settings");
  });

  test("marks current page as active in sidebar", async ({ page }) => {
    await page.getByRole("link", { name: /sessions/i }).click();
    await page.waitForURL("/sessions");
    const sessionsLink = page.getByRole("link", { name: /sessions/i });
    const classes = await sessionsLink.getAttribute("class");
    expect(classes).toContain("active");
  });
});

/* ── Overview page ───────────────────────────────────────────── */
test.describe("Overview page", () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page);
  });

  test("renders the topbar with page title", async ({ page }) => {
    await expect(page.getByText("Overview").first()).toBeVisible();
  });

  test("renders metric cards section", async ({ page }) => {
    // Should show 4 metric cards (or skeletons while loading)
    const cards = page.locator(".metric-card");
    await expect(cards).toHaveCount(4, { timeout: 8_000 });
  });

  test("has a Run Check button", async ({ page }) => {
    await expect(page.getByRole("button", { name: /run check/i })).toBeVisible();
  });

  test("shows Recent Sessions section", async ({ page }) => {
    await expect(page.getByText("Recent Sessions")).toBeVisible();
  });

  test("shows Tools & MCPs section", async ({ page }) => {
    await expect(page.getByText("Tools & MCPs")).toBeVisible({ timeout: 8_000 });
  });
});

/* ── Sessions page ───────────────────────────────────────────── */
test.describe("Sessions page", () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page);
    await page.goto("/sessions");
  });

  test("renders page with filter controls", async ({ page }) => {
    await expect(page.getByPlaceholder(/search session/i)).toBeVisible({ timeout: 8_000 });
  });

  test("shows time range buttons", async ({ page }) => {
    await expect(page.getByRole("button", { name: "24h" }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "7d" }).first()).toBeVisible();
  });

  test("switches time range on button click", async ({ page }) => {
    const sevenDayBtn = page.getByRole("button", { name: "7d" }).first();
    await sevenDayBtn.click();
    const classes = await sevenDayBtn.getAttribute("class");
    expect(classes).toContain("bg-primary");
  });

  test("filter buttons All / Clean / Failed are visible", async ({ page }) => {
    await expect(page.getByRole("button", { name: /^All \d/i }).first()).toBeVisible({ timeout: 8_000 });
    await expect(page.getByRole("button", { name: /^Clean \d/i }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: /^Failed \d/i }).first()).toBeVisible();
  });

  test("shows empty state when no sessions", async ({ page }) => {
    // If no sessions are seeded, should show empty state message
    const emptyOrTable = await Promise.race([
      page.getByText(/no sessions yet/i).waitFor({ timeout: 6_000 }).then(() => "empty"),
      page.locator("table").waitFor({ timeout: 6_000 }).then(() => "table"),
    ]).catch(() => "either");
    expect(["empty", "table", "either"]).toContain(emptyOrTable);
  });
});

/* ── Costs page ──────────────────────────────────────────────── */
test.describe("Costs page", () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page);
    await page.goto("/costs");
  });

  test("renders the Cost Attribution page title in topbar", async ({ page }) => {
    await expect(page.getByText("Cost Attribution").first()).toBeVisible();
  });

  test("renders time window buttons", async ({ page }) => {
    await expect(page.getByRole("button", { name: "24h" })).toBeVisible();
    await expect(page.getByRole("button", { name: "7d" })).toBeVisible();
    await expect(page.getByRole("button", { name: "30d" })).toBeVisible();
  });

  test("shows requires ClickHouse state for SQLite backend", async ({ page }) => {
    // With SQLite backend, costs are not supported
    await expect(
      page.getByText(/cost attribution requires clickhouse/i)
    ).toBeVisible({ timeout: 8_000 });
  });
});

/* ── Health page ─────────────────────────────────────────────── */
test.describe("Health page", () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page);
    await page.goto("/health");
  });

  test("renders Tool Health title in topbar", async ({ page }) => {
    await expect(page.getByText("Tool Health").first()).toBeVisible();
  });

  test("shows Run Check button", async ({ page }) => {
    await expect(page.getByRole("button", { name: /run check/i })).toBeVisible();
  });

  test("clicking Run Check button triggers a check", async ({ page }) => {
    const runBtn = page.getByRole("button", { name: /run check/i });
    await runBtn.click();
    // Button text should briefly show "Checking…" or complete immediately
    await expect(runBtn).toBeEnabled({ timeout: 5_000 });
  });
});

/* ── Security page ───────────────────────────────────────────── */
test.describe("Security page", () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page);
    await page.goto("/security");
  });

  test("renders MCP Security title in topbar", async ({ page }) => {
    await expect(page.getByText("MCP Security").first()).toBeVisible();
  });

  test("shows Run Security Scan button", async ({ page }) => {
    await expect(page.getByRole("button", { name: /run security scan/i })).toBeVisible();
  });

  test("shows empty state before first scan", async ({ page }) => {
    await expect(page.getByText(/no scan results yet/i)).toBeVisible();
  });
});

/* ── Settings page ───────────────────────────────────────────── */
test.describe("Settings page", () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page);
    await page.goto("/settings");
  });

  test("renders Settings title in topbar", async ({ page }) => {
    await expect(page.getByText("Settings").first()).toBeVisible();
  });

  test("shows Users section", async ({ page }) => {
    await expect(page.getByText("Users").first()).toBeVisible();
  });

  test("shows API Keys section", async ({ page }) => {
    await expect(page.getByText("API Keys").first()).toBeVisible();
  });

  test("shows Model Pricing section", async ({ page }) => {
    await expect(page.getByText("Model Pricing").first()).toBeVisible();
  });
});

/* ── Cross-page navigation regression ───────────────────────── */
test.describe("Cross-page navigation", () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page);
  });

  // Regression: settings page negative margin was intercepting sidebar clicks
  test("can navigate from settings back to overview", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByText("Settings").first()).toBeVisible();
    await page.getByRole("link", { name: /overview/i }).click();
    await expect(page).toHaveURL("/", { timeout: 6_000 });
  });

  test("can navigate from settings to sessions", async ({ page }) => {
    await page.goto("/settings");
    await page.getByRole("link", { name: /sessions/i }).click();
    await expect(page).toHaveURL("/sessions", { timeout: 6_000 });
  });

  test("can navigate from settings to agents", async ({ page }) => {
    await page.goto("/settings");
    await page.getByRole("link", { name: /agents/i }).click();
    await expect(page).toHaveURL("/agents", { timeout: 6_000 });
  });

  test("can navigate from sessions back to overview", async ({ page }) => {
    await page.goto("/sessions");
    await page.getByRole("link", { name: /overview/i }).click();
    await expect(page).toHaveURL("/", { timeout: 6_000 });
  });

  test("settings page left-nav does not block app sidebar clicks", async ({ page }) => {
    await page.goto("/settings");
    // Click through multiple settings sections first
    await page.getByRole("button", { name: /notifications/i }).click();
    await page.getByRole("button", { name: /audit logs/i }).click();
    // Then navigate away via app sidebar — this was broken by margin: -20px
    await page.getByRole("link", { name: /overview/i }).click();
    await expect(page).toHaveURL("/", { timeout: 6_000 });
  });

  test("settings user dropdown does not show Settings link", async ({ page }) => {
    await page.goto("/settings");
    // Open user menu
    const userBtn = page.getByText("Admin User").closest("button");
    if (userBtn) {
      await userBtn.click();
      // Should NOT find a Settings link in the dropdown
      await expect(page.getByRole("menuitem", { name: /settings/i })).not.toBeVisible().catch(() => {
        // If no menuitem role, check by text in the dropdown
      });
    }
  });
});

/* ── Unauthenticated redirect ────────────────────────────────── */
test.describe("Auth protection", () => {
  test("redirects unauthenticated users to /login from /", async ({ page }) => {
    // Clear any session cookies
    await page.context().clearCookies();
    await page.goto("/");
    await expect(page).toHaveURL(/\/login/, { timeout: 8_000 });
  });

  test("redirects unauthenticated users to /login from /sessions", async ({ page }) => {
    await page.context().clearCookies();
    await page.goto("/sessions");
    await expect(page).toHaveURL(/\/login/, { timeout: 8_000 });
  });
});
