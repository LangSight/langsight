/**
 * E2E tests for the Overview / dashboard page (/).
 *
 * Covers:
 *   - Metric cards (Active Sessions, Agents Running, Tools Online, Anomalies)
 *   - Recent Sessions section with session rows
 *   - Tools & MCPs section with server status indicators
 *   - SLO Status section
 *   - System status indicator (All Systems Operational / Outage / Degraded)
 *   - Run Check button behavior
 *   - Empty states when no data
 *
 * All API calls intercepted — no real backend required.
 */
import { test, expect, type Page, type Route } from "@playwright/test";
import {
  mockApiRoutes,
  MOCK_SESSIONS,
  MOCK_HEALTH_SERVERS,
  MOCK_ANOMALIES,
} from "./fixtures";

/* ── Authenticated helper ──────────────────────────────────────── */

async function gotoOverview(page: Page): Promise<void> {
  await mockApiRoutes(page);
  await page.goto("/");
  if (page.url().includes("/login")) {
    await page.fill('[id="email"]', "admin@langsight.dev");
    await page.fill('[id="password"]', "demo123");
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.waitForURL("/", { timeout: 10_000 });
  }
}

/* ── Metric cards ──────────────────────────────────────────────── */

test.describe("Overview — metric cards", () => {
  test.beforeEach(async ({ page }) => {
    await gotoOverview(page);
  });

  test("shows Active Sessions card", async ({ page }) => {
    await expect(
      page.getByText("Active Sessions")
    ).toBeVisible({ timeout: 8_000 });
  });

  test("Active Sessions shows correct count from mock data", async ({
    page,
  }) => {
    // 3 sessions in mock
    await expect(
      page.getByText(String(MOCK_SESSIONS.length))
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows Agents Running card", async ({ page }) => {
    await expect(
      page.getByText("Agents Running")
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows Tools Online card", async ({ page }) => {
    await expect(
      page.getByText("Tools Online")
    ).toBeVisible({ timeout: 8_000 });
  });

  test("Tools Online shows up/total ratio", async ({ page }) => {
    // 1 up out of 3 total
    await expect(
      page.getByText("1/3")
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows Anomalies card", async ({ page }) => {
    await expect(
      page.getByText("Anomalies")
    ).toBeVisible({ timeout: 8_000 });
  });

  test("Anomalies shows count from mock data", async ({ page }) => {
    // 1 anomaly in mock
    await expect(
      page.getByText(String(MOCK_ANOMALIES.length)).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("Active Sessions card links to /sessions", async ({ page }) => {
    await page.getByText("Active Sessions").waitFor({ timeout: 8_000 });
    const card = page.locator("a[href='/sessions']").first();
    await expect(card).toBeVisible();
  });

  test("Tools Online card links to /health", async ({ page }) => {
    await page.getByText("Tools Online").waitFor({ timeout: 8_000 });
    const card = page.locator("a[href='/health']").first();
    await expect(card).toBeVisible();
  });
});

/* ── System status indicator ───────────────────────────────────── */

test.describe("Overview — system status", () => {
  test("shows Outage Detected when servers are down", async ({ page }) => {
    await gotoOverview(page);
    // Mock has 1 down server, so "Outage Detected" should show
    await expect(
      page.getByText("Outage Detected").first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows All Systems Operational when all servers are up", async ({
    page,
  }) => {
    await mockApiRoutes(page);
    // Override to all healthy
    await page.route("**/api/health/servers", async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          MOCK_HEALTH_SERVERS.map((s) => ({
            ...s,
            status: "up",
            latency_ms: 42,
            error: null,
          }))
        ),
      });
    });
    await page.route("**/api/proxy/health/servers", async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          MOCK_HEALTH_SERVERS.map((s) => ({
            ...s,
            status: "up",
            latency_ms: 42,
            error: null,
          }))
        ),
      });
    });

    await page.goto("/");
    if (page.url().includes("/login")) {
      await page.fill('[id="email"]', "admin@langsight.dev");
      await page.fill('[id="password"]', "demo123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("/", { timeout: 10_000 });
    }

    await expect(
      page.getByText("All Systems Operational").first()
    ).toBeVisible({ timeout: 8_000 });
  });
});

/* ── Recent Sessions section ───────────────────────────────────── */

