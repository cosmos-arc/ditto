import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { join, relative, resolve } from "node:path";
import { chromium, type Page } from "playwright";

type FixtureAcceptanceOptions = {
	readonly fixture: true;
	readonly outDir: string;
};

type LiveAcceptanceOptions = {
	readonly realData: true;
	readonly reactBase: string;
	readonly apiBase: string;
	readonly outDir: string;
	readonly planningFile: string;
	readonly timeoutMs: number;
};

type AcceptanceOptions = FixtureAcceptanceOptions | LiveAcceptanceOptions;

type CommandCapture = {
	readonly returncode: number;
	readonly stdout: string;
	readonly stderr: string;
};

type AcceptanceDependencies = {
	readonly checkedAt?: Date;
	readonly sourceCommit?: string;
	readonly runCommand?: (command: readonly string[]) => CommandCapture;
};

type CommandEvidence = CommandCapture & {
	readonly name: "ui-contract-suite";
	readonly command: readonly string[];
	readonly passed: boolean;
	readonly artifact_hashes: {
		readonly command_transcript: string;
	};
};

type AcceptanceReport = {
	readonly schema: "ditto.r3-research-frontend-acceptance";
	readonly version: 1;
	readonly generated_at: string;
	readonly source_commit: string;
	readonly mode: "deterministic_fixture";
	readonly passed: boolean;
	readonly release_status: "RELEASE_ACCEPTANCE_BLOCKED";
	readonly r2_live_gate: "NOT_EVALUATED";
	readonly scope: typeof ACCEPTANCE_SCOPE;
	readonly command: CommandEvidence;
};

type LiveStepId =
	| "studio-preflight-launch"
	| "experiment-polling-control"
	| "candidate-comparison-evidence"
	| "one-shot-holdout"
	| "duplicate-holdout-blocked"
	| "review-approve-publish"
	| "r1-active-version"
	| "historical-reactivate"
	| "refresh-recovery";

type LiveAcceptancePlanStep = {
	readonly id: LiveStepId;
	readonly description: string;
};

type LiveStepResult = LiveAcceptancePlanStep & {
	readonly passed: boolean;
	readonly detail: string;
	readonly screenshot: string;
};

type BrowserNetworkError = {
	readonly method: string;
	readonly url: string;
	readonly status: number | null;
	readonly error: string;
	readonly expected: boolean;
};

type LiveAcceptanceReport = {
	readonly schema: "ditto.r3-research-frontend-acceptance";
	readonly version: 2;
	readonly generated_at: string;
	readonly source_commit: string;
	readonly mode: "real_data";
	readonly passed: boolean;
	readonly release_status: "RELEASE_ACCEPTANCE_PASSED" | "RELEASE_ACCEPTANCE_BLOCKED";
	readonly runtime: "VITE_USE_MOCK=false + Chromium + live loopback API";
	readonly react_base: string;
	readonly api_base: string;
	readonly experiment_id: string | null;
	readonly planning_identity: LivePlanningIdentity;
	readonly timeout_ms: number;
	readonly steps: readonly LiveStepResult[];
	readonly console_errors: readonly string[];
	readonly page_errors: readonly string[];
	readonly network_errors: readonly BrowserNetworkError[];
	readonly trace: string;
};

type LivePlanningDocument = {
	readonly experiment_id: string;
	readonly research_cycle_id: string;
	readonly research_cycle_hash: string;
	readonly strategy: {
		readonly strategy_id: string;
		readonly version: number;
		readonly spec_hash: string;
		readonly spec_json: Readonly<Record<string, unknown>>;
	};
	readonly snapshot: { readonly snapshot_id: string; readonly manifest_hash: string };
	readonly validation: Readonly<Record<string, unknown>>;
	readonly matrix: {
		readonly baseline: {
			readonly descriptor_type: string;
			readonly payload: Readonly<Record<string, unknown>>;
			readonly schema_version: number;
		};
		readonly axes: readonly unknown[];
		readonly candidate_limit: number;
	};
	readonly promotion_objective: Readonly<Record<string, unknown>>;
	readonly dataset_requirements: readonly unknown[];
	readonly cost_model: { readonly bytes_per_run: number; readonly bytes_per_trading_session: number };
	readonly budget: {
		readonly candidate_limit: number;
		readonly fold_run_limit: number;
		readonly trading_session_limit: number;
		readonly disk_byte_limit: number;
	};
	readonly seed: number;
	readonly worker_count: 2 | 4;
	readonly failure_policy: "continue_candidate_failures" | "fail_fast";
	readonly created_at: string;
};

type LivePlanningIdentity = {
	readonly document_sha256: string;
	readonly strategy_id: string;
	readonly strategy_version: number;
	readonly strategy_spec_hash: string;
	readonly snapshot_id: string;
	readonly snapshot_manifest_hash: string;
	readonly research_cycle_hash: string;
	readonly seed: number;
};

type LivePlanningJsonFields = {
	readonly strategySpec: string;
	readonly validation: string;
	readonly promotionObjective: string;
	readonly baselinePayload: string;
	readonly axes: string;
	readonly datasetRequirements: string;
};

const RAW_JSON_NUMBER = Symbol("raw-json-number");
type RawJsonNumber = { readonly [RAW_JSON_NUMBER]: string };
const rawJsonFieldsByPlanning = new WeakMap<object, LivePlanningJsonFields>();

