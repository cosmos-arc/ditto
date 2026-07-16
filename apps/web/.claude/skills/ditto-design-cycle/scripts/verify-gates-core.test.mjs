import { describe, expect, it } from "vitest";
import { spawnSync } from "node:child_process";
import {
	buildGateSummary,
	parseArgs,
	toIssue,
} from "./verify-gates-core.mjs";

describe("ditto design-cycle gate core", () => {
	it("parses required prototype path and default viewport matrix", () => {
		const options = parseArgs(["--prototype", "docs/designs/specs/prototypes/page-home.html"]);

		expect(options).toMatchObject({
			prototype: "docs/designs/specs/prototypes/page-home.html",
			viewports: [
				{ label: "VP-STANDARD", width: 1536, height: 1080 },
				{ label: "VP-COMPACT", width: 1366, height: 768 },
			],
		});
	});

	it("supports explicit viewport overrides", () => {
		const options = parseArgs([
			"--prototype",
			"page-home.html",
			"--viewport",
			"VP-LARGE=1920x1080",
			"--viewport",
			"QA=1440x900",
		]);

		expect(options.viewports).toEqual([
			{ label: "VP-LARGE", width: 1920, height: 1080 },
			{ label: "QA", width: 1440, height: 900 },
		]);
	});

	it("rejects missing prototype input", () => {
		expect(() => parseArgs([])).toThrow("Missing required --prototype");
	});

	it("rejects malformed viewport input", () => {
		expect(() =>
			parseArgs(["--prototype", "page.html", "--viewport", "1536x1080"]),
		).toThrow("Expected LABEL=WIDTHxHEIGHT");
	});

	it("marks P0 and P1 issues as blocking by default", () => {
		const summary = buildGateSummary([
			toIssue("gate-1-css", "P0", "token CSS did not load"),
			toIssue("viewport", "P1", "fixed status bar lacks body padding"),
			toIssue("screenshot", "P2", "minor visual drift"),
		]);

		expect(summary.status).toBe("fail");
		expect(summary.blocking).toHaveLength(2);
		expect(summary.nonBlocking).toHaveLength(1);
	});

	it("can run in strict mode where P2 issues also block", () => {
		const summary = buildGateSummary(
			[toIssue("screenshot", "P2", "minor visual drift")],
			{ strict: true },
		);

		expect(summary.status).toBe("fail");
		expect(summary.blocking).toHaveLength(1);
	});

	it("recognizes shell-studio roots in prototype gate checks", () => {
		const result = spawnSync(
			"bun",
			[
				".claude/skills/ditto-design-cycle/scripts/verify-gates.mjs",
				"--prototype",
				"docs/designs/specs/prototypes/page-strategy-studio.html",
				"--viewport",
				"TEST=800x600",
				"--out-dir",
				"test-results/ditto-design-cycle-gates/strategy-studio-selector-test",
			],
			{ cwd: process.cwd(), encoding: "utf8" },
		);

		expect(`${result.stdout}\n${result.stderr}`).not.toContain("shell root not found");
	}, 20_000);
});
