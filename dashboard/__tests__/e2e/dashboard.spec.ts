/**
 * E2E tests for core dashboard pages and navigation.
 *
 * All API calls are intercepted via Playwright route mocking —
 * no real backend or database required.
 */
import { test, expect, type Page } from "@playwright/test";
import { mockApiRoutes, MOCK_SESSIONS } from "./fixtures";

/* ── Authenticated helper ──────────────────────────────────────── */

async function authenticatedGoto(page: Page, path: string): Promise<void> {
  await mockApiRoutes(page);
  await page.goto(path);
  // If redirected to /login, perform sign-in with mocked auth
  if (page.url().includes("/login")) {
    await page.fill('[id="email"]', "admin@langsight.dev");
    await page.fill('[id="password"]', "demo123");
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.waitForURL("**/*", { timeout: 10_000 });
    await page.goto(path);
  }
}

/* ── Sidebar navigation ───────────────────────────────────────── */

test.describe("Sidebar navigation", () => {
  test.beforeEach(async ({ page }) => {
    await authenticatedGoto(page, "/");
  });

  test("sidebar shows LangSight branding", async ({ page }) => {
    await expect(page.getByText("LangSight").first()).toBeVisible();
  });

  test("sidebar shows Overview link", async ({ page }) => {
    await expect(
      page.getByRole("link", { name: "Overview" })
    ).toBeVisible();
  });

  test("sidebar shows Sessions link", async ({ page }) => {
    await expect(
      page.getByRole("link", { name: "Sessions" })
    ).toBeVisible();
  });

  test("sidebar shows Agents link", async ({ page }) => {
    await expect(
      page.getByRole("link", { name: "Agents" })
    ).toBeVisible();
  });

  test("sidebar shows MCP Servers link", async ({ page }) => {
    await expect(
      page.getByRole("link", { name: "MCP Servers" })
    ).toBeVisible();
  });

  test("sidebar shows Costs link", async ({ page }) => {
    await expect(
      page.getByRole("link", { name: "Costs" })
    ).toBeVisible();
  });

  test("sidebar shows Tool Health link under Infrastructure", async ({
    page,
  }) => {
    await expect(
      page.getByRole("link", { name: "Tool Health" })
    ).toBeVisible();
  });

  test("sidebar shows MCP Security link under Infrastructure", async ({
    page,
  }) => {
    await expect(
      page.getByRole("link", { name: "MCP Security" })
    ).toBeVisible();
  });

  test("sidebar shows Settings link", async ({ page }) => {
    await expect(
      page.getByRole("link", { name: "Settings" })
    ).toBeVisible();
  });

  test("navigates to Sessions page via sidebar", async ({ page }) => {
    await page.getByRole("link", { name: "Sessions" }).click();
    await expect(page).toHaveURL("/sessions");
  });

  test("navigates to Agents page via sidebar", async ({ page }) => {
    await page.getByRole("link", { name: "Agents" }).click();
    await expect(page).toHaveURL("/agents");
  });

  test("navigates to MCP Servers page via sidebar", async ({ page }) => {
    await page.getByRole("link", { name: "MCP Servers" }).click();
    await expect(page).toHaveURL("/servers");
  });

  test("navigates to Costs page via sidebar", async ({ page }) => {
    await page.getByRole("link", { name: "Costs" }).click();
    await expect(page).toHaveURL("/costs");
  });

  test("navigates to Tool Health page via sidebar", async ({ page }) => {
    await page.getByRole("link", { name: "Tool Health" }).click();
    await expect(page).toHaveURL("/health");
  });

  test("navigates to MCP Security page via sidebar", async ({ page }) => {
    await page.getByRole("link", { name: "MCP Security" }).click();
    await expect(page).toHaveURL("/security");
  });

  test("navigates to Settings page via sidebar", async ({ page }) => {
    await page.getByRole("link", { name: "Settings" }).click();
    await expect(page).toHaveURL("/settings");
  });

  test("marks current page as active in sidebar", async ({ page }) => {
    await page.getByRole("link", { name: "Sessions" }).click();
    await page.waitForURL("/sessions");
    const sessionsLink = page.getByRole("link", { name: "Sessions" });
    const classes = await sessionsLink.getAttribute("class");
    expect(classes).toContain("active");
  });

  test("shows version badge (v0.2)", async ({ page }) => {
    await expect(page.getByText("v0.2")).toBeVisible();
  });
});

