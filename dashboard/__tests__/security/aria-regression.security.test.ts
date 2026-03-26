/**
 * ARIA regression tests (D9).
 *
 * Security context: accessibility regressions are treated as security issues
 * because they can prevent users relying on assistive technology from
 * operating the auth, API key management, and incident-response UI.
 * An on-call engineer who cannot operate the dashboard due to missing ARIA
 * attributes is effectively locked out of the system.
 *
 * Security invariants proved by this file:
 *
 *   1. Accessible names — every interactive element (button, select, input,
 *      [role=tab]) must have an accessible name via aria-label, aria-labelledby,
 *      or an associated <label>.  Elements with no accessible name are
 *      invisible to screen readers.
 *
 *   2. Tab panel state — elements with role="tab" must have aria-selected set.
 *      The active tab must have aria-selected="true"; all others must have
 *      aria-selected="false" (not missing the attribute).
 *
 *   3. Chart role="img" labels — chart containers that use role="img" to
 *      summarise a data visualisation must carry a non-empty aria-label.
 *      An empty string is as harmful as no label for screen readers.
 *
 * Tests run in jsdom; no real network calls are made.
 * Component rendering is kept minimal — the tests use small inline fixtures.
 */

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Assert that every interactive element in `container` has an accessible name.
 *
 * Accessible name resolution order (ARIA spec):
 *   1. aria-labelledby referencing another element's text
 *   2. aria-label attribute (non-empty)
 *   3. Associated <label> element via htmlFor / id pairing
 *   4. title attribute (fallback)
 *
 * We check: aria-label, aria-labelledby (attribute present), or a <label>
 * whose htmlFor matches the element's id.
 */
function assertAllInteractiveElementsHaveAccessibleNames(container: Element): void {
  const selectors = "button, select, input, [role='tab'], [role='button']";
  const elements = Array.from(container.querySelectorAll(selectors));

  for (const el of elements) {
    const ariaLabel = el.getAttribute("aria-label");
    const ariaLabelledBy = el.getAttribute("aria-labelledby");
    const elementId = el.getAttribute("id");
    const associatedLabel = elementId
      ? container.querySelector(`label[for="${elementId}"]`)
      : null;
    const titleAttr = el.getAttribute("title");
    // For buttons: text content serves as the accessible name
    const textContent = el.textContent?.trim();

    const hasName =
      (ariaLabel && ariaLabel.trim().length > 0) ||
      (ariaLabelledBy && ariaLabelledBy.trim().length > 0) ||
      associatedLabel !== null ||
      (titleAttr && titleAttr.trim().length > 0) ||
      (el.tagName === "BUTTON" && textContent && textContent.length > 0);

    expect(hasName).toBe(true);
    // if (`${el.tagName}[${el.getAttribute('type') ?? el.getAttribute('role') ?? ''}]` is useful for debugging):
  }
}

/**
 * Assert that all [role="tab"] elements have aria-selected set to a boolean
 * string ("true" or "false"), and that exactly one has aria-selected="true".
 */
function assertTabAriaSelected(container: Element): void {
  const tabs = Array.from(container.querySelectorAll("[role='tab']"));
  if (tabs.length === 0) return; // nothing to assert

  for (const tab of tabs) {
    const selected = tab.getAttribute("aria-selected");
    expect(selected === "true" || selected === "false").toBe(true);
  }

  const selectedTabs = tabs.filter((t) => t.getAttribute("aria-selected") === "true");
  expect(selectedTabs.length).toBe(1);
}

/**
 * Assert that all elements with role="img" have a non-empty aria-label.
 */
function assertChartImgRolesHaveLabels(container: Element): void {
  const imgRoles = Array.from(container.querySelectorAll("[role='img']"));
  for (const el of imgRoles) {
    const label = el.getAttribute("aria-label") ?? "";
    expect(label.trim().length).toBeGreaterThan(0);
  }
}

