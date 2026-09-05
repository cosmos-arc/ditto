import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { describe, expect, it } from "vitest";

const projectRoot = resolve(import.meta.dirname, "..");
const acceptanceScript = join(projectRoot, "scripts/r1-trading-acceptance.ts");

async function loadAcceptance(): Promise<typeof import("./r1-trading-acceptance")> {
	const moduleUrl = pathToFileURL(acceptanceScript).href;
	return import(/* @vite-ignore */ moduleUrl);
}

describe("R1 trading visual acceptance contract", () => {
	it("keeps a zero-argument R1 visual audit alongside the generic CLI", () => {
		const packageJson = JSON.parse(readFileSync(join(projectRoot, "package.json"), "utf8")) as {
			scripts?: Record<string, string>;
		};

		expect(packageJson.scripts?.["visual:audit"]).toBe(
			"bun ../../.agents/skills/ditto-app-dev/scripts/visual-audit.mjs --route /portfolio/model --react-base http://127.0.0.1:5173 --prototype-base http://127.0.0.1:8888/docs/designs/specs/prototypes",
		);
		expect(packageJson.scripts?.["visual:audit:cli"]).toBe("bun ../../.agents/skills/ditto-app-dev/scripts/visual-audit.mjs");
		expect(packageJson.scripts?.["acceptance:r1-trading"]).toBe("bun scripts/r1-trading-acceptance.ts");
	});

	it("defines a reproducible desktop/mobile evidence matrix", async () => {
		expect(existsSync(acceptanceScript)).toBe(true);
		const { buildEvidenceCases } = await loadAcceptance();

		expect(buildEvidenceCases().map((item) => `${item.viewport.name}/${item.scenario}`)).toEqual([
			"desktop/blocked",
			"desktop/review",
			"desktop/review-fills",
			"desktop/ready",
			"desktop/fill-review",
			"desktop/multi-fill-ledger",
			"desktop/fill-correction",
			"mobile/blocked",
			"mobile/review",
			"mobile/review-fills",
			"mobile/ready",
			"mobile/fill-review",
			"mobile/multi-fill-ledger",
			"mobile/fill-correction",
		]);
	});

	it("builds backend-shaped readiness states with two effective fills", async () => {
		expect(existsSync(acceptanceScript)).toBe(true);
		const { buildDecisionReport } = await loadAcceptance();

		const blocked = buildDecisionReport("blocked");
		const review = buildDecisionReport("review");
		const ready = buildDecisionReport("ready");

		expect(blocked.readiness).toMatchObject({
			status: "blocked",
			reason_codes: ["ACCOUNT_BASELINE_MISSING"],
		});
		expect(review.readiness).toMatchObject({ status: "review", reason_codes: ["RISK_WARNING"] });
		expect(review.execution_review.effective_fills.map((fill: { readonly fill_id: string }) => fill.fill_id)).toEqual([
			"fill-intent-510300-001",
			"fill-intent-510300-002",
		]);
		expect(review.actions[0]).toMatchObject({ filled_quantity: 600, remaining_quantity: 400 });
		expect(ready.readiness).toMatchObject({ status: "ready", reason_codes: ["READY_FOR_REVIEW"] });
	});

	it("uses loopback-only defaults while allowing explicit output overrides", async () => {
		expect(existsSync(acceptanceScript)).toBe(true);
		const { parseAcceptanceArgs } = await loadAcceptance();

		expect(parseAcceptanceArgs([])).toEqual({
			reactBase: "http://127.0.0.1:5173",
			outDir: "docs/review/r1-trading-acceptance",
		});
		expect(parseAcceptanceArgs(["--react-base", "http://127.0.0.1:4173", "--out-dir", "tmp/r1"])).toEqual({
			reactBase: "http://127.0.0.1:4173",
			outDir: "tmp/r1",
		});
	});

	it("labels network fixtures as frontend-only evidence", async () => {
		const { ACCEPTANCE_SCOPE } = await loadAcceptance();

		expect(ACCEPTANCE_SCOPE).toEqual({
			runtime: "VITE_USE_MOCK=false",
			apiData: "Playwright route fixtures for DailyDecision V2, raw/effective fills, adjustments, and correction mutations",
			proves: "frontend state, visual, append-only correction interaction, accessibility, and scroll behavior only",
			doesNotProve: "Task6 live backend persistence/E2E or production data correctness",
		});
	});

	it("ignores only aborted speculative script loads", async () => {
		const { shouldIgnoreAcceptanceRequestFailure } = await loadAcceptance();

		expect(shouldIgnoreAcceptanceRequestFailure("script", "net::ERR_ABORTED")).toBe(true);
		expect(shouldIgnoreAcceptanceRequestFailure("fetch", "net::ERR_ABORTED")).toBe(false);
		expect(shouldIgnoreAcceptanceRequestFailure("script", "net::ERR_CONNECTION_REFUSED")).toBe(false);
	});
});