const PROJECT_ROOT = resolve(import.meta.dirname, "..");
const DEFAULT_FIXTURE_OUT_DIR = "docs/review/r3-research-acceptance/deterministic";
const DEFAULT_LIVE_OUT_DIR = "docs/review/r3-research-acceptance/live";
const DEFAULT_REACT_BASE = "http://127.0.0.1:5173";
const DEFAULT_API_BASE = "http://127.0.0.1:8000";
const OUTPUT_LIMIT = 12_000;
const BULK_FIELD_THRESHOLD = 100_000;
const DEFAULT_LIVE_TIMEOUT_MS = 300_000;
const MAX_LIVE_TIMEOUT_MS = 3_600_000;

export const ACCEPTANCE_SCOPE = {
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
} as const;

const FIXTURE_TESTS = [
	"src/features/research/components/experiment-create-page.test.tsx",
	"src/features/research/components/experiment-detail-page.test.tsx",
	"src/features/research/components/experiment-run-recovery.test.tsx",
	"src/features/research/components/review-detail-page.test.tsx",
	"src/features/research/components/review-queue-page.test.tsx",
	"src/features/research/live-boundary.test.tsx",
] as const;

function invariant(condition: unknown, message: string): asserts condition {
	if (!condition) throw new Error(message);
}

function trimTrailingSlash(value: string): string {
	return value.replace(/\/+$/u, "");
}

function assertLoopbackBase(value: string, label: string): void {
	const url = new URL(value);
	invariant(url.protocol === "http:" || url.protocol === "https:", `${label} must use HTTP(S)`);
	invariant(
		url.hostname === "127.0.0.1" || url.hostname === "localhost" || url.hostname === "[::1]",
		`${label} must be a loopback URL, received ${value}`,
	);
}

export function parseAcceptanceArgs(args: readonly string[]): AcceptanceOptions {
	let fixture = false;
	let realData = false;
	let reactBase = DEFAULT_REACT_BASE;
	let apiBase = DEFAULT_API_BASE;
	let outDir: string | null = null;
	let planningFile: string | null = null;
	let timeoutMs = DEFAULT_LIVE_TIMEOUT_MS;

	for (let index = 0; index < args.length; index += 1) {
		const argument = args[index];
		if (argument === "--fixture") {
			fixture = true;
			continue;
		}
		if (argument === "--real-data") {
			realData = true;
			continue;
		}
		if (argument === "--out-dir") {
			const value = args[index + 1];
			invariant(value, "Missing value for --out-dir");
			outDir = value;
			index += 1;
			continue;
		}
		if (argument === "--planning-file") {
			const value = args[index + 1];
			invariant(value, "Missing value for --planning-file");
			planningFile = value;
			index += 1;
			continue;
		}
		if (argument === "--timeout-ms") {
			const value = args[index + 1];
			invariant(value, "Missing value for --timeout-ms");
			invariant(/^\d+$/u.test(value), "--timeout-ms must be an integer");
			timeoutMs = Number.parseInt(value, 10);
			invariant(
				timeoutMs >= DEFAULT_LIVE_TIMEOUT_MS && timeoutMs <= MAX_LIVE_TIMEOUT_MS,
				`--timeout-ms must be between ${DEFAULT_LIVE_TIMEOUT_MS} and ${MAX_LIVE_TIMEOUT_MS}`,
			);
			index += 1;
			continue;
		}
		if (argument === "--react-base" || argument === "--api-base") {
			const value = args[index + 1];
			invariant(value, `Missing value for ${argument}`);
			if (argument === "--react-base") reactBase = trimTrailingSlash(value);
			else apiBase = trimTrailingSlash(value);
			index += 1;
			continue;
		}
		throw new Error(`Unknown option: ${argument}`);
	}

	invariant(fixture !== realData, "exactly one of --fixture or --real-data is required");
	if (fixture) {
		invariant(
				reactBase === DEFAULT_REACT_BASE &&
					apiBase === DEFAULT_API_BASE &&
					planningFile === null &&
					timeoutMs === DEFAULT_LIVE_TIMEOUT_MS,
			"live bases and planning file require --real-data",
		);
		return { fixture: true, outDir: outDir ?? DEFAULT_FIXTURE_OUT_DIR };
	}
	invariant(planningFile, "live acceptance requires --planning-file");
	assertLoopbackBase(reactBase, "React base");
	assertLoopbackBase(apiBase, "API base");
	return { realData: true, reactBase, apiBase, outDir: outDir ?? DEFAULT_LIVE_OUT_DIR, planningFile, timeoutMs };
}

export function validateLiveRuntime(environment: Readonly<Record<string, string | undefined>>): void {
	invariant(environment.VITE_USE_MOCK === "false", "live acceptance requires VITE_USE_MOCK=false");
}

export function buildLiveAcceptancePlan(): readonly LiveAcceptancePlanStep[] {
	return [
		{ id: "studio-preflight-launch", description: "Studio identity, read-only preflight, confirmation, and launch" },
		{
			id: "experiment-polling-control",
			description: "Live experiment polling and pause/resume control through the candidate-selection gate",
		},
		{ id: "candidate-comparison-evidence", description: "Candidate pinning, comparison, and evidence drill-down" },
		{
			id: "one-shot-holdout",
			description: "Candidate selection, one-shot holdout evaluation, and successful terminal state",
		},
		{ id: "duplicate-holdout-blocked", description: "Holdout action remains disabled after the immutable claim" },
		{ id: "review-approve-publish", description: "Submit review, approve the packet, and evidence-gated publish" },
		{ id: "r1-active-version", description: "Browser observes the published R1 active pointer" },
		{ id: "historical-reactivate", description: "Historical published version is reactivated with pointer CAS confirmation" },
		{ id: "refresh-recovery", description: "Hard refresh recovers server state without mock fallback" },
	] as const;
}

