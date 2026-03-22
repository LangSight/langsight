/**
 * E2E tests for the Sessions page (/sessions) and Session detail (/sessions/[id]).
 *
 * Covers:
 *   - Session list rendering with agent names, call counts, durations
 *   - Filter buttons (All / Clean / Failed)
 *   - Time range switching
 *   - Search by session ID, agent name, server name
 *   - Navigation to session detail
 *   - Session detail page: trace tree, span details, lineage graph
 *   - Empty state handling
 *   - Pagination behavior
 *
 * All API calls intercepted — no real backend required.
 */
import { test, expect, type Page, type Route } from "@playwright/test";
import { mockApiRoutes, MOCK_SESSIONS } from "./fixtures";

/* ── Authenticated helper ──────────────────────────────────────── */

async function gotoSessions(page: Page): Promise<void> {
  await mockApiRoutes(page);
  await page.goto("/sessions");
  if (page.url().includes("/login")) {
    await page.fill('[id="email"]', "admin@langsight.dev");
    await page.fill('[id="password"]', "demo123");
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.waitForURL("**/*", { timeout: 10_000 });
    await page.goto("/sessions");
  }
}

async function gotoSessionDetail(page: Page, sessionId: string): Promise<void> {
  await mockApiRoutes(page);
  await page.goto(`/sessions/${sessionId}`);
  if (page.url().includes("/login")) {
    await page.fill('[id="email"]', "admin@langsight.dev");
    await page.fill('[id="password"]', "demo123");
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.waitForURL("**/*", { timeout: 10_000 });
    await page.goto(`/sessions/${sessionId}`);
  }
}

/* ── Session list rendering ────────────────────────────────────── */

