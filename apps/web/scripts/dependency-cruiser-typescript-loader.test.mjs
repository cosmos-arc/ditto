import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { expect, test } from "vitest";

test("the dependency compiler retains Node filesystem support through the loader", () => {
  const loader = fileURLToPath(new URL("./dependency-cruiser-typescript-loader.mjs", import.meta.url));
  const result = spawnSync("node", ["--import", loader, "--input-type=module", "--eval", `
    import ts from "typescript";
    import { createRequire } from "node:module";
    const require = createRequire(import.meta.resolve("dependency-cruiser"));
    require.resolve("typescript");
    const result = ts.readConfigFile("tsconfig.browser.json", ts.sys.readFile);
    if (result.error) throw new Error(ts.flattenDiagnosticMessageText(result.error.messageText, "\\n"));
    console.log(result.config.extends);
  `], { cwd: fileURLToPath(new URL("..", import.meta.url)), encoding: "utf8" });
  expect(result.status, result.stderr).toBe(0);
  expect(result.stdout.trim()).toBe("./tsconfig.base.json");
});

test("the real cruiser confines transport and rebuilt barrels while allowing errors and type contracts", async () => {
  const { mkdtemp, mkdir, writeFile, rm } = await import("node:fs/promises");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const webRoot = fileURLToPath(new URL("..", import.meta.url));
  const root = await mkdtemp(join(tmpdir(), "ditto-transport-boundary-"));
  const illegal = {
    "src/features/portfolio/components/direct.ts": 'export { apiClient } from "@/api/transport";',
    "src/features/portfolio/hooks/direct.ts": 'export { apiClient } from "../../../api/transport";',
    "src/workflows/example/direct.ts": 'export { apiClient } from "@/api";',
    "src/main.tsx": 'export { apiClient } from "./api/transport";',
  };
  const files = {
    "tsconfig.browser.json": JSON.stringify({ compilerOptions: { baseUrl: ".", paths: { "@/*": ["src/*"] } } }),
    "src/api/transport.ts": "export const apiClient = 1;",
    "src/api/index.ts": 'export { apiClient } from "./transport";',
    "src/api/errors.ts": "export class ApiError extends Error {}",
    "src/api/market-contract.ts": "export type Market = { id: string };",
    "src/api/bootstrap.ts": 'export { apiClient } from "./transport";',
    "src/features/portfolio/api/allowed.ts": 'export { apiClient } from "@/api/transport";',
    "src/features/portfolio/components/allowed.ts": 'export { ApiError } from "@/api/errors"; export type { Market } from "@/api/market-contract";',
    "src/workflows/example/allowed.ts": 'export { ApiError } from "@/api/errors";',
    "src/features/portfolio/components/allowed.test.ts": 'export { apiClient } from "@/api/transport";',
    ...illegal,
  };
  const cruise = () => spawnSync("node", [
    "--import", join(webRoot, "scripts/dependency-cruiser-typescript-loader.mjs"),
    join(webRoot, "node_modules/dependency-cruiser/bin/dependency-cruise.mjs"),
    "--config", join(webRoot, "dependency-cruiser.config.mjs"), "--output-type", "json", "src",
  ], { cwd: root, encoding: "utf8", env: { ...process.env, NODE_PATH: join(webRoot, "node_modules") } });
  try {
    for (const [relative, content] of Object.entries(files)) {
      const target = join(root, relative);
      await mkdir(join(target, ".."), { recursive: true });
      await writeFile(target, content);
    }
    const rejected = cruise();
    const report = JSON.parse(rejected.stdout);
    expect(report.summary.violations.map(({ from, rule }) => [from, rule.name, rule.severity]).sort()).toEqual(
      Object.keys(illegal).map((from) => [from, "core-api-client-surface-stays-in-transport-zones", "error"]).sort(),
    );
    // JSON output returns zero; the existing runner rejects error-level violations.
    expect(rejected.status, rejected.stderr).toBe(0);
    for (const relative of Object.keys(illegal)) await rm(join(root, relative));
    const allowed = cruise();
    expect(allowed.status, allowed.stderr || allowed.stdout).toBe(0);
    expect(JSON.parse(allowed.stdout).summary.violations).toEqual([]);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