test.describe("Overview — Recent Sessions", () => {
  test.beforeEach(async ({ page }) => {
    await gotoOverview(page);
  });

  test("shows Recent Sessions heading", async ({ page }) => {
    await expect(
      page.getByText("Recent Sessions")
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows View all link", async ({ page }) => {
    await expect(
      page.getByText("View all").first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("displays session rows with agent names", async ({ page }) => {
    await expect(
      page.getByText("data-pipeline-agent").first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows clean badge for successful sessions", async ({ page }) => {
    await expect(
      page.getByText("clean").first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows failed badge for sessions with failures", async ({ page }) => {
    await expect(
      page.getByText(/\d+ failed/).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("session rows are clickable links", async ({ page }) => {
    await page.getByText("data-pipeline-agent").first().waitFor({ timeout: 8_000 });
    // Find a session link
    const sessionLink = page.locator("a[href^='/sessions/sess_']").first();
    await expect(sessionLink).toBeVisible();
  });
});

/* ── Tools & MCPs section ──────────────────────────────────────── */

test.describe("Overview — Tools & MCPs", () => {
  test.beforeEach(async ({ page }) => {
    await gotoOverview(page);
  });

  test("shows Tools & MCPs heading", async ({ page }) => {
    await expect(
      page.getByText("Tools & MCPs")
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows server names", async ({ page }) => {
    await expect(
      page.getByText("postgres-mcp").first()
    ).toBeVisible({ timeout: 8_000 });
    await expect(
      page.getByText("s3-mcp").first()
    ).toBeVisible();
  });

  test("shows tool count for servers", async ({ page }) => {
    // postgres-mcp has 5 tools
    await expect(
      page.getByText(/5 tools/).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("server rows link to /health", async ({ page }) => {
    await page.getByText("postgres-mcp").first().waitFor({ timeout: 8_000 });
    const healthLink = page.locator("a[href='/health']").first();
    await expect(healthLink).toBeVisible();
  });
});

/* ── SLO Status section ────────────────────────────────────────── */

test.describe("Overview — SLO Status", () => {
  test.beforeEach(async ({ page }) => {
    await gotoOverview(page);
  });

  test("shows Agent SLOs heading", async ({ page }) => {
    await expect(
      page.getByText("Agent SLOs")
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows meeting target count", async ({ page }) => {
    // Both SLOs are "ok", so should show 2/2
    await expect(
      page.getByText(/2\/2 meeting target/).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows SLO agent name", async ({ page }) => {
    await expect(
      page.getByText("data-pipeline-agent").first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows SLO metric type (Success Rate)", async ({ page }) => {
    await expect(
      page.getByText(/success rate/i).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows SLO current value", async ({ page }) => {
    // data-pipeline-agent SLO: current_value 99.5%
    await expect(
      page.getByText("99.5%").first()
    ).toBeVisible({ timeout: 8_000 });
  });
});

/* ── Run Check button ──────────────────────────────────────────── */

test.describe("Overview — Run Check", () => {
  test("Run Check button is visible", async ({ page }) => {
    await gotoOverview(page);
    await expect(
      page.getByRole("button", { name: /run check/i })
    ).toBeVisible({ timeout: 8_000 });
  });

  test("clicking Run Check triggers health check and remains enabled after", async ({
    page,
  }) => {
    await gotoOverview(page);
    const btn = page.getByRole("button", { name: /run check/i });
    await btn.click();
    await expect(btn).toBeEnabled({ timeout: 5_000 });
  });
});

/* ── Empty states ──────────────────────────────────────────────── */

test.describe("Overview — empty state", () => {
  test("shows empty session message when no sessions", async ({ page }) => {
    await mockApiRoutes(page);

    await page.route("**/api/proxy/agents/sessions*", async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });
    await page.route("**/api/agents/sessions*", async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await page.goto("/");
    if (page.url().includes("/login")) {
      await page.fill('[id="email"]', "admin@langsight.dev");
      await page.fill('[id="password"]', "demo123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("/", { timeout: 10_000 });
    }

    await expect(
      page.getByText(/no sessions yet/i).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows empty tools message when no servers configured", async ({
    page,
  }) => {
    await mockApiRoutes(page);

    await page.route("**/api/proxy/health/servers", async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });
    await page.route("**/api/health/servers", async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await page.goto("/");
    if (page.url().includes("/login")) {
      await page.fill('[id="email"]', "admin@langsight.dev");
      await page.fill('[id="password"]', "demo123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("/", { timeout: 10_000 });
    }

    await expect(
      page.getByText(/no tools configured/i).first()
    ).toBeVisible({ timeout: 8_000 });
  });
});
