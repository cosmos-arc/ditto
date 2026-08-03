import { existsSync, readFileSync } from "node:fs";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
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

		expect(() => parseAcceptanceArgs([])).toThrow("exactly one");
		expect(parseAcceptanceArgs(["--fixture"])).toEqual({
			fixture: true,
			outDir: "docs/review/r3-research-acceptance/deterministic",
		});
		expect(parseAcceptanceArgs(["--fixture", "--out-dir", "tmp/r3-ui"])).toEqual({
			fixture: true,
			outDir: "tmp/r3-ui",
		});
	});

	it("accepts an explicit live browser mode with loopback-only bases", async () => {
		const { parseAcceptanceArgs } = await loadAcceptance();

		expect(() => parseAcceptanceArgs(["--real-data"])).toThrow("--planning-file");
		expect(parseAcceptanceArgs(["--real-data", "--planning-file", "/tmp/stock-planning.json"])).toEqual({
			realData: true,
			reactBase: "http://127.0.0.1:5173",
			apiBase: "http://127.0.0.1:8000",
			outDir: "docs/review/r3-research-acceptance/live",
			planningFile: "/tmp/stock-planning.json",
			timeoutMs: 300_000,
		});
		expect(
			parseAcceptanceArgs([
				"--real-data",
				"--planning-file",
				"/tmp/stock-planning.json",
				"--react-base",
				"http://localhost:4173/",
				"--api-base",
				"http://[::1]:8001/",
				"--out-dir",
				"tmp/r3-live-ui",
				"--timeout-ms",
				"2100000",
			]),
		).toEqual({
			realData: true,
			reactBase: "http://localhost:4173",
			apiBase: "http://[::1]:8001",
			outDir: "tmp/r3-live-ui",
			planningFile: "/tmp/stock-planning.json",
			timeoutMs: 2_100_000,
		});
		expect(() =>
			parseAcceptanceArgs([
				"--real-data",
				"--planning-file",
				"/tmp/stock-planning.json",
				"--timeout-ms",
				"299999",
			]),
		).toThrow("between 300000 and 3600000");
		expect(() => parseAcceptanceArgs(["--fixture", "--real-data"])).toThrow("exactly one");
		expect(() =>
			parseAcceptanceArgs([
				"--real-data",
				"--planning-file",
				"/tmp/stock-planning.json",
				"--api-base",
				"https://example.com",
			]),
		).toThrow(
			"loopback",
		);
	});

	it("loads the exact backend planning document used by live Studio", async () => {
		const { livePlanningJsonFields, loadLivePlanningDocument } = await loadAcceptance();
		const root = await mkdtemp(join(tmpdir(), "ditto-r3-live-planning-"));
		try {
			const path = join(root, "planning.json");
			const document = {
				experiment_id: "r3-live-stock-browser",
				research_cycle_id: "r3-live-cycle-stock-browser",
				research_cycle_hash: "a".repeat(64),
				strategy: {
					strategy_id: "seed_stock_selection_rotation",
					version: 3,
					spec_hash: "b".repeat(64),
					spec_json: { strategy_id: "seed_stock_selection_rotation", slippage_bps: 10 },
				},
				snapshot: { snapshot_id: "snapshot:r3", manifest_hash: "c".repeat(64) },
				validation: { trading_sessions: ["2026-07-31"] },
				matrix: {
					baseline: { descriptor_type: "stock-universe-equal-weight", payload: {}, schema_version: 1 },
					axes: [],
					candidate_limit: 128,
				},
				promotion_objective: { schema_id: "r3-promotion-objective", schema_version: 1 },
				dataset_requirements: [],
				cost_model: { bytes_per_run: 100, bytes_per_trading_session: 2 },
				budget: {
					candidate_limit: 128,
					fold_run_limit: 1000,
					trading_session_limit: 1_000_000,
					disk_byte_limit: 100_000_000,
				},
				seed: 42,
				worker_count: 2,
				failure_policy: "continue_candidate_failures",
				created_at: "2026-08-01T01:02:03Z",
			};
			await writeFile(path, JSON.stringify(document).replace('"slippage_bps":10', '"slippage_bps":10.0'), "utf8");

			const loaded = await loadLivePlanningDocument(path);
			expect(loaded).toEqual(document);
			expect(livePlanningJsonFields(loaded).strategySpec).toContain('"slippage_bps":10.0');
			await writeFile(
				path,
				JSON.stringify({ ...document, strategy: { ...document.strategy, strategy_id: "wrong" } }),
				"utf8",
			);
			await expect(loadLivePlanningDocument(path)).rejects.toThrow("stock strategy");
		} finally {
			await rm(root, { recursive: true, force: true });
		}
	});

	it("injects large canonical form values with one input and one change event", async () => {
		const { setNativeFormValue } = await loadAcceptance();
		const textarea = document.createElement("textarea");
		const value = "x".repeat(721_295);
		let inputEvents = 0;
		let changeEvents = 0;
		textarea.addEventListener("input", () => {
			inputEvents += 1;
		});
		textarea.addEventListener("change", () => {
			changeEvents += 1;
		});

		setNativeFormValue(textarea, value);

		expect(textarea.value).toBe(value);
		expect(inputEvents).toBe(1);
		expect(changeEvents).toBe(1);
		expect(() => setNativeFormValue(document.createElement("div"), value)).toThrow("input or textarea");
	});

	it("requires the explicit live runtime opt-in and a non-mock frontend", async () => {
		const { validateLiveRuntime } = await loadAcceptance();

		expect(() => validateLiveRuntime({})).toThrow("VITE_USE_MOCK=false");
		expect(() => validateLiveRuntime({ VITE_USE_MOCK: "true" })).toThrow("VITE_USE_MOCK=false");
		expect(() => validateLiveRuntime({ VITE_USE_MOCK: "false" })).not.toThrow();
	});

	it("distinguishes a resumable live experiment from a not-yet-launched identity", async () => {
		const { liveExperimentExists } = await loadAcceptance();
		const requests: string[] = [];
		const fetcher = async (input: string | URL | Request) => {
			requests.push(String(input));
			return new Response(null, { status: requests.length === 1 ? 404 : 200 });
		};

		await expect(liveExperimentExists("http://127.0.0.1:8000", "exp with spaces", fetcher)).resolves.toBe(false);
		await expect(liveExperimentExists("http://127.0.0.1:8000", "exp with spaces", fetcher)).resolves.toBe(true);
		expect(requests).toEqual([
			"http://127.0.0.1:8000/api/v1/research/experiments/exp%20with%20spaces",
			"http://127.0.0.1:8000/api/v1/research/experiments/exp%20with%20spaces",
		]);
	});

	it("waits for a server-backed control to become enabled instead of sampling it once", async () => {
		const { waitForEnabled } = await loadAcceptance();
		let probes = 0;

		await expect(
			waitForEnabled(
				async () => {
					probes += 1;
					return probes === 3;
				},
				async () => undefined,
				100,
			),
		).resolves.toBeUndefined();
		expect(probes).toBe(3);
		await expect(waitForEnabled(async () => false, async () => undefined, 0)).rejects.toThrow("did not become enabled");
	});

	it("uses persisted experiment truth to choose the live selection path", async () => {
		const { hasPersistedCandidateSelection } = await loadAcceptance();

		expect(hasPersistedCandidateSelection({ selection_state: null }, "exp-1")).toBe(false);
		expect(
			hasPersistedCandidateSelection(
				{ selection_state: { experiment_id: "exp-1", selection_id: "selection-1" } },
				"exp-1",
			),
		).toBe(true);
		expect(() => hasPersistedCandidateSelection({}, "exp-1")).toThrow("selection_state");
		expect(() =>
			hasPersistedCandidateSelection({ selection_state: { experiment_id: "wrong" } }, "exp-1"),
		).toThrow("experiment identity");
	});

	it("binds every approved live browser checkpoint without request interception", async () => {
		const { buildLiveAcceptancePlan } = await loadAcceptance();
		const source = readFileSync(acceptanceScript, "utf8");
		const plan = buildLiveAcceptancePlan();

		expect(plan.map((step) => step.id)).toEqual([
			"studio-preflight-launch",
			"experiment-polling-control",
			"candidate-comparison-evidence",
			"one-shot-holdout",
			"duplicate-holdout-blocked",
			"review-approve-publish",
			"r1-active-version",
			"historical-reactivate",
			"refresh-recovery",
		]);
		expect(plan[1]?.description).toContain("candidate-selection gate");
		expect(plan[3]?.description).toContain("successful terminal state");
		expect(source).toContain('await pause.waitFor({ state: "visible" })');
		expect(source).toContain("Selection evidence is publishing; candidate promotion remains locked.");
		expect(source).toContain("hasPersistedCandidateSelection(serverExperiment, experimentId)");
		expect(source).not.toContain("waitForSelectionActionReady");
		expect(source.match(/await page\.reload\(/gu)).toHaveLength(1);
		expect(source).not.toContain("terminal-before-control");
		expect(source).not.toContain("page.route(");
		expect(source).not.toContain("route.fulfill(");
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
