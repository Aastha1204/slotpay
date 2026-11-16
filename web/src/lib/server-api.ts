// Where server components reach the API. Locally: the FastAPI process. On Vercel: the /api Function of this same project.
export const API_INTERNAL =
  process.env.API_INTERNAL_URL ??
  (process.env.VERCEL ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL ?? process.env.VERCEL_URL}/api` : "http://localhost:8000");
