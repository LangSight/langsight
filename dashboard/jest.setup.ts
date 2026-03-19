import "@testing-library/jest-dom";

// Polyfill Web APIs needed for Next.js Route Handler tests
import { TextEncoder, TextDecoder } from "util";
Object.assign(global, { TextEncoder, TextDecoder });

// Next.js Route Handlers use the Fetch API — polyfill for jsdom
if (typeof global.Request === "undefined") {
  const { Request, Response, Headers, fetch: nodeFetch } = require("node-fetch");
  Object.assign(global, { Request, Response, Headers });
  if (typeof global.fetch === "undefined") global.fetch = nodeFetch;
}

// Silence next/navigation warnings in tests
jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: jest.fn(),
    replace: jest.fn(),
    refresh: jest.fn(),
    back: jest.fn(),
    prefetch: jest.fn(),
  }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

// Mock next-auth
jest.mock("next-auth/react", () => ({
  useSession: () => ({
    data: {
      user: { name: "Admin User", email: "admin@langsight.io" },
      expires: "2099-01-01",
    },
    status: "authenticated",
  }),
  signIn: jest.fn(),
  signOut: jest.fn(),
}));

// Mock next-themes
jest.mock("next-themes", () => ({
  useTheme: () => ({ theme: "dark", setTheme: jest.fn() }),
}));

// Suppress console.error in tests (React act() warnings etc.)
const originalError = console.error;
beforeAll(() => {
  console.error = (...args: unknown[]) => {
    if (
      typeof args[0] === "string" &&
      (args[0].includes("Warning:") || args[0].includes("act("))
    ) return;
    originalError(...args);
  };
});
afterAll(() => {
  console.error = originalError;
});