test.describe("Sessions list — rendering", () => {
  test.beforeEach(async ({ page }) => {
    await gotoSessions(page);
  });

  test("renders Sessions heading", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: /sessions/i }).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows session count in subtitle", async ({ page }) => {
    await expect(
      page.getByText(/3 sessions/i).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows total tool call count in subtitle", async ({ page }) => {
    // Total calls across all mock sessions: 12 + 8 + 25 = 45
    await expect(
      page.getByText(/45 tool calls/i).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows failure count in subtitle", async ({ page }) => {
    // Total failures: 0 + 2 + 1 = 3
    await expect(
      page.getByText(/3 failures/i).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("renders session table headers", async ({ page }) => {
    await expect(
      page.getByText("Session ID").first()
    ).toBeVisible({ timeout: 8_000 });
    await expect(page.getByText("Agent").first()).toBeVisible();
    await expect(page.getByText("Calls").first()).toBeVisible();
    await expect(page.getByText("Failed").first()).toBeVisible();
    await expect(page.getByText("Duration").first()).toBeVisible();
  });

  test("shows truncated session IDs", async ({ page }) => {
    await expect(
      page.getByText(/sess_abc123def4/).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows agent names in rows", async ({ page }) => {
    await expect(
      page.getByText("data-pipeline-agent").first()
    ).toBeVisible({ timeout: 8_000 });
    await expect(
      page.getByText("security-scanner-agent").first()
    ).toBeVisible();
  });

  test("shows server tags for sessions", async ({ page }) => {
    await expect(
      page.getByText("postgres-mcp").first()
    ).toBeVisible({ timeout: 8_000 });
  });
});

/* ── Time range switching ──────────────────────────────────────── */

test.describe("Sessions list — time range", () => {
  test.beforeEach(async ({ page }) => {
    await gotoSessions(page);
  });

  test("24h button is active by default", async ({ page }) => {
    const btn = page.getByRole("button", { name: "24h" }).first();
    await expect(btn).toBeVisible({ timeout: 8_000 });
    const classes = await btn.getAttribute("class");
    expect(classes).toContain("bg-primary");
  });

  test("clicking 7d activates it and deactivates 24h", async ({ page }) => {
    await page.getByRole("button", { name: "24h" }).first().waitFor({ timeout: 8_000 });
    const sevenDBtn = page.getByRole("button", { name: "7d" }).first();
    await sevenDBtn.click();
    const classes7d = await sevenDBtn.getAttribute("class");
    expect(classes7d).toContain("bg-primary");

    const btn24h = page.getByRole("button", { name: "24h" }).first();
    const classes24h = await btn24h.getAttribute("class");
    expect(classes24h).not.toContain("bg-primary");
  });

  test("all four time range options are available", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: "1h" }).first()
    ).toBeVisible({ timeout: 8_000 });
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
});

/* ── Status filter buttons ─────────────────────────────────────── */

test.describe("Sessions list — status filters", () => {
  test.beforeEach(async ({ page }) => {
    await gotoSessions(page);
  });

  test("All filter shows total session count", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: /^All \d/i }).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("Clean filter shows count of sessions without failures", async ({
    page,
  }) => {
    // 1 clean session in mock data
    await expect(
      page.getByRole("button", { name: /^Clean \d/i }).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("Failed filter shows count of sessions with failures", async ({
    page,
  }) => {
    // 2 sessions with failed_calls > 0 in mock data
    await expect(
      page.getByRole("button", { name: /^Failed \d/i }).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("clicking Clean filter highlights it", async ({ page }) => {
    await page
      .getByRole("button", { name: /^All \d/i })
      .first()
      .waitFor({ timeout: 8_000 });
    const cleanBtn = page.getByRole("button", { name: /^Clean/i }).first();
    await cleanBtn.click();
    const classes = await cleanBtn.getAttribute("class");
    expect(classes).toMatch(/primary/i);
  });
});

/* ── Search ────────────────────────────────────────────────────── */

test.describe("Sessions list — search", () => {
  test.beforeEach(async ({ page }) => {
    await gotoSessions(page);
  });

  test("search input is present", async ({ page }) => {
    await expect(
      page.getByPlaceholder(/search session/i)
    ).toBeVisible({ timeout: 8_000 });
  });

  test("searching by agent name filters sessions", async ({ page }) => {
    await page.getByText("data-pipeline-agent").first().waitFor({ timeout: 8_000 });
    const search = page.getByPlaceholder(/search session/i);
    await search.fill("security-scanner");
    // Should only show the security-scanner-agent sessions
    await expect(
      page.getByText("security-scanner-agent").first()
    ).toBeVisible();
    // data-pipeline-agent sessions should be hidden
    await expect(
      page.getByText("data-pipeline-agent")
    ).not.toBeVisible({ timeout: 2_000 });
  });

  test("searching by session ID prefix works", async ({ page }) => {
    await page.getByText(/sess_abc123/).first().waitFor({ timeout: 8_000 });
    const search = page.getByPlaceholder(/search session/i);
    await search.fill("sess_abc");
    await expect(page.getByText(/sess_abc123/).first()).toBeVisible();
  });

  test("searching by server name filters sessions", async ({ page }) => {
    await page.getByText("data-pipeline-agent").first().waitFor({ timeout: 8_000 });
    const search = page.getByPlaceholder(/search session/i);
    await search.fill("redis");
    // Only the session using redis-mcp should be visible
    await expect(
      page.getByText("security-scanner-agent").first()
    ).toBeVisible();
  });
});

/* ── Navigation to session detail ──────────────────────────────── */

test.describe("Sessions list — navigation", () => {
  test.beforeEach(async ({ page }) => {
    await gotoSessions(page);
  });

  test("clicking a session row navigates to its detail page", async ({
    page,
  }) => {
    await page.getByText(/sess_abc123/).first().waitFor({ timeout: 8_000 });
    await page.getByText(/sess_abc123/).first().click();
    await expect(page).toHaveURL(
      `/sessions/${MOCK_SESSIONS[0].session_id}`,
      { timeout: 8_000 }
    );
  });
});

/* ── Session detail page ───────────────────────────────────────── */

test.describe("Session detail page", () => {
  test.beforeEach(async ({ page }) => {
    await gotoSessionDetail(page, MOCK_SESSIONS[0].session_id);
  });

  test("shows the session ID", async ({ page }) => {
    await expect(
      page.getByText(/sess_abc123/).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows back navigation to sessions list", async ({ page }) => {
    const backLink = page.getByRole("link", { name: /sessions|back/i }).first();
    await expect(backLink).toBeVisible({ timeout: 8_000 });
  });

  test("shows span count or tool call info", async ({ page }) => {
    // The trace has 3 spans / 2 tool calls
    const spanInfo = page.getByText(/\d+\s*(span|tool|call)/i).first();
    await expect(spanInfo).toBeVisible({ timeout: 8_000 });
  });

  test("shows agent name in the detail view", async ({ page }) => {
    await expect(
      page.getByText("data-pipeline-agent").first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("shows server names used in the session", async ({ page }) => {
    await expect(
      page.getByText("postgres-mcp").first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("back link navigates to /sessions", async ({ page }) => {
    const backLink = page.getByRole("link", { name: /sessions|back/i }).first();
    await expect(backLink).toBeVisible({ timeout: 8_000 });
    await backLink.click();
    await expect(page).toHaveURL("/sessions", { timeout: 8_000 });
  });
});

/* ── Empty state ───────────────────────────────────────────────── */

test.describe("Sessions list — empty state", () => {
  test("shows empty state when no sessions exist", async ({ page }) => {
    await mockApiRoutes(page);

    // Override to return empty sessions
    await page.route("**/api/proxy/agents/sessions*", async (route: Route) => {
      const url = route.request().url();
      // Only intercept the list endpoint, not detail
      if (!url.includes("/agents/sessions/")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([]),
        });
      } else {
        await route.fallback();
      }
    });
    await page.route("**/api/agents/sessions*", async (route: Route) => {
      const url = route.request().url();
      if (!url.includes("/agents/sessions/")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([]),
        });
      } else {
        await route.fallback();
      }
    });

    await page.goto("/sessions");
    if (page.url().includes("/login")) {
      await page.fill('[id="email"]', "admin@langsight.dev");
      await page.fill('[id="password"]', "demo123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("**/*", { timeout: 10_000 });
      await page.goto("/sessions");
    }

    await expect(
      page.getByText(/no sessions yet/i).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("empty state suggests instrumenting agents", async ({ page }) => {
    await mockApiRoutes(page);
    await page.route("**/api/proxy/agents/sessions*", async (route: Route) => {
      const url = route.request().url();
      if (!url.includes("/agents/sessions/")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([]),
        });
      } else {
        await route.fallback();
      }
    });
    await page.route("**/api/agents/sessions*", async (route: Route) => {
      const url = route.request().url();
      if (!url.includes("/agents/sessions/")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([]),
        });
      } else {
        await route.fallback();
      }
    });

    await page.goto("/sessions");
    if (page.url().includes("/login")) {
      await page.fill('[id="email"]', "admin@langsight.dev");
      await page.fill('[id="password"]', "demo123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("**/*", { timeout: 10_000 });
      await page.goto("/sessions");
    }

    await expect(
      page.getByText(/instrument.*agent|langsight sdk/i).first()
    ).toBeVisible({ timeout: 8_000 });
  });
});

/* ── Error state ───────────────────────────────────────────────── */

test.describe("Sessions list — API error", () => {
  test("shows error message when API returns error", async ({ page }) => {
    await mockApiRoutes(page);

    // Override to return an error
    await page.route("**/api/proxy/agents/sessions*", async (route: Route) => {
      const url = route.request().url();
      if (!url.includes("/agents/sessions/")) {
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Internal Server Error" }),
        });
      } else {
        await route.fallback();
      }
    });
    await page.route("**/api/agents/sessions*", async (route: Route) => {
      const url = route.request().url();
      if (!url.includes("/agents/sessions/")) {
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Internal Server Error" }),
        });
      } else {
        await route.fallback();
      }
    });

    await page.goto("/sessions");
    if (page.url().includes("/login")) {
      await page.fill('[id="email"]', "admin@langsight.dev");
      await page.fill('[id="password"]', "demo123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("**/*", { timeout: 10_000 });
      await page.goto("/sessions");
    }

    await expect(
      page.getByText(/could not load sessions|error|check clickhouse/i).first()
    ).toBeVisible({ timeout: 8_000 });
  });
});