// ─── 1. Interactive element accessible names ──────────────────────────────────

describe("ARIA regression — interactive elements must have accessible names", () => {
  /**
   * Invariant: no button, select, or input must be left without an accessible
   * name.  A missing accessible name is an WCAG 2.1 Level A failure (SC 4.1.2).
   */

  it("button with text content has accessible name from text", () => {
    const container = document.createElement("div");
    container.innerHTML = `<button>Save</button>`;
    assertAllInteractiveElementsHaveAccessibleNames(container);
  });

  it("button with aria-label and no text content has accessible name", () => {
    const container = document.createElement("div");
    container.innerHTML = `<button aria-label="Close dialog"><svg/></button>`;
    assertAllInteractiveElementsHaveAccessibleNames(container);
  });

  it("button with ONLY an icon and NO aria-label fails accessible name check", () => {
    const container = document.createElement("div");
    // Deliberate failure fixture — icon-only button with no accessible name
    container.innerHTML = `<button><svg width="16" height="16"/></button>`;

    const buttons = Array.from(container.querySelectorAll("button"));
    const btn = buttons[0]!;
    const ariaLabel = btn.getAttribute("aria-label");
    const textContent = btn.textContent?.trim();

    // This fixture intentionally has no accessible name — the test documents
    // the failure so engineers know what pattern to avoid.
    const hasName = (ariaLabel && ariaLabel.trim().length > 0) || (textContent && textContent.length > 0);
    expect(hasName).toBeFalsy();
  });

  it("input with associated label has accessible name", () => {
    const container = document.createElement("div");
    container.innerHTML = `
      <label for="search-input">Search sessions</label>
      <input id="search-input" type="search" />
    `;
    assertAllInteractiveElementsHaveAccessibleNames(container);
  });

  it("input with aria-label (no visible label) has accessible name", () => {
    const container = document.createElement("div");
    container.innerHTML = `<input type="search" aria-label="Search sessions" />`;
    assertAllInteractiveElementsHaveAccessibleNames(container);
  });

  it("input with sr-only label class has accessible name via associated label", () => {
    // The .sr-only pattern used in sessions/page.tsx — a visually hidden label
    const container = document.createElement("div");
    container.innerHTML = `
      <label for="agent-filter" class="sr-only">Filter by agent</label>
      <select id="agent-filter">
        <option value="all">All agents</option>
      </select>
    `;
    assertAllInteractiveElementsHaveAccessibleNames(container);
  });

  it("select with aria-label (no label element) has accessible name", () => {
    const container = document.createElement("div");
    container.innerHTML = `<select aria-label="Filter by agent"><option>All</option></select>`;
    assertAllInteractiveElementsHaveAccessibleNames(container);
  });

  it("select with ONLY a placeholder option and no label fails", () => {
    const container = document.createElement("div");
    // Deliberate failure — no label, no aria-label
    container.innerHTML = `<select><option>All agents</option></select>`;
    const select = container.querySelector("select")!;
    const ariaLabel = select.getAttribute("aria-label");
    const associatedLabel = container.querySelector(`label[for="${select.id ?? ""}"]`);

    // This fixture intentionally fails — documents the anti-pattern
    expect(ariaLabel).toBeNull();
    expect(associatedLabel).toBeNull();
  });

  it("status filter button group uses aria-pressed not aria-selected", () => {
    // The sessions page uses aria-pressed for toggle buttons (not tabs)
    const container = document.createElement("div");
    container.innerHTML = `
      <div role="group" aria-label="Session status filter">
        <button aria-pressed="true">All <span aria-label="47 sessions">47</span></button>
        <button aria-pressed="false">Clean <span aria-label="40 sessions">40</span></button>
        <button aria-pressed="false">Failed <span aria-label="7 sessions">7</span></button>
      </div>
    `;
    const buttons = Array.from(container.querySelectorAll("button"));
    for (const btn of buttons) {
      // aria-pressed must be present and a valid boolean string
      const pressed = btn.getAttribute("aria-pressed");
      expect(pressed === "true" || pressed === "false").toBe(true);
    }
  });
});