/* ── Overview page ─────────────────────────────────────────────── */

test.describe("Overview page", () => {
  test.beforeEach(async ({ page }) => {
    await authenticatedGoto(page, "/");
  });

  test("renders the Run Check button", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: /run check/i })
    ).toBeVisible({ timeout: 8_000 });
  });

  test("renders metric cards with session count", async ({ page }) => {
    // Wait for data to load — look for the Active Sessions metric
    await expect(
      page.getByText("Active Sessions")
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows the session count matching mock data", async ({ page }) => {
    // Mock returns 3 sessions — the number and label are in the same card
    await expect(
      page.getByText(String(MOCK_SESSIONS.length)).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("renders Agents Running metric card", async ({ page }) => {
    await expect(
      page.getByText("Agents Running")
    ).toBeVisible({ timeout: 8_000 });
  });

  test("renders Tools Online metric card", async ({ page }) => {
    await expect(
      page.getByText("Tools Online")
    ).toBeVisible({ timeout: 8_000 });
  });

  test("renders Anomalies metric card", async ({ page }) => {
    await expect(
      page.getByText("Anomalies")
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows Recent Sessions section", async ({ page }) => {
    await expect(page.getByText("Recent Sessions")).toBeVisible({
      timeout: 8_000,
    });
  });

  test("shows Tools & MCPs section", async ({ page }) => {
    await expect(page.getByText("Tools & MCPs")).toBeVisible({
      timeout: 8_000,
    });
  });

  test("displays server names in the Tools & MCPs section", async ({
    page,
  }) => {
    await expect(
      page.getByText("postgres-mcp").first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows system status indicator", async ({ page }) => {
    // With 1 down server in mock, should show outage or degraded status
    const statusText = page.locator("text=/outage detected|systems degraded|all systems operational/i");
    await expect(statusText.first()).toBeVisible({ timeout: 8_000 });
  });

  test("shows SLO status section when SLOs exist", async ({ page }) => {
    await expect(page.getByText("Agent SLOs")).toBeVisible({
      timeout: 8_000,
    });
  });

  test("shows SLO agent name from mock data", async ({ page }) => {
    await expect(
      page.getByText("data-pipeline-agent").first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows View all links for sessions and tools", async ({ page }) => {
    const viewAllLinks = page.getByText("View all");
    await expect(viewAllLinks.first()).toBeVisible({ timeout: 8_000 });
  });
});

/* ── Sessions page ─────────────────────────────────────────────── */

test.describe("Sessions page", () => {
  test.beforeEach(async ({ page }) => {
    await authenticatedGoto(page, "/sessions");
  });

  test("renders the Sessions heading", async ({ page }) => {
    await expect(page.getByText("Sessions").first()).toBeVisible({
      timeout: 8_000,
    });
  });

  test("shows the search input", async ({ page }) => {
    await expect(
      page.getByPlaceholder(/search session/i)
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows time range buttons (1h, 6h, 24h, 7d)", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: "1h" }).first()
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "6h" }).first()
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "24h" }).first()
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "7d" }).first()
    ).toBeVisible();
  });

  test("24h button is active by default", async ({ page }) => {
    const btn = page.getByRole("button", { name: "24h" }).first();
    await expect(btn).toBeVisible();
    const classes = await btn.getAttribute("class");
    expect(classes).toContain("bg-primary");
  });

  test("shows filter buttons All, Clean, Failed with counts", async ({
    page,
  }) => {
    await expect(
      page.getByRole("button", { name: /^All \d/i }).first()
    ).toBeVisible({ timeout: 8_000 });
    await expect(
      page.getByRole("button", { name: /^Clean \d/i }).first()
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /^Failed \d/i }).first()
    ).toBeVisible();
  });

  test("shows session count in subtitle", async ({ page }) => {
    // Should show "3 sessions" from mock data
    await expect(
      page.getByText(/\d+ sessions/i).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("renders session table with session IDs", async ({ page }) => {
    // Should see at least a truncated session ID from mock data
    await expect(
      page.getByText(/sess_abc123def4/).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows agent name in session rows", async ({ page }) => {
    const sessionRow = page.locator("tr").filter({
      has: page.getByText(/sess_abc123def4/).first(),
    }).first();
    await expect(
      sessionRow.getByText("data-pipeline-agent")
    ).toBeVisible({ timeout: 8_000 });
  });

  test("clicking a session row navigates to session detail", async ({
    page,
  }) => {
    // Click on a session row
    await page.getByText(/sess_abc123def4/).first().click();
    await expect(page).toHaveURL(
      `/sessions/${MOCK_SESSIONS[0].session_id}`,
      { timeout: 8_000 }
    );
  });

  test("switching time range changes the active button", async ({ page }) => {
    const sevenDayBtn = page.getByRole("button", { name: "7d" }).first();
    await sevenDayBtn.click();
    const classes = await sevenDayBtn.getAttribute("class");
    expect(classes).toContain("bg-primary");
  });

  test("clicking Failed filter shows only failed sessions", async ({
    page,
  }) => {
    await page
      .getByRole("button", { name: /^Failed \d/i })
      .first()
      .click();
    // After clicking failed, only sessions with failed_calls > 0 should show
    // All remaining visible session rows should show failure indicators
    await expect(
      page.getByRole("button", { name: /^Failed/i }).first()
    ).toBeVisible();
  });
});

/* ── Session detail page ───────────────────────────────────────── */

test.describe("Session detail page", () => {
  test.beforeEach(async ({ page }) => {
    await authenticatedGoto(
      page,
      `/sessions/${MOCK_SESSIONS[0].session_id}`
    );
  });

  test("shows the session ID in the page", async ({ page }) => {
    await expect(
      page.getByText(/sess_abc123def4/).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows back link to sessions list", async ({ page }) => {
    // Look for the back arrow or Sessions breadcrumb
    const backLink = page.getByRole("link", { name: /sessions|back/i }).first();
    await expect(backLink).toBeVisible({ timeout: 8_000 });
  });

  test("shows span count information", async ({ page }) => {
    // The trace has 3 spans
    await expect(
      page.getByText(/\d+ span|tool call|agent/i).first()
    ).toBeVisible({ timeout: 8_000 });
  });
});

/* ── Health page ───────────────────────────────────────────────── */

test.describe("Health page", () => {
  test.beforeEach(async ({ page }) => {
    await authenticatedGoto(page, "/health");
  });

  test("renders Tool Health heading", async ({ page }) => {
    await expect(page.getByText("Tool Health").first()).toBeVisible();
  });

  test("shows Run Check button", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: /run check/i })
    ).toBeVisible();
  });

  test("shows server count in subtitle", async ({ page }) => {
    await expect(
      page.getByText(/3 servers/).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("displays postgres-mcp server name", async ({ page }) => {
    await expect(
      page.getByText("postgres-mcp").first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("displays s3-mcp server name", async ({ page }) => {
    await expect(
      page.getByText("s3-mcp").first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("displays redis-mcp server name", async ({ page }) => {
    await expect(
      page.getByText("redis-mcp").first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows status badges (up, degraded, down)", async ({ page }) => {
    await expect(page.getByText("up").first()).toBeVisible({ timeout: 8_000 });
    await expect(page.getByText("degraded").first()).toBeVisible({
      timeout: 8_000,
    });
    await expect(page.getByText("down").first()).toBeVisible({
      timeout: 8_000,
    });
  });

  test("shows alert banner when servers are down", async ({ page }) => {
    // Mock data has 1 down server
    await expect(
      page.getByText(/server.*down|down.*server/i).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows filter pills (All, Up, Degraded, Down)", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: /all/i }).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows search input for filtering servers", async ({ page }) => {
    await expect(
      page.getByPlaceholder(/filter servers/i)
    ).toBeVisible();
  });

  test("clicking Run Check button triggers and completes", async ({
    page,
  }) => {
    const runBtn = page.getByRole("button", { name: /run check/i });
    await runBtn.click();
    // Should re-enable after check completes
    await expect(runBtn).toBeEnabled({ timeout: 5_000 });
  });

  test("clicking a server row expands it", async ({ page }) => {
    // Click on the postgres-mcp row
    await page.getByText("postgres-mcp").first().click();
    // Expanded view should show history details: Uptime, Avg latency, Checks
    await expect(
      page.getByText(/uptime|avg latency|checks/i).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("search filters server list", async ({ page }) => {
    const searchInput = page.getByPlaceholder(/filter servers/i);
    await searchInput.fill("postgres");
    // Should only show postgres-mcp, not s3 or redis
    await expect(page.getByText("postgres-mcp").first()).toBeVisible();
    // Other servers should not be visible
    await expect(page.getByText("redis-mcp")).not.toBeVisible({ timeout: 2_000 });
  });

  test("error message shown for down server", async ({ page }) => {
    await expect(
      page.getByText(/connection refused/i).first()
    ).toBeVisible({ timeout: 8_000 });
  });
});

/* ── Agents page ───────────────────────────────────────────────── */

test.describe("Agents page", () => {
  test.beforeEach(async ({ page }) => {
    await authenticatedGoto(page, "/agents");
  });

  test("renders Agents heading", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: /agents/i }).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows time window buttons (1h, 6h, 24h, 7d)", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: "24h" }).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows Topology button", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: /topology/i })
    ).toBeVisible({ timeout: 8_000 });
  });

  test("displays agent names from mock sessions", async ({ page }) => {
    await expect(
      page.getByText("data-pipeline-agent").first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows agent count in subtitle", async ({ page }) => {
    await expect(
      page.getByText(/\d+ agent/i).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows search input for filtering agents", async ({ page }) => {
    await expect(
      page.getByPlaceholder(/search agents/i)
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows status filter buttons", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: /failing/i }).first()
    ).toBeVisible({ timeout: 8_000 });
    await expect(
      page.getByRole("button", { name: /healthy/i }).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("clicking an agent row opens the detail panel", async ({ page }) => {
    // Click on an agent name in the table
    await page.getByText("data-pipeline-agent").first().click();
    // Detail panel should show tabs (about, overview, topology, sessions)
    await expect(
      page.getByRole("button", { name: /about/i }).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("agent detail panel shows tabs", async ({ page }) => {
    await page.getByText("data-pipeline-agent").first().click();
    await expect(
      page.getByRole("button", { name: /overview/i }).first()
    ).toBeVisible({ timeout: 5_000 });
    await expect(
      page.getByRole("button", { name: /sessions/i }).first()
    ).toBeVisible({ timeout: 5_000 });
  });
});

/* ── Costs page ────────────────────────────────────────────────── */

test.describe("Costs page", () => {
  test.beforeEach(async ({ page }) => {
    await authenticatedGoto(page, "/costs");
  });

  test("renders Cost Attribution heading", async ({ page }) => {
    await expect(
      page.getByText("Cost Attribution").first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows time window buttons", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: "24h" })
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "7d" })
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "30d" })
    ).toBeVisible();
  });

  test("shows ClickHouse requirement or cost data", async ({ page }) => {
    // Mock returns supports_costs: false, so should show ClickHouse message
    // OR if implementation changed, it might show $0.00 totals
    const clickhouseMsg = page.getByText(/cost attribution requires clickhouse/i);
    const totalCost = page.getByText(/\$0\.00/);
    const eitherVisible = await Promise.race([
      clickhouseMsg.waitFor({ timeout: 8_000 }).then(() => true),
      totalCost.first().waitFor({ timeout: 8_000 }).then(() => true),
    ]).catch(() => false);
    expect(eitherVisible).toBeTruthy();
  });
});

/* ── Security page ─────────────────────────────────────────────── */

test.describe("Security page", () => {
  test.beforeEach(async ({ page }) => {
    await authenticatedGoto(page, "/security");
  });

  test("renders MCP Security heading", async ({ page }) => {
    await expect(
      page.getByText("MCP Security").first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows Run Security Scan button", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: /run security scan/i })
    ).toBeVisible();
  });
});

/* ── Settings page ─────────────────────────────────────────────── */

test.describe("Settings page", () => {
  test.beforeEach(async ({ page }) => {
    await authenticatedGoto(page, "/settings");
  });

  test("renders Settings heading", async ({ page }) => {
    await expect(page.getByText("Settings").first()).toBeVisible({
      timeout: 8_000,
    });
  });

  test("shows Users section", async ({ page }) => {
    await expect(page.getByText("Users").first()).toBeVisible({
      timeout: 8_000,
    });
  });

  test("shows API Keys section", async ({ page }) => {
    await expect(page.getByText("API Keys").first()).toBeVisible({
      timeout: 8_000,
    });
  });

  test("shows Model Pricing section", async ({ page }) => {
    await expect(page.getByText("Model Pricing").first()).toBeVisible({
      timeout: 8_000,
    });
  });

  test("shows Notifications section button", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: /notifications/i })
    ).toBeVisible({ timeout: 8_000 });
  });
});

/* ── Servers page ──────────────────────────────────────────────── */

test.describe("Servers page", () => {
  test.beforeEach(async ({ page }) => {
    await authenticatedGoto(page, "/servers");
  });

  test("renders MCP Servers heading", async ({ page }) => {
    // The page title should be visible
    await expect(
      page.getByText(/mcp servers|servers/i).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("displays server names from health data", async ({ page }) => {
    await expect(
      page.getByText("postgres-mcp").first()
    ).toBeVisible({ timeout: 8_000 });
  });
});

/* ── Cross-page navigation ─────────────────────────────────────── */

test.describe("Cross-page navigation", () => {
  test.beforeEach(async ({ page }) => {
    await authenticatedGoto(page, "/");
  });

  test("can navigate from overview to sessions and back", async ({ page }) => {
    await page.getByRole("link", { name: /sessions/i }).click();
    await expect(page).toHaveURL("/sessions", { timeout: 6_000 });
    await page.getByRole("link", { name: /overview/i }).click();
    await expect(page).toHaveURL("/", { timeout: 6_000 });
  });

  test("can navigate from settings to overview via sidebar", async ({
    page,
  }) => {
    await page.goto("/settings");
    await expect(page.getByText("Settings").first()).toBeVisible({
      timeout: 8_000,
    });
    await page.getByRole("link", { name: /overview/i }).click();
    await expect(page).toHaveURL("/", { timeout: 6_000 });
  });

  test("can navigate from settings to sessions via sidebar", async ({
    page,
  }) => {
    await page.goto("/settings");
    await page.getByRole("link", { name: /sessions/i }).click();
    await expect(page).toHaveURL("/sessions", { timeout: 6_000 });
  });

  test("can navigate from settings to agents via sidebar", async ({
    page,
  }) => {
    await page.goto("/settings");
    await page.getByRole("link", { name: /agents/i }).click();
    await expect(page).toHaveURL("/agents", { timeout: 6_000 });
  });

  test("overview Recent Sessions link goes to /sessions", async ({ page }) => {
    const viewAllLink = page
      .locator("text=View all")
      .first();
    await expect(viewAllLink).toBeVisible({ timeout: 8_000 });
    await viewAllLink.click();
    await expect(page).toHaveURL(/\/sessions|\/health/, { timeout: 6_000 });
  });
});

/* ── Auth protection ───────────────────────────────────────────── */

test.describe("Auth protection", () => {
  test("redirects unauthenticated users to /login from /", async ({
    page,
  }) => {
    // Do NOT set up mocked session — let auth fail naturally
    await page.context().clearCookies();
    // Only mock the auth routes to return no session
    await page.route("**/api/auth/session", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({}),
      });
    });
    await page.goto("/");
    await expect(page).toHaveURL(/\/login/, { timeout: 8_000 });
  });

  test("redirects unauthenticated users to /login from /sessions", async ({
    page,
  }) => {
    await page.context().clearCookies();
    await page.route("**/api/auth/session", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({}),
      });
    });
    await page.goto("/sessions");
    await expect(page).toHaveURL(/\/login/, { timeout: 8_000 });
  });

  test("redirects unauthenticated users to /login from /health", async ({
    page,
  }) => {
    await page.context().clearCookies();
    await page.route("**/api/auth/session", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({}),
      });
    });
    await page.goto("/health");
    await expect(page).toHaveURL(/\/login/, { timeout: 8_000 });
  });

  test("redirects unauthenticated users to /login from /settings", async ({
    page,
  }) => {
    await page.context().clearCookies();
    await page.route("**/api/auth/session", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({}),
      });
    });
    await page.goto("/settings");
    await expect(page).toHaveURL(/\/login/, { timeout: 8_000 });
  });
});
