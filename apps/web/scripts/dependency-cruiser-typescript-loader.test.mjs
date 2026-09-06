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
