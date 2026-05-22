export const testEnv = {
  baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://localhost:5173",
  email: process.env.PLAYWRIGHT_TEST_EMAIL || "",
  phone: process.env.PLAYWRIGHT_TEST_PHONE || "",
  password: process.env.PLAYWRIGHT_TEST_PASSWORD || "",
  factoryName: process.env.PLAYWRIGHT_TEST_FACTORY_NAME || "",
};

export function uniqueLocalUser() {
  const id = `${Date.now()}${Math.floor(Math.random() * 1000)}`;
  const suffix = id.slice(-8);

  return {
    fullName: `E2E Owner ${suffix}`,
    email: process.env.PLAYWRIGHT_TEST_EMAIL || `e2e.${id}@example.test`,
    phone: process.env.PLAYWRIGHT_TEST_PHONE || `98${suffix}`,
    password: process.env.PLAYWRIGHT_TEST_PASSWORD || `E2eTest@${suffix}`,
    factoryName: process.env.PLAYWRIGHT_TEST_FACTORY_NAME || `E2E Factory ${suffix}`,
  };
}

export function apiHealthCandidates(baseURL: string) {
  const url = new URL(baseURL);
  const isLocal = url.hostname === "localhost" || url.hostname === "127.0.0.1";
  const origin = isLocal ? `${url.protocol}//${url.hostname}:8000` : `${url.protocol}//${url.host}`;

  return [`${origin}/health`, `${origin}/api/health`];
}