export function buildFixtureCommand(): readonly string[] {
	return ["bunx", "vitest", "run", ...FIXTURE_TESTS];
}

function runCommand(command: readonly string[]): CommandCapture {
	const result = spawnSync(command[0], command.slice(1), {
		cwd: PROJECT_ROOT,
		encoding: "utf8",
	});
	return {
		returncode: result.status ?? 1,
		stdout: (result.stdout ?? "").slice(-OUTPUT_LIMIT),
		stderr: (result.stderr ?? "").slice(-OUTPUT_LIMIT),
	};
}

function sourceCommit(): string {
	const result = spawnSync("git", ["rev-parse", "HEAD"], {
		cwd: PROJECT_ROOT,
		encoding: "utf8",
	});
	invariant(result.status === 0, "Unable to resolve frontend source commit");
	return result.stdout.trim();
}

function sha256(payload: string): string {
	return createHash("sha256").update(payload).digest("hex");
}

function canonicalJson(value: unknown): string {
	return `${JSON.stringify(value, null, 2)}\n`;
}

function isRawJsonNumber(value: unknown): value is RawJsonNumber {
	return typeof value === "object" && value !== null && RAW_JSON_NUMBER in value;
}

function stringifyLosslessJson(value: unknown): string {
	if (isRawJsonNumber(value)) return value[RAW_JSON_NUMBER];
	if (value === null || typeof value === "boolean") return JSON.stringify(value);
	if (typeof value === "string") return JSON.stringify(value);
	if (Array.isArray(value)) return `[${value.map(stringifyLosslessJson).join(",")}]`;
	if (typeof value === "object") {
		return `{${Object.entries(value)
			.map(([key, entry]) => `${JSON.stringify(key)}:${stringifyLosslessJson(entry)}`)
			.join(",")}}`;
	}
	throw new Error("lossless planning JSON contained an unsupported value");
}

function parseLosslessJson(source: string): unknown {
	type ReviverContext = { readonly source?: string };
	type ParseWithSource = (
		text: string,
		reviver: (this: unknown, key: string, value: unknown, context: ReviverContext) => unknown,
	) => unknown;
	const parseWithSource = JSON.parse as ParseWithSource;
	return parseWithSource(source, (_key, value, context) => {
		if (typeof value !== "number") return value;
		invariant(context.source !== undefined, "JSON parser did not expose the numeric source token");
		return { [RAW_JSON_NUMBER]: context.source } satisfies RawJsonNumber;
	});
}

function stringifyJsonField(value: unknown): string {
	const encoded = JSON.stringify(value);
	invariant(encoded !== undefined, "planning JSON field could not be serialized");
	return encoded;
}

export function livePlanningJsonFields(document: LivePlanningDocument): LivePlanningJsonFields {
	return (
		rawJsonFieldsByPlanning.get(document) ?? {
			strategySpec: stringifyJsonField(document.strategy.spec_json),
			validation: stringifyJsonField(document.validation),
			promotionObjective: stringifyJsonField(document.promotion_objective),
			baselinePayload: stringifyJsonField(document.matrix.baseline.payload),
			axes: stringifyJsonField(document.matrix.axes),
			datasetRequirements: stringifyJsonField(document.dataset_requirements),
		}
	);
}

function recordValue(value: unknown, label: string): Record<string, unknown> {
	invariant(typeof value === "object" && value !== null && !Array.isArray(value), `${label} must be an object`);
	return value as Record<string, unknown>;
}

function stringValue(record: Readonly<Record<string, unknown>>, key: string): string {
	const value = record[key];
	invariant(typeof value === "string" && value.trim() === value && value.length > 0, `${key} must be a non-empty string`);
	return value;
}

function numberValue(record: Readonly<Record<string, unknown>>, key: string): number {
	const value = record[key];
	invariant(typeof value === "number" && Number.isFinite(value), `${key} must be a finite number`);
	return value;
}

function arrayValue(record: Readonly<Record<string, unknown>>, key: string): readonly unknown[] {
	const value = record[key];
	invariant(Array.isArray(value), `${key} must be an array`);
	return value;
}

