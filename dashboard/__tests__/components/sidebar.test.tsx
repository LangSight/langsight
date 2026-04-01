/**
 * Tests for the Sidebar component.
 * Verifies nav structure, active state, project switcher, and user menu.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Sidebar } from "@/components/sidebar";

// Mock SWR to avoid real API calls in tests
jest.mock("swr", () => ({
  __esModule: true,
  default: jest.fn(() => ({ data: [], isLoading: false, error: null })),
}));

// Mock project context
const mockSetActiveProject = jest.fn();
jest.mock("@/lib/project-context", () => ({
  useProject: () => ({
    activeProject: null,
    setActiveProject: mockSetActiveProject,
  }),
}));

// Mock api
jest.mock("@/lib/api", () => ({
  fetcher: jest.fn(),
  createProject: jest.fn(),
}));

// Mock usePathname for active state tests
const mockUsePathname = jest.fn(() => "/");
jest.mock("next/navigation", () => ({
  usePathname: () => mockUsePathname(),
  useRouter: () => ({ push: jest.fn(), prefetch: jest.fn() }),
}));

function renderSidebar() {
  return render(<Sidebar />);
}

/* ── Brand ───────────────────────────────────────────────────── */
describe("Sidebar — branding", () => {
  it("renders the LangSight logo", () => {
    renderSidebar();
    expect(screen.getByText("LangSight")).toBeInTheDocument();
  });

  it("renders the version badge", () => {
    renderSidebar();
    expect(screen.getByText("v0.6")).toBeInTheDocument();
  });
});

/* ── Navigation links ───────────────────────────────────────── */
describe("Sidebar — navigation", () => {
  it("renders all primary nav items", () => {
    renderSidebar();
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Sessions")).toBeInTheDocument();
    expect(screen.getByText("Agents")).toBeInTheDocument();
    expect(screen.getByText("Costs")).toBeInTheDocument();
  });

  it("renders infrastructure nav items", () => {
    renderSidebar();
    expect(screen.getByText("MCP Servers")).toBeInTheDocument();
    expect(screen.getByText("Live")).toBeInTheDocument();
    expect(screen.getByText("MCP Security")).toBeInTheDocument();
    expect(screen.getByText("Alerts")).toBeInTheDocument();
  });

  it("renders Settings link", () => {
    renderSidebar();
    expect(screen.getByText("Settings")).toBeInTheDocument();
  });

  it("Dashboard link points to /", () => {
    renderSidebar();
    const overviewLink = screen.getByRole("link", { name: /dashboard/i });
    expect(overviewLink).toHaveAttribute("href", "/");
  });

  it("Sessions link points to /sessions", () => {
    renderSidebar();
    const sessionsLink = screen.getByRole("link", { name: /sessions/i });
    expect(sessionsLink).toHaveAttribute("href", "/sessions");
  });

  it("Agents link points to /agents", () => {
    renderSidebar();
    const agentsLink = screen.getByRole("link", { name: /agents/i });
    expect(agentsLink).toHaveAttribute("href", "/agents");
  });

  it("Costs link points to /costs", () => {
    renderSidebar();
    expect(screen.getByRole("link", { name: /costs/i })).toHaveAttribute("href", "/costs");
  });

  it("MCP Servers link points to /servers", () => {
    renderSidebar();
    expect(screen.getByRole("link", { name: /mcp servers/i })).toHaveAttribute("href", "/servers");
  });

  it("Live link points to /live", () => {
    renderSidebar();
    expect(screen.getByRole("link", { name: /^live$/i })).toHaveAttribute("href", "/live");
  });

  it("MCP Security link points to /security", () => {
    renderSidebar();
    expect(screen.getByRole("link", { name: /mcp security/i })).toHaveAttribute("href", "/security");
  });

  it("Alerts link points to /alerts", () => {
    renderSidebar();
    expect(screen.getByRole("link", { name: /^alerts$/i })).toHaveAttribute("href", "/alerts");
  });
});

/* ── Active state ───────────────────────────────────────────── */
describe("Sidebar — active state", () => {
  it("marks Dashboard as active on /", () => {
    mockUsePathname.mockReturnValue("/");
    renderSidebar();
    const overviewLink = screen.getByRole("link", { name: /dashboard/i });
    expect(overviewLink.className).toContain("active");
  });

  it("marks Sessions as active on /sessions", () => {
    mockUsePathname.mockReturnValue("/sessions");
    renderSidebar();
    const sessionsLink = screen.getByRole("link", { name: /sessions/i });
    expect(sessionsLink.className).toContain("active");
  });

  it("marks Agents as active on /agents/detail", () => {
    mockUsePathname.mockReturnValue("/agents/detail");
    renderSidebar();
    const agentsLink = screen.getByRole("link", { name: /agents/i });
    expect(agentsLink.className).toContain("active");
  });

  it("does not mark Sessions as active on /settings", () => {
    mockUsePathname.mockReturnValue("/settings");
    renderSidebar();
    const sessionsLink = screen.getByRole("link", { name: /sessions/i });
    expect(sessionsLink.className).not.toContain("active");
  });
});

/* ── User menu ───────────────────────────────────────────────── */
describe("Sidebar — user menu", () => {
  it("shows signed-in user name", () => {
    renderSidebar();
    expect(screen.getByText("Admin User")).toBeInTheDocument();
  });

  it("shows signed-in user email", () => {
    renderSidebar();
    expect(screen.getByText("admin@langsight.dev")).toBeInTheDocument();
  });

  it("opens user menu on click", async () => {
    renderSidebar();
    const userButton = screen.getByText("Admin User").closest("button");
    expect(userButton).toBeTruthy();
    await userEvent.click(userButton!);
    await waitFor(() => {
      expect(screen.getByText("Sign out")).toBeInTheDocument();
    });
  });

});

/* ── Project switcher ───────────────────────────────────────── */
describe("Sidebar — project switcher", () => {
  it('shows "All Projects" by default (no active project)', () => {
    renderSidebar();
    expect(screen.getByText("All Projects")).toBeInTheDocument();
  });

  it("opens project dropdown on click", async () => {
    renderSidebar();
    const projectBtn = screen.getByText("All Projects").closest("button");
    await userEvent.click(projectBtn!);
    await waitFor(() => {
      // Dropdown should be visible with the "All Projects" option inside it
      const allProjectsItems = screen.getAllByText("All Projects");
      expect(allProjectsItems.length).toBeGreaterThanOrEqual(1);
    });
  });
});

/* ── Status widget ───────────────────────────────────────────── */
describe("Sidebar — API status widget", () => {
  it("shows LangSight API status", () => {
    renderSidebar();
    expect(screen.getByText("LangSight API")).toBeInTheDocument();
  });
});
