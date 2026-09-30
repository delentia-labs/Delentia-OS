import { defineConfig, globalIgnores } from "eslint/config";
import nextCoreWebVitals from "eslint-config-next/core-web-vitals";

// `next lint` was removed in Next.js 16, so linting runs through the ESLint CLI.
export default defineConfig([
  globalIgnores([".next/**", "out/**", "src-tauri/**", "next-env.d.ts"]),
  ...nextCoreWebVitals,
]);