/** Load and validate the exact content-addressed backend planning document used by live Studio. */
export async function loadLivePlanningDocument(path: string): Promise<LivePlanningDocument> {
	let parsed: unknown;
	let losslessParsed: unknown;
	try {
		const source = await readFile(resolve(path), "utf8");
		parsed = JSON.parse(source) as unknown;
		losslessParsed = parseLosslessJson(source);
	} catch (error: unknown) {
		throw new Error(`unable to read live planning document: ${browserError(error)}`);
	}
	const root = recordValue(parsed, "planning document");
	const strategy = recordValue(root.strategy, "strategy");
	const snapshot = recordValue(root.snapshot, "snapshot");
	const matrix = recordValue(root.matrix, "matrix");
	const baseline = recordValue(matrix.baseline, "matrix.baseline");
	const costModel = recordValue(root.cost_model, "cost_model");
	const budget = recordValue(root.budget, "budget");
	const strategyId = stringValue(strategy, "strategy_id");
	invariant(strategyId === "seed_stock_selection_rotation", "live browser planning must bind the stock strategy");
	const strategyVersion = numberValue(strategy, "version");
	invariant(Number.isInteger(strategyVersion) && strategyVersion > 1, "strategy version must be a research candidate");
	const candidateLimit = numberValue(matrix, "candidate_limit");
	invariant(candidateLimit === numberValue(budget, "candidate_limit"), "matrix and budget candidate limits must match");
	const workerCount = numberValue(root, "worker_count");
	invariant(workerCount === 2 || workerCount === 4, "worker_count must be 2 or 4");
	const failurePolicy = stringValue(root, "failure_policy");
	invariant(
		failurePolicy === "continue_candidate_failures" || failurePolicy === "fail_fast",
		"failure_policy is unsupported",
	);
	const createdAt = stringValue(root, "created_at");
	invariant(!Number.isNaN(Date.parse(createdAt)) && /(?:Z|[+-]\d{2}:\d{2})$/u.test(createdAt), "created_at must include timezone");
	recordValue(strategy.spec_json, "strategy.spec_json");
	recordValue(root.validation, "validation");
	recordValue(baseline.payload, "matrix.baseline.payload");
	recordValue(root.promotion_objective, "promotion_objective");
	arrayValue(matrix, "axes");
	arrayValue(root, "dataset_requirements");
	stringValue(root, "experiment_id");
	stringValue(root, "research_cycle_id");
	stringValue(root, "research_cycle_hash");
	stringValue(strategy, "spec_hash");
	stringValue(snapshot, "snapshot_id");
	stringValue(snapshot, "manifest_hash");
	stringValue(baseline, "descriptor_type");
	numberValue(baseline, "schema_version");
	numberValue(costModel, "bytes_per_run");
	numberValue(costModel, "bytes_per_trading_session");
	numberValue(budget, "fold_run_limit");
	numberValue(budget, "trading_session_limit");
	numberValue(budget, "disk_byte_limit");
	numberValue(root, "seed");
	const document = parsed as LivePlanningDocument;
	const losslessRoot = recordValue(losslessParsed, "lossless planning document");
	const losslessStrategy = recordValue(losslessRoot.strategy, "lossless strategy");
	const losslessMatrix = recordValue(losslessRoot.matrix, "lossless matrix");
	const losslessBaseline = recordValue(losslessMatrix.baseline, "lossless matrix.baseline");
	rawJsonFieldsByPlanning.set(document, {
		strategySpec: stringifyLosslessJson(losslessStrategy.spec_json),
		validation: stringifyLosslessJson(losslessRoot.validation),
		promotionObjective: stringifyLosslessJson(losslessRoot.promotion_objective),
		baselinePayload: stringifyLosslessJson(losslessBaseline.payload),
		axes: stringifyLosslessJson(losslessMatrix.axes),
		datasetRequirements: stringifyLosslessJson(losslessRoot.dataset_requirements),
	});
	return document;
}

export async function runFixtureAcceptance(
	options: FixtureAcceptanceOptions,
	dependencies: AcceptanceDependencies = {},
): Promise<AcceptanceReport> {
	const command = buildFixtureCommand();
	const capture = (dependencies.runCommand ?? runCommand)(command);
	const transcript = canonicalJson({
		command,
		returncode: capture.returncode,
		stderr: capture.stderr.slice(-OUTPUT_LIMIT),
		stdout: capture.stdout.slice(-OUTPUT_LIMIT),
	});
	const commandEvidence: CommandEvidence = {
		name: "ui-contract-suite",
		command,
		returncode: capture.returncode,
		stdout: capture.stdout.slice(-OUTPUT_LIMIT),
		stderr: capture.stderr.slice(-OUTPUT_LIMIT),
		passed: capture.returncode === 0,
		artifact_hashes: { command_transcript: sha256(transcript) },
	};
	const checkedAt = dependencies.checkedAt ?? new Date();
	const report: AcceptanceReport = {
		schema: "ditto.r3-research-frontend-acceptance",
		version: 1,
		generated_at: checkedAt.toISOString().replace(/\.\d{3}Z$/u, "Z"),
		source_commit: dependencies.sourceCommit ?? sourceCommit(),
		mode: "deterministic_fixture",
		passed: commandEvidence.passed,
		release_status: "RELEASE_ACCEPTANCE_BLOCKED",
		r2_live_gate: "NOT_EVALUATED",
		scope: ACCEPTANCE_SCOPE,
		command: commandEvidence,
	};

	const outDir = resolve(PROJECT_ROOT, options.outDir);
	const reportPath = join(outDir, "report.json");
	await mkdir(outDir, { recursive: true });
	await writeFile(reportPath, canonicalJson(report), "utf8");
	await writeFile(
		join(outDir, "manifest.json"),
		canonicalJson({
			schema: "ditto.r3-research-frontend-evidence-manifest",
			version: 1,
			entries: [
				{
					relative_path: relative(PROJECT_ROOT, reportPath),
					sha256: sha256(canonicalJson(report)),
					mode: report.mode,
					generated_at: report.generated_at,
					source_commit: report.source_commit,
					command: command.join(" "),
				},
			],
		}),
		"utf8",
	);
	return report;
}

