import { existsSync, readFileSync } from "node:fs";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { describe, expect, it } from "vitest";

const projectRoot = resolve(import.meta.dirname, "..");
const acceptanceScript = join(projectRoot, "scripts/r3-research-acceptance.ts");

async function loadAcceptance(): Promise<typeof import("./r3-research-acceptance")> {
	return import(/* @vite-ignore */ pathToFileURL(acceptanceScript).href);
}

describe("R3 research deterministic acceptance contract", () => {
	it("exposes the approved fixture-only package command", () => {
		const packageJson = JSON.parse(readFileSync(join(projectRoot, "package.json"), "utf8")) as {
			scripts?: Record<string, string>;
		};

		expect(existsSync(acceptanceScript)).toBe(true);
		expect(packageJson.scripts?.["acceptance:r3-research"]).toBe("bun scripts/r3-research-acceptance.ts");
	});

	it("requires fixture mode and keeps output isolated", async () => {
		const { parseAcceptanceArgs } = await loadAcceptance();

		expect(() => parseAcceptanceArgs([])).toThrow("--fixture is required");
		expect(parseAcceptanceArgs(["--fixture"])).toEqual({
			fixture: true,
			outDir: "docs/review/r3-research-acceptance/deterministic",
		});
		expect(parseAcceptanceArgs(["--fixture", "--out-dir", "tmp/r3-ui"])).toEqual({
			fixture: true,
			outDir: "tmp/r3-ui",
		});
	});

	it("binds Studio, Experiment, Review, refresh, hard-gate, and live-boundary tests", async () => {
		const { buildFixtureCommand } = await loadAcceptance();
		const command = buildFixtureCommand().join(" ");

		expect(command).toContain("experiment-create-page.test.tsx");
		expect(command).toContain("experiment-detail-page.test.tsx");
		expect(command).toContain("experiment-run-recovery.test.tsx");
		expect(command).toContain("review-detail-page.test.tsx");
		expect(command).toContain("review-queue-page.test.tsx");
		expect(command).toContain("live-boundary.test.tsx");
	});

	it("labels MSW evidence as UI contract only", async () => {
		const { ACCEPTANCE_SCOPE } = await loadAcceptance();

		expect(ACCEPTANCE_SCOPE).toEqual({
			mode: "deterministic_fixture",
			runtime: "jsdom + isolated MSW HTTP fixtures",
			proves: ["studio_experiment_review_flow", "refresh_recovery", "hard_gate_blocked_ui", "typed_live_boundary"],
			doesNotProve: [
				"provider_entitlement",
				"certified_live_data",
				"live_96_month_history",
				"real_browser_acceptance",
				"production_recovery",
			],
		});
	});

	it("writes a blocked release report with a hashed command transcript", async () => {
		const { runFixtureAcceptance } = await loadAcceptance();
		const outDir = await mkdtemp(join(tmpdir(), "ditto-r3-ui-acceptance-"));
		try {
			const report = await runFixtureAcceptance(
				{ fixture: true, outDir },
				{
					checkedAt: new Date("2026-08-01T01:02:03Z"),
					sourceCommit: "a".repeat(40),
					runCommand: () => ({ returncode: 0, stdout: "6 passed", stderr: "" }),
				},
			);

			expect(report).toMatchObject({
				mode: "deterministic_fixture",
				passed: true,
				release_status: "RELEASE_ACCEPTANCE_BLOCKED",
				r2_live_gate: "NOT_EVALUATED",
			});
			expect(report.command.artifact_hashes.command_transcript).toMatch(/^[a-f0-9]{64}$/u);
			expect(readFileSync(join(outDir, "report.json"), "utf8")).not.toContain('"live_passed": true');
		} finally {
			await rm(outDir, { recursive: true, force: true });
		}
	});
});