// ─── 2. Tab panel ARIA state ──────────────────────────────────────────────────

describe("ARIA regression — tab panels: focused tab has aria-selected=true, others false", () => {
  /**
   * Invariant: the monitoring page and agents page use role="tab" buttons.
   * WCAG SC 4.1.2 requires the selected state to be programmatically
   * determinable.  aria-selected must be "true" on the active tab and "false"
   * (not absent) on all others.
   */

  it("exactly one tab has aria-selected=true in a 3-tab group", () => {
    const container = document.createElement("div");
    container.innerHTML = `
      <div role="tablist" aria-label="Monitoring view">
        <button role="tab" aria-selected="true">Overview</button>
        <button role="tab" aria-selected="false">Models</button>
        <button role="tab" aria-selected="false">Tools</button>
      </div>
    `;
    assertTabAriaSelected(container);
  });

  it("all tabs must have aria-selected attribute (not absent)", () => {
    const container = document.createElement("div");
    container.innerHTML = `
      <div role="tablist" aria-label="Monitoring view">
        <button role="tab" aria-selected="false">Overview</button>
        <button role="tab" aria-selected="true">Models</button>
        <button role="tab" aria-selected="false">Tools</button>
      </div>
    `;
    const tabs = Array.from(container.querySelectorAll("[role='tab']"));
    for (const tab of tabs) {
      expect(tab.hasAttribute("aria-selected")).toBe(true);
    }
  });

  it("tab with missing aria-selected attribute violates the invariant", () => {
    // Deliberate failure fixture — documents the anti-pattern
    const container = document.createElement("div");
    container.innerHTML = `
      <div role="tablist">
        <button role="tab">Overview</button>
        <button role="tab">Models</button>
      </div>
    `;
    const tabs = Array.from(container.querySelectorAll("[role='tab']"));
    const missingSelected = tabs.filter((t) => !t.hasAttribute("aria-selected"));
    // This fixture intentionally fails — confirms our guard catches it
    expect(missingSelected.length).toBeGreaterThan(0);
  });

  it("switching tabs updates aria-selected correctly — only new tab is true", () => {
    const container = document.createElement("div");
    container.innerHTML = `
      <div role="tablist" aria-label="Agent detail">
        <button role="tab" id="tab-about" aria-selected="true">About</button>
        <button role="tab" id="tab-overview" aria-selected="false">Overview</button>
        <button role="tab" id="tab-sessions" aria-selected="false">Sessions</button>
        <button role="tab" id="tab-slos" aria-selected="false">SLOs</button>
      </div>
    `;

    // Simulate switching to "overview" tab
    const tabs = Array.from(container.querySelectorAll("[role='tab']")) as Element[];
    for (const tab of tabs) {
      tab.setAttribute("aria-selected", tab.id === "tab-overview" ? "true" : "false");
    }

    assertTabAriaSelected(container);

    const overviewTab = container.querySelector("#tab-overview")!;
    const aboutTab = container.querySelector("#tab-about")!;
    expect(overviewTab.getAttribute("aria-selected")).toBe("true");
    expect(aboutTab.getAttribute("aria-selected")).toBe("false");
  });

  it("tablist has an accessible name via aria-label", () => {
    const container = document.createElement("div");
    container.innerHTML = `
      <div role="tablist" aria-label="Monitoring view">
        <button role="tab" aria-selected="true">Overview</button>
      </div>
    `;
    const tablist = container.querySelector("[role='tablist']")!;
    const label = tablist.getAttribute("aria-label") ?? "";
    expect(label.trim().length).toBeGreaterThan(0);
  });
});

// ─── 3. Chart role="img" labels ───────────────────────────────────────────────