function browserError(value: unknown): string {
	return value instanceof Error ? value.message : String(value);
}

function redactedUrl(value: string): string {
	try {
		const url = new URL(value);
		return `${url.origin}${url.pathname}`;
	} catch {
		return value.split("?", 1)[0] ?? value;
	}
}

function isExpectedNetworkStatus(status: number, url: string): boolean {
	return (
		(status === 404 && (url.includes("selection-evidence") || url.includes("candidate-evidence"))) ||
		(status === 409 && url.includes("holdout"))
	);
}

async function sha256File(path: string): Promise<string> {
	return sha256(await readFile(path));
}

async function assertLiveApi(apiBase: string): Promise<void> {
	const response = await fetch(`${apiBase}/healthz`, { signal: AbortSignal.timeout(10_000) });
	invariant(response.ok, `live API health check failed with HTTP ${response.status}`);
	const payload = (await response.json()) as unknown;
	invariant(
		typeof payload === "object" && payload !== null && "status" in payload && payload.status === "ok",
		"live API health response did not report status=ok",
	);
}

type LiveFetch = (input: string | URL | Request, init?: RequestInit) => Promise<Response>;

export async function liveExperimentExists(
	apiBase: string,
	experimentId: string,
	fetcher: LiveFetch = fetch,
): Promise<boolean> {
	const response = await fetcher(
		`${apiBase}/api/v1/research/experiments/${encodeURIComponent(experimentId)}`,
		{ signal: AbortSignal.timeout(30_000) },
	);
	if (response.status === 404) return false;
	invariant(response.ok, `live experiment probe failed with HTTP ${response.status}`);
	return true;
}

async function fillDecision(page: Page, action: string, confirm: string): Promise<void> {
	await page.getByRole("button", { name: action, exact: true }).click();
	await page.getByLabel("执行者").fill("chevy");
	await page.getByLabel("原因").fill(`Task 18 live acceptance: ${action}`);
	await page.getByRole("button", { name: confirm, exact: true }).click();
}

/** Set one controlled text field with exactly one input/change pair. Safe to serialize into Playwright's page context. */
export function setNativeFormValue(element: HTMLElement, value: string): void {
	const prototype =
		element instanceof HTMLTextAreaElement
			? HTMLTextAreaElement.prototype
			: element instanceof HTMLInputElement
				? HTMLInputElement.prototype
				: null;
	if (prototype === null) throw new Error("bulk form value target must be an input or textarea");
	const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
	if (setter === undefined) throw new Error("bulk form value target has no native value setter");
	setter.call(element, value);
	element.dispatchEvent(new Event("input", { bubbles: true }));
	element.dispatchEvent(new Event("change", { bubbles: true }));
}

async function fillPlanningField(page: Page, label: string, value: string): Promise<void> {
	const field = page.getByLabel(label, { exact: true });
	if (value.length < BULK_FIELD_THRESHOLD) {
		await field.fill(value);
		return;
	}
	await field.evaluate(setNativeFormValue, value);
	invariant((await field.inputValue()) === value, `${label} did not retain the complete canonical value`);
}

async function fillLivePlanningDocument(page: Page, document: LivePlanningDocument): Promise<void> {
	const jsonFields = livePlanningJsonFields(document);
	const fields = new Map<string, string>([
		["Experiment ID", document.experiment_id],
		["Research cycle ID", document.research_cycle_id],
		["Research cycle hash", document.research_cycle_hash],
		["Strategy ID", document.strategy.strategy_id],
		["Strategy version", String(document.strategy.version)],
		["Strategy spec hash", document.strategy.spec_hash],
		["Frozen StrategySpec JSON", jsonFields.strategySpec],
		["Snapshot ID", document.snapshot.snapshot_id],
		["Snapshot manifest hash", document.snapshot.manifest_hash],
		["Canonical validation JSON", jsonFields.validation],
		["Promotion objective JSON", jsonFields.promotionObjective],
		["Baseline descriptor", document.matrix.baseline.descriptor_type],
		["Baseline schema version", String(document.matrix.baseline.schema_version)],
		["Candidate limit", String(document.matrix.candidate_limit)],
		["Baseline payload JSON", jsonFields.baselinePayload],
		["Matrix axes JSON", jsonFields.axes],
		["Dataset requirements JSON", jsonFields.datasetRequirements],
		["Bytes per run", String(document.cost_model.bytes_per_run)],
		["Bytes per trading session", String(document.cost_model.bytes_per_trading_session)],
		["Fold run limit", String(document.budget.fold_run_limit)],
		["Trading session limit", String(document.budget.trading_session_limit)],
		["Disk byte limit", String(document.budget.disk_byte_limit)],
		["Seed", String(document.seed)],
		["Created at", document.created_at],
	]);
	for (const [label, value] of fields) await fillPlanningField(page, label, value);
	await page.getByLabel("Worker count", { exact: true }).selectOption(String(document.worker_count));
	await page.getByLabel("Failure policy", { exact: true }).selectOption(document.failure_policy);
}

async function screenshot(page: Page, outDir: string, id: LiveStepId): Promise<string> {
	const path = join(outDir, `${id}.png`);
	await page.screenshot({ path, fullPage: true });
	return relative(PROJECT_ROOT, path);
}

