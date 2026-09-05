import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { auditLeafManifestDependencies } from "./check-leaf-dependencies";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

async function writeFixture(path: string, contents: string): Promise<void> {
	await mkdir(dirname(path), { recursive: true });
	await writeFile(path, contents, "utf8");
}

describe("Web leaf manifest dependency audit", () => {
	it("finds root-only imports across source and scripts without misclassifying aliases or builtins", async () => {
		const fixtureRoot = await mkdtemp(join(tmpdir(), "ditto-web-leaf-manifest-"));
		try {
			await writeFixture(
				join(fixtureRoot, "package.json"),
				JSON.stringify({
					name: "@ditto/fixture-web",
					dependencies: { react: "19.0.0" },
					devDependencies: { typescript: "6.0.0", vitest: "4.0.0" },
				}),
			);
			await writeFixture(
				join(fixtureRoot, "tsconfig.base.json"),
				JSON.stringify({
					compilerOptions: { paths: { "@/*": ["./src/*"] } },
				}),
			);
			await writeFixture(join(fixtureRoot, "src/local.ts"), "export const local = true;\n");
			await writeFixture(
				join(fixtureRoot, "src/main.ts"),
				[
					'import type { ReactNode } from "react";',
					'import "react/jsx-runtime";',
					'import { local } from "@/local";',
					'import { readFile } from "node:fs/promises";',
					'export { lint } from "@redocly/cli";',
					'const resolveReporter = () => require.resolve("root-reporter");',
					"void (local satisfies boolean);",
					"void (null as ReactNode);",
					"void readFile;",
					"void resolveReporter;",
				].join("\n"),
			);
			await writeFixture(
				join(fixtureRoot, "scripts/check.ts"),
				[
					'import type { PlaywrightTestConfig } from "@playwright/test";',
					'const loadTestRunner = () => import("vitest");',
					"void (null as PlaywrightTestConfig);",
					"void loadTestRunner;",
				].join("\n"),
			);

			const audit = await auditLeafManifestDependencies({ webRoot: fixtureRoot });

			expect(audit.violations).toEqual([
				{
					packageName: "@playwright/test",
					source: "scripts/check.ts",
					specifier: "@playwright/test",
				},
				{
					packageName: "@redocly/cli",
					source: "src/main.ts",
					specifier: "@redocly/cli",
				},
				{
					packageName: "root-reporter",
					source: "src/main.ts",
					specifier: "root-reporter",
				},
			]);
			expect(audit.filesChecked).toBe(3);
		} finally {
			await rm(fixtureRoot, { recursive: true, force: true });
		}
	});

	it("checks top-level executable modules as part of the leaf boundary", async () => {
		const fixtureRoot = await mkdtemp(join(tmpdir(), "ditto-web-leaf-top-level-"));
		try {
			await writeFixture(
				join(fixtureRoot, "package.json"),
				JSON.stringify({ name: "@ditto/fixture-web", devDependencies: {} }),
			);
			await writeFixture(join(fixtureRoot, "release-check.mjs"), 'import "root-release-helper";\n');

			const audit = await auditLeafManifestDependencies({ webRoot: fixtureRoot });

			expect(audit.violations).toEqual([
				{
					packageName: "root-release-helper",
					source: "release-check.mjs",
					specifier: "root-release-helper",
				},
			]);
		} finally {
			await rm(fixtureRoot, { recursive: true, force: true });
		}
	});

	it("keeps the checked-in Web source and scripts self-contained", { timeout: 20_000 }, async () => {
		const audit = await auditLeafManifestDependencies({ webRoot });

		expect(audit.violations).toEqual([]);
		expect(audit.filesChecked).toBeGreaterThan(100);
	});
});
