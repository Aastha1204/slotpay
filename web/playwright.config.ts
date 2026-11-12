import { defineConfig, devices } from "@playwright/test";

const PY = process.env.PYTHON ?? "python";
const DB = process.env.DATABASE_URL ?? "postgresql://postgres:postgres@127.0.0.1:54322/postgres";

// Real API + real DB for catalogue/slots; payment/hold POSTs are stubbed per test (no Razorpay keys needed).
export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  fullyParallel: false,
  workers: 1, // one browser at a time: slot lists are fetched live, so parallel load makes timings flaky
  retries: 0,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:3100", channel: "chrome", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [
    { name: "pixel-7", use: { ...devices["Pixel 7"], channel: "chrome" } },
    { name: "small-360x800", use: { ...devices["Pixel 7"], viewport: { width: 360, height: 800 }, channel: "chrome" } },
  ],
  webServer: [
    { command: `${PY} ../api/run.py`, url: "http://localhost:8000/health", reuseExistingServer: true, timeout: 60_000,
      env: { DATABASE_URL: DB, WEB_ORIGIN: "http://localhost:3100", DEMO_KEY: "demo123", DEMO_MODE: "true", JOBS_SECRET: "j", PROTOTYPE_MODE: "true", REMINDER_DEMO_DELAY_SEC: "8", WHATSAPP_MODE: "simulator", SUPABASE_JWT_SECRET: "local-prototype-jwt-secret-0123456789abcdef" } },
    { command: "npx next dev -p 3100", url: "http://localhost:3100/b/glow-studio", reuseExistingServer: true, timeout: 120_000,
      env: { NEXT_PUBLIC_PROTOTYPE: "1", NEXT_PUBLIC_DEMO_KEY: "demo123", NEXT_PUBLIC_API_BASE_URL: "/api", API_INTERNAL_URL: "http://localhost:8000" } },
  ],
});