async function executeLiveStep(
	page: Page,
	outDir: string,
	step: LiveAcceptancePlanStep,
	action: () => Promise<string>,
): Promise<LiveStepResult> {
	let passed = false;
	let detail: string;
	try {
		detail = await action();
		passed = true;
	} catch (error: unknown) {
		detail = browserError(error);
	}
	let screenshotPath = "";
	try {
		screenshotPath = await screenshot(page, outDir, step.id);
	} catch (error: unknown) {
		passed = false;
		detail = `${detail}; screenshot failed: ${browserError(error)}`;
	}
	return { ...step, passed, detail, screenshot: screenshotPath };
}

function responseData(value: unknown): Record<string, unknown> | null {
	if (typeof value !== "object" || value === null || !("data" in value)) return null;
	const data = value.data;
	return typeof data === "object" && data !== null ? (data as Record<string, unknown>) : null;
}

async function browserApiGet(page: Page, path: string): Promise<Record<string, unknown>> {
	const payload = await page.evaluate(async (apiPath) => {
		const response = await fetch(apiPath);
		if (!response.ok) throw new Error(`browser API GET ${apiPath} failed with HTTP ${response.status}`);
		return (await response.json()) as unknown;
	}, path);
	const data = responseData(payload);
	invariant(data, `browser API GET ${path} returned no data object`);
	return data;
}