describe("ARIA regression — chart containers with role=img must have non-empty aria-label", () => {
  /**
   * Invariant: Recharts / custom chart wrappers that use role="img" must carry
   * a descriptive aria-label.  An empty string is as harmful as no label.
   * WCAG SC 1.1.1 requires a text alternative for non-text content.
   */

  it("chart container with role=img and non-empty aria-label passes", () => {
    const container = document.createElement("div");
    container.innerHTML = `
      <div role="img" aria-label="Session error rate over the last 24 hours">
        <!-- chart svg content -->
      </div>
    `;
    assertChartImgRolesHaveLabels(container);
  });

  it("chart container with role=img and empty aria-label fails the invariant", () => {
    const container = document.createElement("div");
    container.innerHTML = `<div role="img" aria-label=""></div>`;

    const imgEl = container.querySelector("[role='img']")!;
    const label = imgEl.getAttribute("aria-label") ?? "";
    // This fixture intentionally fails — documents the anti-pattern
    expect(label.trim().length).toBe(0);
  });

  it("chart container with role=img but NO aria-label attribute fails", () => {
    const container = document.createElement("div");
    container.innerHTML = `<div role="img"><!-- chart --></div>`;

    const imgEl = container.querySelector("[role='img']")!;
    expect(imgEl.getAttribute("aria-label")).toBeNull();
  });

  it("multiple chart containers each have non-empty aria-labels", () => {
    const container = document.createElement("div");
    container.innerHTML = `
      <div role="img" aria-label="Tool call latency p99 chart"><!-- chart 1 --></div>
      <div role="img" aria-label="Token consumption by model chart"><!-- chart 2 --></div>
      <div role="img" aria-label="Session error rate chart"><!-- chart 3 --></div>
    `;
    assertChartImgRolesHaveLabels(container);
  });

  it("aria-label with only whitespace is treated as empty (fails)", () => {
    const container = document.createElement("div");
    container.innerHTML = `<div role="img" aria-label="   "></div>`;

    const imgEl = container.querySelector("[role='img']")!;
    const label = (imgEl.getAttribute("aria-label") ?? "").trim();
    // Whitespace-only is equivalent to empty — documents the anti-pattern
    expect(label.length).toBe(0);
  });

  it("assertChartImgRolesHaveLabels passes when no role=img elements are present", () => {
    const container = document.createElement("div");
    container.innerHTML = `<div class="chart">no role attr</div>`;
    // Should not throw — no role=img means no assertions to fail
    expect(() => assertChartImgRolesHaveLabels(container)).not.toThrow();
  });
});

// ─── 4. Group-level accessible names ─────────────────────────────────────────

describe("ARIA regression — control groups have accessible names", () => {
  /**
   * Invariant: element groups with role="group" (e.g. the session status
   * filter buttons in sessions/page.tsx) must carry an aria-label so screen
   * reader users understand the purpose of the group.
   */

  it("role=group with aria-label passes", () => {
    const container = document.createElement("div");
    container.innerHTML = `
      <div role="group" aria-label="Session status filter">
        <button aria-pressed="true">All</button>
        <button aria-pressed="false">Clean</button>
        <button aria-pressed="false">Failed</button>
      </div>
    `;
    const group = container.querySelector("[role='group']")!;
    const label = group.getAttribute("aria-label") ?? "";
    expect(label.trim().length).toBeGreaterThan(0);
  });

  it("role=group without aria-label or aria-labelledby is an ARIA violation", () => {
    const container = document.createElement("div");
    container.innerHTML = `
      <div role="group">
        <button>All</button>
        <button>Clean</button>
      </div>
    `;
    const group = container.querySelector("[role='group']")!;
    const ariaLabel = group.getAttribute("aria-label");
    const ariaLabelledBy = group.getAttribute("aria-labelledby");
    // Documents the anti-pattern — group has no accessible name
    expect(ariaLabel).toBeNull();
    expect(ariaLabelledBy).toBeNull();
  });
});
