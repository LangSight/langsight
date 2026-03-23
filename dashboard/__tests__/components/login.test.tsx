/**
 * Tests for the login page component.
 * Mocks next-auth signIn to avoid real network calls.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { signIn } from "next-auth/react";
import LoginPage from "@/app/(auth)/login/page";

const mockSignIn = signIn as jest.MockedFunction<typeof signIn>;
const mockPush = jest.fn();
const mockRefresh = jest.fn();
type SignInResult = NonNullable<Awaited<ReturnType<typeof signIn>>>;

function makeSignInResponse(overrides: Partial<SignInResult> = {}): SignInResult {
  return {
    ok: true,
    error: undefined,
    status: 200,
    url: null,
    code: undefined,
    ...overrides,
  };
}

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, refresh: mockRefresh }),
}));

/* ── Render helpers ─────────────────────────────────────────── */
function renderLogin() {
  return render(<LoginPage />);
}

/* ── Layout / accessibility ──────────────────────────────────── */
describe("LoginPage — layout", () => {
  it("renders the LangSight brand name", () => {
    renderLogin();
    expect(screen.getAllByText("LangSight").length).toBeGreaterThan(0);
  });

  it("renders email and password inputs", () => {
    renderLogin();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
  });

  it("renders the sign in button", () => {
    renderLogin();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
  });

  it("pre-fills email with demo credential", () => {
    renderLogin();
    const emailInput = screen.getByLabelText("Email") as HTMLInputElement;
    expect(emailInput.value).toBe("admin@admin.com");
  });

  it("shows demo credentials hint", () => {
    renderLogin();
    expect(screen.getByText(/demo credentials/i)).toBeInTheDocument();
  });

  it("password input is type=password by default", () => {
    renderLogin();
    const pwInput = screen.getByLabelText("Password") as HTMLInputElement;
    expect(pwInput.type).toBe("password");
  });
});

/* ── Password visibility toggle ────────────────────────────── */
describe("LoginPage — password visibility", () => {
  it("toggles password visibility when eye button is clicked", async () => {
    renderLogin();
    const pwInput = screen.getByLabelText("Password") as HTMLInputElement;
    const toggleBtn = screen.getByRole("button", { name: /show password|hide password/i });

    expect(pwInput.type).toBe("password");
    await userEvent.click(toggleBtn);
    expect(pwInput.type).toBe("text");
    await userEvent.click(toggleBtn);
    expect(pwInput.type).toBe("password");
  });
});

/* ── Form interaction ───────────────────────────────────────── */
describe("LoginPage — form interaction", () => {
  it("allows typing into email and password fields", async () => {
    renderLogin();
    const emailInput = screen.getByLabelText("Email") as HTMLInputElement;
    const pwInput    = screen.getByLabelText("Password") as HTMLInputElement;

    await userEvent.clear(emailInput);
    await userEvent.type(emailInput, "test@example.com");
    expect(emailInput.value).toBe("test@example.com");

    await userEvent.clear(pwInput);
    await userEvent.type(pwInput, "secret");
    expect(pwInput.value).toBe("secret");
  });
});

/* ── Sign-in success ────────────────────────────────────────── */
describe("LoginPage — successful sign in", () => {
  beforeEach(() => {
    mockSignIn.mockResolvedValue(makeSignInResponse());
  });

  it("calls signIn with credentials provider and form values", async () => {
    renderLogin();
    const submitBtn = screen.getByRole("button", { name: /sign in/i });
    await userEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockSignIn).toHaveBeenCalledWith(
        "credentials",
        expect.objectContaining({
          email: "admin@admin.com",
          redirect: false,
        })
      );
    });
  });

  it("redirects to / on success", async () => {
    renderLogin();
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/");
    });
  });

  it("shows loading state while submitting", async () => {
    // Make signIn take a moment
    mockSignIn.mockImplementationOnce(
      () => new Promise((res) => setTimeout(() => res(makeSignInResponse()), 50))
    );

    renderLogin();
    const submitBtn = screen.getByRole("button", { name: /sign in/i });
    await userEvent.click(submitBtn);

    expect(screen.getByText(/signing in/i)).toBeInTheDocument();
  });
});

/* ── Sign-in failure ────────────────────────────────────────── */
describe("LoginPage — failed sign in", () => {
  beforeEach(() => {
    mockPush.mockReset();
    mockSignIn.mockResolvedValue(
      makeSignInResponse({ ok: false, error: "CredentialsSignin", status: 401 })
    );
  });

  it("does not redirect on error", async () => {
    renderLogin();
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(mockSignIn).toHaveBeenCalled();
    });
    expect(mockPush).not.toHaveBeenCalled();
  });
});