export async function runLiveAcceptance(options: LiveAcceptanceOptions): Promise<LiveAcceptanceReport> {
	validateLiveRuntime(process.env);
	await assertLiveApi(options.apiBase);
	const planning = await loadLivePlanningDocument(options.planningFile);
	const planningIdentity: LivePlanningIdentity = {
		document_sha256: await sha256File(resolve(options.planningFile)),
		strategy_id: planning.strategy.strategy_id,
		strategy_version: planning.strategy.version,
		strategy_spec_hash: planning.strategy.spec_hash,
		snapshot_id: planning.snapshot.snapshot_id,
		snapshot_manifest_hash: planning.snapshot.manifest_hash,
		research_cycle_hash: planning.research_cycle_hash,
		seed: planning.seed,
	};

	const outDir = resolve(PROJECT_ROOT, options.outDir);
	await mkdir(outDir, { recursive: true });
	const tracePath = join(outDir, "trace.zip");
	const consoleErrors: string[] = [];
	const pageErrors: string[] = [];
	const networkErrors: BrowserNetworkError[] = [];
	const steps: LiveStepResult[] = [];
	const plan = buildLiveAcceptancePlan();
	const browser = await chromium.launch({ headless: true });
	const context = await browser.newContext({ viewport: { width: 1536, height: 960 } });
	await context.tracing.start({ screenshots: true, snapshots: true, sources: false });
	const page = await context.newPage();
	page.setDefaultTimeout(options.timeoutMs);
	page.on("console", (message) => {
		if (message.type() === "error") consoleErrors.push(message.text().slice(0, OUTPUT_LIMIT));
	});
	page.on("pageerror", (error) => pageErrors.push(error.message.slice(0, OUTPUT_LIMIT)));
	page.on("requestfailed", (request) => {
		networkErrors.push({
			method: request.method(),
			url: redactedUrl(request.url()),
			status: null,
			error: request.failure()?.errorText ?? "request failed",
			expected: false,
		});
	});
	page.on("response", (response) => {
		if (response.status() < 400) return;
		const url = redactedUrl(response.url());
		networkErrors.push({
			method: response.request().method(),
			url,
			status: response.status(),
			error: response.statusText(),
			expected: isExpectedNetworkStatus(response.status(), url),
		});
	});

	let experimentId: string | null = planning.experiment_id;
	let promotedVersion: number | null = null;
	let resumedExistingExperiment = false;
	const strategyId = planning.strategy.strategy_id;
	try {
		steps.push(
			await executeLiveStep(page, outDir, plan[0], async () => {
				await page.goto(`${options.reactBase}/research/strategies/${strategyId}/studio`, {
					waitUntil: "domcontentloaded",
				});
				await page.locator('[data-info-unit="strategy-header"]').waitFor();
				await page.goto(`${options.reactBase}/research/experiments/new`, { waitUntil: "domcontentloaded" });
				await fillLivePlanningDocument(page, planning);
				await page.getByRole("button", { name: "运行只读 Preflight" }).click();
				const confirmation = page.getByRole("checkbox", { name: /确认 plan hash/u });
				await confirmation.waitFor({ state: "visible" });
				await expectEnabled(confirmation);
				const history = await page.getByText(/\d+ 个月/u).first().textContent();
				const months = Number.parseInt(history?.match(/\d+/u)?.[0] ?? "0", 10);
				invariant(months >= 96, `preflight eligible history was ${months}, expected at least 96 months`);
				await confirmation.check();
				if (experimentId && (await liveExperimentExists(options.apiBase, experimentId))) {
					resumedExistingExperiment = true;
					await page.goto(`${options.reactBase}/research/experiments/${experimentId}`, {
						waitUntil: "domcontentloaded",
					});
					return `verified ${months}-month live preflight and resumed already-launched ${experimentId}`;
				}
				await page.getByRole("button", { name: "启动实验" }).click();
				await page.waitForURL(new RegExp(`/research/experiments/${experimentId}$`, "u"));
				return `launched ${experimentId} after ${months}-month live preflight`;
			}),
		);

		steps.push(
			await executeLiveStep(page, outDir, plan[1], async () => {
				invariant(experimentId, "experiment launch did not produce an identity");
				const header = page.getByRole("heading", { name: `Experiment ${experimentId}` });
				await header.waitFor();
				const pause = page.getByRole("button", { name: "暂停", exact: true });
				let control: string;
				if (!resumedExistingExperiment) {
					await pause.waitFor({ state: "visible" });
					await expectEnabled(pause);
					await pause.click();
					const resume = page.getByRole("button", { name: "恢复", exact: true });
					await expectEnabled(resume);
					await resume.click();
					control = "pause-resume";
				} else {
					control = "resumed-existing-server-truth";
				}
				await page
					.locator('[data-contract-slot="experiment-meta"]')
					.getByText(/candidate_selection/iu)
					.waitFor();
				return `polling reached the candidate-selection gate; control=${control}`;
			}),
		);

		steps.push(
			await executeLiveStep(page, outDir, plan[2], async () => {
				const select = page.locator('button[data-candidate-role="eligible"]').first();
				await select.waitFor();
				const candidateRow = select.locator("xpath=..");
				const pin = candidateRow.getByRole("checkbox", { name: /^Pin /u });
				await pin.check();
				await page.getByLabel("晋级理由").fill("Task 18 live objective and evidence review");
				await candidateRow.getByRole("button", { name: "查看证据" }).click();
				await page.getByRole("heading", { name: /Candidate evidence/u }).waitFor();
				await page.getByText("factor-contributions", { exact: true }).waitFor();
				const recoveredHoldout = page.getByRole("button", { name: "执行一次性 Holdout" });
				if (await recoveredHoldout.isVisible()) {
					await expectEnabled(recoveredHoldout);
					return `inspected live comparison and evidence for ${await pin.getAttribute("aria-label")}; recovered persisted candidate selection`;
				}
				await page
					.getByText("Selection evidence is publishing; candidate promotion remains locked.", { exact: true })
					.waitFor({ state: "hidden" });
				await expectEnabled(select);
				return `inspected live comparison and evidence for ${await pin.getAttribute("aria-label")}`;
			}),
		);

		steps.push(
			await executeLiveStep(page, outDir, plan[3], async () => {
				const select = page.locator('button[data-candidate-role="eligible"]').first();
				const holdout = page.getByRole("button", { name: "执行一次性 Holdout" });
				if (!(await holdout.isVisible())) {
					await expectEnabled(select);
					await select.click();
				}
				await holdout.waitFor();
				await holdout.click();
				const claim = page.getByText(/^claim /u);
				await claim.waitFor();
				const claimDetail = (await claim.textContent()) ?? "holdout claim persisted";
				await page
					.locator('[data-contract-slot="experiment-meta"]')
					.getByText(/completed|succeeded/iu)
					.waitFor();
				return `${claimDetail}; experiment reached a successful terminal state`;
			}),
		);

		steps.push(
			await executeLiveStep(page, outDir, plan[4], async () => {
				const holdout = page.getByRole("button", { name: "执行一次性 Holdout" });
				invariant(await holdout.isDisabled(), "holdout button remained enabled after immutable claim");
				return "duplicate holdout action is disabled after the first server claim";
			}),
		);

		steps.push(
			await executeLiveStep(page, outDir, plan[5], async () => {
				await page.goto(`${options.reactBase}/research/strategies/${strategyId}`, { waitUntil: "domcontentloaded" });
				await page.getByRole("tab", { name: "版本" }).click();
				await fillDecision(page, "提交审查", "确认提交");
				await page.goto(`${options.reactBase}/research/reviews`, { waitUntil: "domcontentloaded" });
				const review = page.getByRole("link").filter({ hasText: strategyId }).first();
				await review.waitFor();
				const href = await review.getAttribute("href");
				invariant(href, "review queue entry did not expose a route");
				promotedVersion = Number.parseInt(new URL(href, options.reactBase).searchParams.get("version") ?? "0", 10);
				invariant(promotedVersion > 0, "review queue entry had no strategy version");
				await review.click();
				await fillDecision(page, "批准", "确认批准");
				const publish = page.getByRole("button", { name: "发布", exact: true });
				await publish.waitFor();
				await publish.click();
				await page.getByLabel("执行者").fill("chevy");
				await page.getByLabel("原因").fill("Task 18 evidence-gated live publish");
				await page.getByLabel("确认句").fill(`发布 v${promotedVersion}`);
				await page.getByRole("button", { name: "确认发布" }).click();
				await page.getByText("published", { exact: true }).waitFor();
				return `approved and published ${strategyId}@${promotedVersion}`;
			}),
		);

		steps.push(
			await executeLiveStep(page, outDir, plan[6], async () => {
				const active = await browserApiGet(page, `/api/v1/strategies/${strategyId}/active`);
				invariant(active.active_version === promotedVersion, "R1 active pointer did not select the published version");
				invariant(typeof active.pointer_revision === "number", "R1 active pointer revision was missing");
				return `R1 active=${String(active.active_version)} pointer_revision=${String(active.pointer_revision)}`;
			}),
		);

		steps.push(
			await executeLiveStep(page, outDir, plan[7], async () => {
				invariant(promotedVersion, "published version was not recorded");
				await page.goto(`${options.reactBase}/research/strategies/${strategyId}`, { waitUntil: "domcontentloaded" });
				await page.getByRole("tab", { name: "版本" }).click();
				const reactivate = page.getByRole("button", { name: "重新激活" });
				await reactivate.first().waitFor();
				let target = 0;
				for (let index = 0; index < (await reactivate.count()); index += 1) {
					await reactivate.nth(index).click();
					const heading = page.getByRole("heading", { name: /重新激活 v\d+/u });
					const title = (await heading.textContent()) ?? "";
					target = Number.parseInt(title.match(/\d+/u)?.[0] ?? "0", 10);
					if (target !== promotedVersion) break;
					await page.getByRole("button", { name: "取消" }).click();
				}
				invariant(target > 0 && target !== promotedVersion, "no historical published version was available");
				await page.getByLabel("执行者").fill("chevy");
				await page.getByLabel("原因").fill("Task 18 historical rollback verification");
				await page.getByLabel("影响摘要").fill("Verify R1 active-pointer recovery on certified evidence");
				const confirmationText = (await page.getByText(/strategy:reactivate:.*:confirm/u).textContent()) ?? "";
				const confirmation = confirmationText.match(/strategy:reactivate:[^」\s]+:confirm/u)?.[0];
				invariant(confirmation, "reactivate confirmation identity was not rendered");
				await page.getByLabel("确认句").fill(confirmation);
				await page.getByRole("button", { name: "确认重新激活" }).click();
				await page.getByRole("heading", { name: /重新激活 v\d+/u }).waitFor({ state: "hidden" });
				return `reactivated historical ${strategyId}@${target}`;
			}),
		);

		steps.push(
			await executeLiveStep(page, outDir, plan[8], async () => {
				await page.reload({ waitUntil: "domcontentloaded" });
				await page.getByText("版本历史").waitFor();
				invariant(page.url().startsWith(options.reactBase), "refresh escaped the approved React origin");
				return "hard refresh recovered the live strategy versions and active-pointer view";
			}),
		);
	} finally {
		await context.tracing.stop({ path: tracePath });
		await browser.close();
	}

	const unexpectedNetworkErrors = networkErrors.filter((error) => !error.expected);
	const passed =
		steps.length === plan.length &&
		steps.every((step) => step.passed) &&
		consoleErrors.length === 0 &&
		pageErrors.length === 0 &&
		unexpectedNetworkErrors.length === 0;
	const generatedAt = new Date().toISOString().replace(/\.\d{3}Z$/u, "Z");
	const report: LiveAcceptanceReport = {
		schema: "ditto.r3-research-frontend-acceptance",
		version: 2,
		generated_at: generatedAt,
		source_commit: sourceCommit(),
		mode: "real_data",
		passed,
		release_status: passed ? "RELEASE_ACCEPTANCE_PASSED" : "RELEASE_ACCEPTANCE_BLOCKED",
		runtime: "VITE_USE_MOCK=false + Chromium + live loopback API",
		react_base: options.reactBase,
		api_base: options.apiBase,
		experiment_id: experimentId,
		planning_identity: planningIdentity,
		timeout_ms: options.timeoutMs,
		steps,
		console_errors: consoleErrors,
		page_errors: pageErrors,
		network_errors: networkErrors,
		trace: relative(PROJECT_ROOT, tracePath),
	};
	const reportPath = join(outDir, "report.json");
	const networkPath = join(outDir, "network-errors.json");
	await writeFile(reportPath, canonicalJson(report), "utf8");
	await writeFile(networkPath, canonicalJson(networkErrors), "utf8");
	const evidencePaths = [reportPath, networkPath, tracePath, ...steps.map((step) => resolve(PROJECT_ROOT, step.screenshot))];
	await writeFile(
		join(outDir, "manifest.json"),
		canonicalJson({
			schema: "ditto.r3-research-frontend-evidence-manifest",
			version: 2,
			generated_at: generatedAt,
			source_commit: report.source_commit,
			mode: report.mode,
			entries: await Promise.all(
				evidencePaths.map(async (path) => ({
					relative_path: relative(PROJECT_ROOT, path),
					sha256: await sha256File(path),
				})),
			),
		}),
		"utf8",
	);
	return report;
}

export async function waitForEnabled(
	probe: () => Promise<boolean>,
	pause: (milliseconds: number) => Promise<unknown>,
	timeoutMs = 300_000,
): Promise<void> {
	const startedAt = Date.now();
	while (!(await probe())) {
		if (Date.now() - startedAt >= timeoutMs) throw new Error(`element did not become enabled within ${timeoutMs}ms`);
		await pause(500);
	}
}

async function expectEnabled(locator: ReturnType<Page["getByRole"]>): Promise<void> {
	await locator.waitFor({ state: "visible" });
	await waitForEnabled(
		() => locator.isEnabled(),
		(milliseconds) => locator.page().waitForTimeout(milliseconds),
	);
}

async function main(args: readonly string[]): Promise<void> {
	const options = parseAcceptanceArgs(args);
	const report = "fixture" in options ? await runFixtureAcceptance(options) : await runLiveAcceptance(options);
	console.log(canonicalJson(report));
	if (!report.passed) process.exitCode = 1;
}

if (import.meta.main) {
	main(process.argv.slice(2)).catch((error: unknown) => {
		console.error(error instanceof Error ? error.message : error);
		process.exit(1);
	});
}
