import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join, relative, resolve } from "node:path";
import { type Browser, type BrowserContextOptions, chromium, type Locator, type Page, type Route } from "playwright";
import type { components } from "../src/types/generated/api";

type DailyDecisionV2Response = components["schemas"]["DailyDecisionV2Response"];
type FillAdjustmentResponse = components["schemas"]["FillAdjustmentResponse"];
type FillResponse = components["schemas"]["FillResponse"];
type RecordFillRequest = components["schemas"]["RecordFillRequest"];
type ReplaceFillRequest = components["schemas"]["ReplaceFillRequest"];
type VoidFillRequest = components["schemas"]["VoidFillRequest"];
type ReadinessState = DailyDecisionV2Response["readiness"]["status"];

type AcceptanceOptions = {
	readonly reactBase: string;
	readonly outDir: string;
};

type AcceptanceViewport = {
	readonly name: "desktop" | "mobile";
	readonly width: number;
	readonly height: number;
};

type EvidenceScenario =
	| "blocked"
	| "review"
	| "review-fills"
	| "ready"
	| "fill-review"
	| "multi-fill-ledger"
	| "fill-correction";

type EvidenceCase = {
	readonly viewport: AcceptanceViewport;
	readonly scenario: EvidenceScenario;
};

type EvidenceRecord = EvidenceCase & {
	readonly route: string;
	readonly screenshot: string;
	readonly assertions: readonly string[];
};

const PROJECT_ROOT = resolve(import.meta.dirname, "..");
const DEFAULT_OPTIONS: AcceptanceOptions = {
	reactBase: "http://127.0.0.1:5173",
	outDir: "docs/review/r1-trading-acceptance",
};
export const ACCEPTANCE_SCOPE = {
	runtime: "VITE_USE_MOCK=false",
	apiData: "Playwright route fixtures for DailyDecision V2, raw/effective fills, adjustments, and correction mutations",
	proves: "frontend state, visual, append-only correction interaction, accessibility, and scroll behavior only",
	doesNotProve: "Task6 live backend persistence/E2E or production data correctness",
} as const;
const STRATEGY_ID = "seed_etf_industry_rotation";
const ACCOUNT_ID = "paper-r1";
const SIGNAL_DATE = "2026-07-16";
const ROUTE_QUERY = `strategy_id=${STRATEGY_ID}&account_id=${ACCOUNT_ID}&trade_date=${SIGNAL_DATE}`;
const ACCEPTANCE_VIEWPORTS: readonly AcceptanceViewport[] = [
	{ name: "desktop", width: 1536, height: 900 },
	{ name: "mobile", width: 390, height: 844 },
];
const EVIDENCE_SCENARIOS: readonly EvidenceScenario[] = [
	"blocked",
	"review",
	"review-fills",
	"ready",
	"fill-review",
	"multi-fill-ledger",
	"fill-correction",
];
const VISUAL_STABILITY_CSS = `
	*, *::before, *::after {
		caret-color: transparent !important;
		scroll-behavior: auto !important;
		transition-duration: 0s !important;
		transition-delay: 0s !important;
	}
	.reveal-up {
		opacity: 1 !important;
		transform: none !important;
	}
`;

function invariant(condition: unknown, message: string): asserts condition {
	if (!condition) throw new Error(message);
}

function trimTrailingSlash(value: string): string {
	return value.replace(/\/+$/u, "");
}

function assertLoopbackBase(value: string): void {
	const url = new URL(value);
	invariant(
		url.hostname === "127.0.0.1" || url.hostname === "localhost" || url.hostname === "::1",
		`R1 acceptance only permits loopback React bases, received ${value}`,
	);
}

export function parseAcceptanceArgs(args: readonly string[]): AcceptanceOptions {
	const options = { ...DEFAULT_OPTIONS };

	for (let index = 0; index < args.length; index += 1) {
		const arg = args[index];
		const next = args[index + 1];
		invariant(next, `Missing value for ${arg}`);

		if (arg === "--react-base") {
			options.reactBase = trimTrailingSlash(next);
		} else if (arg === "--out-dir") {
			options.outDir = next;
		} else {
			throw new Error(`Unknown option: ${arg}`);
		}
		index += 1;
	}

	assertLoopbackBase(options.reactBase);
	return options;
}

export function buildEvidenceCases(): readonly EvidenceCase[] {
	return ACCEPTANCE_VIEWPORTS.flatMap((viewport) => EVIDENCE_SCENARIOS.map((scenario) => ({ viewport, scenario })));
}

function buildEffectiveFills(): FillResponse[] {
	return [
		{
			fill_id: "fill-intent-510300-001",
			intent_id: "intent-510300",
			strategy_id: STRATEGY_ID,
			trade_date: "2026-07-17",
			instrument_id: 510300,
			direction: "buy",
			quantity: 250,
			fill_price: 4.31,
			fee: 1.2,
			slippage: 0.01,
			notes: "manual paper fill 1/2",
			settlement_date: "2026-07-20",
		},
		{
			fill_id: "fill-intent-510300-002",
			intent_id: "intent-510300",
			strategy_id: STRATEGY_ID,
			trade_date: "2026-07-17",
			instrument_id: 510300,
			direction: "buy",
			quantity: 350,
			fill_price: 4.32,
			fee: 1.4,
			slippage: 0.02,
			notes: "manual paper fill 2/2",
			settlement_date: "2026-07-20",
		},
	];
}

export function buildDecisionReport(state: ReadinessState): DailyDecisionV2Response {
	const isBlocked = state === "blocked";
	const isReview = state === "review";
	const reasonCode = isBlocked ? "ACCOUNT_BASELINE_MISSING" : isReview ? "RISK_WARNING" : "READY_FOR_REVIEW";
	const effectiveFills = buildEffectiveFills();

	return {
		identity: {
			strategy_id: STRATEGY_ID,
			strategy_version: "r1",
			account_id: ACCOUNT_ID,
			sleeve_id: `manual-${ACCOUNT_ID}-${STRATEGY_ID}`,
			signal_date: SIGNAL_DATE,
			decision_date: SIGNAL_DATE,
			intended_trade_date: "2026-07-17",
		},
		readiness: {
			status: state,
			reason_codes: [reasonCode],
			details: [
				isBlocked
					? "账户基线缺失，交易动作保持关闭"
					: isReview
						? "风险证据需要人工复核"
						: "必要证据齐备，可进入人工执行",
			],
		},
		data: {
			required_datasets: ["etf_daily"],
			snapshot_ids: { etf_daily: "sha256:r1-etf-daily-20260716" },
			dataset_states: [
				{
					dataset: "etf_daily",
					status: "ready",
					snapshot_id: "sha256:r1-etf-daily-20260716",
					reason: "",
				},
			],
			freshness: "ready",
			dq_state: "passed",
		},
		run_package: {
			outcome: "completed",
			batch_key: `eod-${SIGNAL_DATE}-${STRATEGY_ID}-r1`,
			artifact_id: `signal-package-${STRATEGY_ID}-${SIGNAL_DATE}-r1`,
			checksum: "sha256:r1-acceptance-signal-package",
			checksum_valid: true,
			no_rebalance: false,
			factor_evidence: { "510300": { momentum_20d: 0.82 } },
			risk_evidence: isReview ? ["RISK_WARNING"] : [],
		},
		account_positions: {
			baseline_id: isBlocked ? null : "baseline-paper-r1-20260716",
			account_id: ACCOUNT_ID,
			sleeve_id: `manual-${ACCOUNT_ID}-${STRATEGY_ID}`,
			cash_available: isBlocked ? null : 60_000,
			cash_settled: isBlocked ? null : 60_000,
			cash_frozen: isBlocked ? null : 0,
			total_value: isBlocked ? null : 100_000,
			nav: isBlocked ? null : 1,
			exposure: isBlocked ? null : 40_000,
			as_of: isBlocked ? null : SIGNAL_DATE,
			positions: isBlocked
				? []
				: [
						{
							snapshot_id: "position-510300-r1",
							strategy_id: STRATEGY_ID,
							snapshot_date: SIGNAL_DATE,
							instrument_id: 510300,
							quantity: 1_000,
							available_quantity: 800,
							average_cost: 4.12,
							market_value: 4_320,
							unrealized_pnl: 180,
							realized_pnl: 20,
							total_fees: 3,
						},
					],
		},
		actions: [
			{
				intent_id: "intent-510300",
				instrument_id: 510300,
				direction: "buy",
				target_weight: 0.3,
				current_weight: 0.12,
				delta_weight: 0.18,
				raw_quantity: 1_050,
				rounded_quantity: 1_000,
				suggested_quantity: 1_000,
				reference_price: 4.31,
				lot_size: 100,
				cash_impact: -4_310,
				reason: "rounded_down_to_board_lot",
				sizing_readiness: "ready",
				risk_flags: isReview ? ["RISK_WARNING"] : [],
				intent_status: "partially_filled",
				filled_quantity: 600,
				remaining_quantity: 400,
			},
		],
		execution_review: {
			effective_fills: effectiveFills,
			deviation: {
				strategy_id: STRATEGY_ID,
				signal_date: SIGNAL_DATE,
				total_signals: 1,
				filled: 1,
				unfilled: 0,
				items: [
					{
						instrument_id: 510300,
						signal_action: "buy",
						signal_weight: 0.3,
						actual_weight: 0.18,
						deviation_bps: 120,
						fill_status: "partial",
					},
				],
			},
			pnl: {
				total_realized_pnl: 20,
				total_unrealized_pnl: 180,
				total_fees: 3,
				net_pnl: 197,
			},
			exceptions: [],
			unresolved_conflicts: [],
		},
	};
}

function browserViewport(viewport: AcceptanceViewport): BrowserContextOptions["viewport"] {
	return { width: viewport.width, height: viewport.height };
}

export function shouldIgnoreAcceptanceRequestFailure(resourceType: string, errorText: string): boolean {
	return resourceType === "script" && errorText === "net::ERR_ABORTED";
}

function createPageIssueCollector(page: Page): string[] {
	const issues: string[] = [];
	page.on("pageerror", (error) => issues.push(`pageerror: ${error.message}`));
	page.on("console", (message) => {
		if (message.type() === "error") issues.push(`console: ${message.text()}`);
	});
	page.on("requestfailed", (request) => {
		const errorText = request.failure()?.errorText ?? "unknown";
		if (shouldIgnoreAcceptanceRequestFailure(request.resourceType(), errorText)) return;
		issues.push(`requestfailed: ${request.method()} ${request.url()} ${errorText}`);
	});
	return issues;
}

type TradingFixtureState = {
	readonly rawFills: FillResponse[];
	readonly adjustments: FillAdjustmentResponse[];
};

function effectiveFixtureFills(state: TradingFixtureState): FillResponse[] {
	const adjustedIds = new Set(state.adjustments.map((adjustment) => adjustment.fill_id));
	return state.rawFills.filter((fill) => !adjustedIds.has(fill.fill_id));
}

function paginated<T>(data: readonly T[]) {
	return { data, pagination: { total: data.length, limit: data.length, offset: 0, has_more: false } };
}

async function fulfillJson(route: Route, data: unknown, status = 200): Promise<void> {
	await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(data) });
}

function correctionFillId(pathname: string, action: "void" | "replace"): string | null {
	const match = pathname.match(new RegExp(`/api/v1/trade/fills/([^/]+)/${action}$`, "u"));
	return match ? decodeURIComponent(match[1]) : null;
}

function createAdjustment(params: {
	readonly adjustmentId: string;
	readonly fillId: string;
	readonly type: "void" | "replace";
	readonly reason: string;
	readonly replacementFillId: string | null;
}): FillAdjustmentResponse {
	return {
		adjustment_id: params.adjustmentId,
		fill_id: params.fillId,
		adjustment_type: params.type,
		replacement_fill_id: params.replacementFillId,
		reason: params.reason,
		created_at: "2026-07-16T12:00:00+08:00",
	};
}

async function fulfillVoid(route: Route, state: TradingFixtureState, fillId: string): Promise<void> {
	const payload = route.request().postDataJSON() as VoidFillRequest;
	const replay = state.adjustments.find((item) => item.adjustment_id === payload.adjustment_id);
	if (replay) return fulfillJson(route, { data: replay });
	if (!effectiveFixtureFills(state).some((fill) => fill.fill_id === fillId)) {
		return fulfillJson(route, { detail: `fill ${fillId} was already adjusted` }, 409);
	}
	const adjustment = createAdjustment({
		adjustmentId: payload.adjustment_id,
		fillId,
		type: "void",
		reason: payload.reason,
		replacementFillId: null,
	});
	state.adjustments.push(adjustment);
	return fulfillJson(route, { data: adjustment });
}

async function fulfillReplace(route: Route, state: TradingFixtureState, fillId: string): Promise<void> {
	const payload = route.request().postDataJSON() as ReplaceFillRequest;
	const replay = state.adjustments.find((item) => item.adjustment_id === payload.adjustment_id);
	if (replay) return fulfillJson(route, { data: replay });
	const original = effectiveFixtureFills(state).find((fill) => fill.fill_id === fillId);
	if (!original) return fulfillJson(route, { detail: `fill ${fillId} was already adjusted` }, 409);
	const replacement: FillResponse = {
		...original,
		fill_id: payload.replacement_fill_id,
		trade_date: payload.trade_date,
		quantity: payload.quantity,
		fill_price: payload.fill_price,
		fee: payload.fee,
		slippage: payload.slippage,
		notes: payload.notes,
		settlement_date: payload.trade_date,
	};
	const adjustment = createAdjustment({
		adjustmentId: payload.adjustment_id,
		fillId,
		type: "replace",
		reason: payload.reason,
		replacementFillId: replacement.fill_id,
	});
	state.rawFills.push(replacement);
	state.adjustments.push(adjustment);
	return fulfillJson(route, { data: adjustment });
}

async function fulfillTradingFixture(
	route: Route,
	report: DailyDecisionV2Response,
	state: TradingFixtureState,
): Promise<void> {
	const request = route.request();
	const pathname = new URL(request.url()).pathname;
	if (pathname === "/api/v1/trade/daily-decision/v2") return fulfillJson(route, { data: report });
	if (pathname === "/api/v1/trade/fill-adjustments") return fulfillJson(route, paginated(state.adjustments));
	if (pathname === "/api/v1/trade/fills/effective") return fulfillJson(route, paginated(effectiveFixtureFills(state)));
	const voidFillId = correctionFillId(pathname, "void");
	if (voidFillId && request.method() === "POST") return fulfillVoid(route, state, voidFillId);
	const replaceFillId = correctionFillId(pathname, "replace");
	if (replaceFillId && request.method() === "POST") return fulfillReplace(route, state, replaceFillId);
	if (pathname === "/api/v1/trade/fills" && request.method() === "GET") {
		return fulfillJson(route, paginated(state.rawFills));
	}
	if (pathname === "/api/v1/trade/fills" && request.method() === "POST") {
		const payload = request.postDataJSON() as RecordFillRequest;
		const fill: FillResponse = { ...payload, settlement_date: payload.trade_date };
		return fulfillJson(route, { data: fill });
	}
	await route.fallback();
}

async function installApiRoutes(page: Page, report: DailyDecisionV2Response): Promise<readonly string[]> {
	const requests: string[] = [];
	const state: TradingFixtureState = { rawFills: buildEffectiveFills(), adjustments: [] };
	page.on("request", (request) => requests.push(request.url()));
	await page.route("**/api/v1/trade/**", (route) => fulfillTradingFixture(route, report, state));
	return requests;
}

async function openLivePage(page: Page, reactBase: string, route: string, requests: readonly string[]): Promise<void> {
	const url = `${reactBase}${route}${route.includes("?") ? "&" : "?"}${ROUTE_QUERY}`;
	const response = await page.goto(url, { waitUntil: "load", timeout: 30_000 });
	invariant(response?.ok(), `Failed to load ${url}: ${response?.status() ?? "no response"}`);
	await page.waitForFunction(() => document.fonts.ready);
	await page.addStyleTag({ content: VISUAL_STABILITY_CSS });

	const usesPrototypeMocks = await page.evaluate(async () => {
		const runtimeModulePath = "/src/features/portfolio/api/runtime.ts";
		const runtime = await import(runtimeModulePath);
		return runtime.shouldUsePrototypeMocks();
	});
	invariant(!usesPrototypeMocks, "React dev server is not running with VITE_USE_MOCK=false");
	invariant(!requests.some((item) => item.includes("/mockServiceWorker.js")), "Mock service worker was requested");
	invariant(
		!requests.some((item) => new URL(item).pathname.startsWith("/api/trading/")),
		"A prototype-only /api/trading endpoint was requested",
	);
	invariant(
		!(await page.getByText("1.0842", { exact: true }).isVisible()),
		"Prototype portfolio value leaked into live mode",
	);
}

async function assertScrollable(locator: Locator, page: Page, label: string): Promise<void> {
	const before = await locator.evaluate((element) => ({
		scrollTop: element.scrollTop,
		clientHeight: element.clientHeight,
		scrollHeight: element.scrollHeight,
		overflowY: getComputedStyle(element).overflowY,
	}));
	invariant(before.overflowY === "auto" || before.overflowY === "scroll", `${label} does not own vertical scrolling`);
	invariant(before.scrollHeight > before.clientHeight, `${label} is not exercising an overflowing state`);

	await locator.hover();
	await page.mouse.wheel(0, Math.max(500, before.clientHeight));
	await page.waitForTimeout(100);
	const after = await locator.evaluate((element) => element.scrollTop);
	invariant(after > before.scrollTop, `${label} did not respond to a wheel gesture`);
	await page.evaluate(() => {
		if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
	});
	const resetScrollTop = await locator.evaluate((element) => {
		element.style.scrollBehavior = "auto";
		element.style.overflowAnchor = "none";
		element.scrollTop = 0;
		return element.scrollTop;
	});
	invariant(resetScrollTop === 0, `${label} did not reset to the top deterministically`);
	await page.evaluate(
		() =>
			new Promise<void>((resolveFrame) => {
				requestAnimationFrame(() => requestAnimationFrame(() => resolveFrame()));
			}),
	);
	invariant((await locator.evaluate((element) => element.scrollTop)) === 0, `${label} drifted after reset`);
	const documentScroll = await page.evaluate(() => {
		document.documentElement.style.scrollBehavior = "auto";
		document.body.style.scrollBehavior = "auto";
		window.scrollTo(0, 0);
		return { x: window.scrollX, y: window.scrollY };
	});
	invariant(documentScroll.x === 0 && documentScroll.y === 0, `${label} left the document viewport scrolled`);
	await page.waitForTimeout(250);
}

async function assertInViewport(locator: Locator, label: string): Promise<void> {
	const geometry = await locator.first().evaluate((element) => {
		const rect = element.getBoundingClientRect();
		const centerX = rect.left + rect.width / 2;
		const centerY = rect.top + rect.height / 2;
		let effectiveOpacity = 1;
		let visibility = true;
		for (let current: Element | null = element; current; current = current.parentElement) {
			const style = getComputedStyle(current);
			effectiveOpacity *= Number.parseFloat(style.opacity || "1");
			visibility &&= style.display !== "none" && style.visibility !== "hidden";
		}
		return {
			bottom: rect.bottom,
			effectiveOpacity,
			height: rect.height,
			hitTestVisible: document
				.elementsFromPoint(centerX, centerY)
				.some((candidate) => candidate === element || element.contains(candidate)),
			left: rect.left,
			right: rect.right,
			top: rect.top,
			viewportHeight: window.innerHeight,
			viewportWidth: window.innerWidth,
			visibility,
			width: rect.width,
		};
	});
	invariant(
		geometry.width > 0 &&
			geometry.height > 0 &&
			geometry.effectiveOpacity > 0.1 &&
			geometry.hitTestVisible &&
			geometry.visibility &&
			geometry.top >= 0 &&
			geometry.left >= 0 &&
			geometry.bottom <= geometry.viewportHeight &&
			geometry.right <= geometry.viewportWidth,
		`${label} is outside the captured viewport`,
	);
}

async function assertViewportIntegrity(page: Page): Promise<void> {
	const integrity = await page.evaluate(() => ({
		bodyScrollWidth: document.body.scrollWidth,
		viewportWidth: window.innerWidth,
	}));
	invariant(
		integrity.bodyScrollWidth <= integrity.viewportWidth + 1,
		`Body overflows horizontally: ${integrity.bodyScrollWidth} > ${integrity.viewportWidth}`,
	);
}

function screenshotPath(outDir: string, evidence: EvidenceCase): string {
	return join(outDir, evidence.viewport.name, `${evidence.scenario}.png`);
}

async function captureScreenshot(page: Page, path: string): Promise<void> {
	await mkdir(dirname(path), { recursive: true });
	await page.evaluate(
		() =>
			new Promise<void>((resolveFrame) => {
				requestAnimationFrame(() => requestAnimationFrame(() => resolveFrame()));
			}),
	);
	await page.screenshot({ path, fullPage: false });
}

function assertCleanPage(issues: readonly string[], label: string): void {
	invariant(issues.length === 0, `${label} emitted page issues:\n${issues.join("\n")}`);
}

async function newAcceptancePage(
	browser: Browser,
	viewport: AcceptanceViewport,
	report: DailyDecisionV2Response,
): Promise<{ readonly page: Page; readonly issues: string[]; readonly requests: readonly string[] }> {
	const page = await browser.newPage({ reducedMotion: "reduce", viewport: browserViewport(viewport) });
	const issues = createPageIssueCollector(page);
	const requests = await installApiRoutes(page, report);
	return { page, issues, requests };
}

async function captureOverviewState(
	browser: Browser,
	options: AcceptanceOptions,
	evidence: EvidenceCase,
	state: ReadinessState,
): Promise<EvidenceRecord> {
	const report = buildDecisionReport(state);
	const { page, issues, requests } = await newAcceptancePage(browser, evidence.viewport, report);
	const assertions: string[] = [];
	const path = screenshotPath(resolve(PROJECT_ROOT, options.outDir), evidence);

	try {
		await openLivePage(page, options.reactBase, "/portfolio/model", requests);
		const workspace = page.getByRole("region", { name: "Daily Decision 工作区" });
		await workspace.waitFor();
		await assertViewportIntegrity(page);
		assertions.push("live mode verified without prototype/MSW fallback", "body has no horizontal overflow");

		const expectedLabel = state === "blocked" ? "阻塞" : state === "review" ? "需复核" : "可执行";
		invariant(
			await workspace.getByText(expectedLabel, { exact: true }).first().isVisible(),
			`${state} label is missing`,
		);
		assertions.push(`${state} readiness label is visible`);

		if (state === "blocked") {
			const alert = workspace.getByRole("alert");
			invariant(
				await alert.getByText("ACCOUNT_BASELINE_MISSING", { exact: true }).isVisible(),
				"blocked reason missing",
			);
			invariant(!(await workspace.getByText("#510300", { exact: true }).isVisible()), "blocked state exposed actions");
			assertions.push("blocked reason is announced and trade suggestions stay hidden");
		} else {
			const actionTable = workspace.getByRole("region", { name: "执行建议表" });
			invariant((await actionTable.getAttribute("tabindex")) === "0", "action table is not keyboard focusable");
			const tableOverflow = await actionTable.evaluate((element) => ({
				clientWidth: element.clientWidth,
				scrollWidth: element.scrollWidth,
				overflowX: getComputedStyle(element).overflowX,
			}));
			invariant(tableOverflow.overflowX === "auto", "action table does not own horizontal overflow");
			invariant(
				tableOverflow.scrollWidth > tableOverflow.clientWidth,
				"action table fixture does not exercise overflow",
			);
			await actionTable.evaluate((element) => element.focus({ preventScroll: true }));
			invariant(
				await actionTable.evaluate((element) => document.activeElement === element),
				"action table did not focus",
			);
			assertions.push("wide action table is horizontally scrollable and keyboard focusable");
		}

		const scroller =
			evidence.viewport.name === "desktop"
				? page.locator("[data-slot='main'] > div")
				: page.locator("[data-slot='main']");
		await assertScrollable(scroller, page, `${evidence.viewport.name} Trading main`);
		assertions.push("Trading main content responds to vertical wheel scrolling");

		// Capture from a fresh navigation so focus/scroll probes cannot leave Chromium
		// compositor state in the evidence frame.
		await openLivePage(page, options.reactBase, "/portfolio/model", requests);
		await page.waitForTimeout(300);
		const captureScroller =
			evidence.viewport.name === "desktop"
				? page.locator("[data-slot='main'] > div")
				: page.locator("[data-slot='main']");
		invariant(
			(await captureScroller.evaluate((element) => element.scrollTop)) === 0,
			`${evidence.viewport.name} Trading evidence did not start at the top`,
		);
		if (evidence.viewport.name === "mobile") {
			const regionGeometry = await page.evaluate(() => {
				const main = document.querySelector("[data-slot='main']");
				const activity = document.querySelector("[data-slot='activity']");
				if (!(main instanceof HTMLElement) || !(activity instanceof HTMLElement)) return null;
				const mainRect = main.getBoundingClientRect();
				const activityRect = activity.getBoundingClientRect();
				return { activityTop: activityRect.top, mainBottom: mainRect.bottom };
			});
			invariant(regionGeometry, "mobile Trading main/activity regions are missing");
			invariant(
				regionGeometry.mainBottom <= regionGeometry.activityTop + 1,
				`mobile activity row overlaps main: ${regionGeometry.mainBottom} > ${regionGeometry.activityTop}`,
			);
			assertions.push("mobile signal queue is a separate grid row and does not overlap the scrollable main region");
		}
		await assertInViewport(page.getByText("交易总览", { exact: true }), "Trading page title");
		await assertInViewport(page.getByText("Session 数据待后端补齐", { exact: true }), "Trading session strip");
		await assertInViewport(
			page.locator("[data-slot='decision-banner']").getByText(expectedLabel, { exact: true }).first(),
			`${state} readiness label`,
		);
		assertions.push("page title, session strip, and readiness label remain in the captured viewport");
		await captureScreenshot(page, path);
		assertCleanPage(issues, `${evidence.viewport.name}/${evidence.scenario}`);
	} finally {
		await page.close();
	}

	return {
		...evidence,
		route: "/portfolio/model",
		screenshot: relative(PROJECT_ROOT, path),
		assertions,
	};
}

async function captureReviewFills(
	browser: Browser,
	options: AcceptanceOptions,
	evidence: EvidenceCase,
): Promise<EvidenceRecord> {
	const { page, issues, requests } = await newAcceptancePage(browser, evidence.viewport, buildDecisionReport("review"));
	const assertions: string[] = [];
	const path = screenshotPath(resolve(PROJECT_ROOT, options.outDir), evidence);

	try {
		await openLivePage(page, options.reactBase, "/portfolio/model", requests);
		const workspace = page.getByRole("region", { name: "Daily Decision 工作区" });
		const secondFill = workspace.getByText("fill-intent-510300-002", { exact: true });
		await secondFill.scrollIntoViewIfNeeded();
		invariant(
			await workspace.getByText("fill-intent-510300-001", { exact: true }).isVisible(),
			"first fill is missing",
		);
		invariant(await secondFill.isVisible(), "second fill is missing");
		invariant(
			await workspace.getByText("剩余 400", { exact: true }).first().isVisible(),
			"fixture remaining quantity missing",
		);
		invariant(await workspace.getByText(/净盈亏 ¥197/u).isVisible(), "PnL evidence missing");
		assertions.push(
			"two effective fills are visible for one intent",
			"remaining quantity and PnL come from the Playwright network fixture response",
		);
		await captureScreenshot(page, path);
		assertCleanPage(issues, `${evidence.viewport.name}/${evidence.scenario}`);
	} finally {
		await page.close();
	}

	return {
		...evidence,
		route: "/portfolio/model",
		screenshot: relative(PROJECT_ROOT, path),
		assertions,
	};
}

async function captureFillReview(
	browser: Browser,
	options: AcceptanceOptions,
	evidence: EvidenceCase,
): Promise<EvidenceRecord> {
	const { page, issues, requests } = await newAcceptancePage(browser, evidence.viewport, buildDecisionReport("review"));
	const assertions: string[] = [];
	const path = screenshotPath(resolve(PROJECT_ROOT, options.outDir), evidence);

	try {
		await openLivePage(page, options.reactBase, "/portfolio/review", requests);
		await page.getByRole("button", { name: /#510300/u }).click();
		const trigger = page.getByRole("button", { name: "录入手工成交" });
		await trigger.waitFor();
		await trigger.focus();
		await page.keyboard.press("Enter");

		const dialog = page.getByRole("dialog", { name: "订单确认" });
		await dialog.waitFor();
		invariant(
			await dialog.evaluate((element) => element.contains(document.activeElement)),
			"focus did not enter fill dialog",
		);
		invariant(
			await dialog.getByText("RISK_WARNING", { exact: true }).isVisible(),
			"review reason missing from fill dialog",
		);
		invariant(await dialog.getByText("已成交 600", { exact: true }).isVisible(), "filled quantity missing from dialog");
		invariant(
			await dialog.getByText("剩余 400", { exact: true }).isVisible(),
			"remaining quantity missing from dialog",
		);

		await dialog.getByLabel("成交价格").fill("4.32");
		await dialog.getByRole("button", { name: "提交手工成交" }).click();
		invariant(
			await dialog.getByRole("alert").getByText("请先确认已复核后端返回的原因", { exact: true }).isVisible(),
			"review confirmation gate did not block submission",
		);
		const scrollMetrics = await dialog.evaluate((element) => ({
			clientHeight: element.clientHeight,
			scrollHeight: element.scrollHeight,
			overflowY: getComputedStyle(element).overflowY,
		}));
		invariant(scrollMetrics.overflowY === "auto", "fill dialog does not own vertical scrolling");
		if (scrollMetrics.scrollHeight > scrollMetrics.clientHeight) {
			await dialog.hover({ position: { x: 100, y: Math.max(100, scrollMetrics.clientHeight - 100) } });
			await page.mouse.wheel(0, scrollMetrics.scrollHeight);
			await page.waitForTimeout(100);
			invariant((await dialog.evaluate((element) => element.scrollTop)) > 0, "fill dialog did not scroll");
		}
		const submitVisible = await dialog.getByRole("button", { name: "提交手工成交" }).evaluate((element) => {
			const rect = element.getBoundingClientRect();
			return rect.top >= 0 && rect.bottom <= window.innerHeight;
		});
		invariant(submitVisible, "fill submit button is outside the viewport after scrolling");
		assertions.push(
			"keyboard focus enters the dialog",
			"review reason, filled quantity, and remaining quantity are visible",
			"submission is gated until review confirmation",
			"the submit action stays reachable and overflow states scroll when needed",
		);
		const resetDialogTop = await dialog.evaluate((element) => {
			element.style.scrollBehavior = "auto";
			element.style.overflowAnchor = "none";
			element.scrollTop = 0;
			return element.scrollTop;
		});
		invariant(resetDialogTop === 0, "fill dialog did not reset before evidence capture");
		await assertInViewport(dialog.getByText("订单确认", { exact: true }), "fill dialog title");
		await assertInViewport(dialog.getByText("intent-510300", { exact: true }), "fill dialog intent context");
		await assertInViewport(dialog.getByText("#510300", { exact: true }), "fill dialog instrument context");
		assertions.push("captured dialog starts with its title, intent, and instrument context");
		await captureScreenshot(page, path);

		await page.keyboard.press("Escape");
		await dialog.waitFor({ state: "detached" });
		const triggerHandle = await trigger.elementHandle();
		invariant(triggerHandle, "fill trigger detached before focus restoration");
		await page.waitForFunction((element) => document.activeElement === element, triggerHandle, { timeout: 1_000 });
		assertions.push("Escape closes the dialog and restores trigger focus");
		assertCleanPage(issues, `${evidence.viewport.name}/${evidence.scenario}`);
	} finally {
		await page.close();
	}

	return {
		...evidence,
		route: "/portfolio/review",
		screenshot: relative(PROJECT_ROOT, path),
		assertions,
	};
}

async function captureMultiFillLedger(
	browser: Browser,
	options: AcceptanceOptions,
	evidence: EvidenceCase,
): Promise<EvidenceRecord> {
	const { page, issues, requests } = await newAcceptancePage(browser, evidence.viewport, buildDecisionReport("review"));
	const assertions: string[] = [];
	const path = screenshotPath(resolve(PROJECT_ROOT, options.outDir), evidence);

	try {
		await openLivePage(page, options.reactBase, "/portfolio/transactions", requests);
		await page.getByText("fill-intent-510300-002", { exact: true }).waitFor();
		invariant(await page.getByText("fill-intent-510300-001", { exact: true }).isVisible(), "first ledger fill missing");
		invariant(
			await page
				.getByText(/分批 2 笔/u)
				.first()
				.isVisible(),
			"split-fill label missing",
		);
		const ledger = page.getByRole("list", { name: "手工成交记录" });
		invariant((await ledger.getAttribute("tabindex")) === "0", "fill ledger is not keyboard focusable");
		await ledger.focus();
		invariant(
			await ledger.evaluate((element) => document.activeElement === element),
			"fill ledger did not receive focus",
		);
		assertions.push("two fills for one intent are visible", "fill ledger is keyboard focusable");
		await assertViewportIntegrity(page);
		await captureScreenshot(page, path);
		assertCleanPage(issues, `${evidence.viewport.name}/${evidence.scenario}`);
	} finally {
		await page.close();
	}

	return {
		...evidence,
		route: "/portfolio/transactions",
		screenshot: relative(PROJECT_ROOT, path),
		assertions,
	};
}

async function captureFillCorrection(
	browser: Browser,
	options: AcceptanceOptions,
	evidence: EvidenceCase,
): Promise<EvidenceRecord> {
	const { page, issues, requests } = await newAcceptancePage(browser, evidence.viewport, buildDecisionReport("review"));
	const assertions: string[] = [];
	const path = screenshotPath(resolve(PROJECT_ROOT, options.outDir), evidence);
	const originalFillId = "fill-intent-510300-001";

	try {
		await openLivePage(page, options.reactBase, "/portfolio/transactions", requests);
		const trigger = page.getByRole("button", { name: `替换成交 ${originalFillId}` });
		await trigger.click();
		const dialog = page.getByRole("dialog", { name: "替换成交" });
		await dialog.waitFor();
		invariant(await dialog.getByRole("region", { name: "不可变原始成交证据" }).isVisible(), "raw evidence missing");
		invariant((await dialog.getByLabel("替换成交数量").inputValue()) === "250", "replacement quantity not prefilled");
		invariant((await dialog.getByLabel("替换成交价格").inputValue()) === "4.31", "replacement price not prefilled");
		await dialog.getByLabel("替换成交数量").fill("200");
		await dialog.getByLabel("更正原因").fill("券商回单确认数量为 200 股");
		await assertViewportIntegrity(page);
		const correctionScrollTop = await dialog.evaluate((element) => {
			element.style.scrollBehavior = "auto";
			element.style.overflowAnchor = "none";
			element.scrollTop = 0;
			return element.scrollTop;
		});
		invariant(correctionScrollTop === 0, "correction Sheet did not reset before capture");
		await assertInViewport(dialog.getByRole("heading", { name: "替换成交" }), "correction Sheet title");
		await captureScreenshot(page, path);
		assertions.push(
			"live mode uses Playwright API fixtures without MSW or prototype fallback",
			"correction Sheet keeps immutable raw evidence visible",
			"replacement fields are prefilled and remain usable on this viewport",
			"captured Sheet starts at its title and immutable evidence",
		);

		const correctionRequest = page.waitForRequest(
			(request) => request.method() === "POST" && request.url().endsWith(`/${originalFillId}/replace`),
		);
		await dialog.getByRole("button", { name: "确认追加替换" }).click();
		const request = await correctionRequest;
		const payload = request.postDataJSON() as ReplaceFillRequest;
		invariant(payload.adjustment_id.startsWith(`adjustment-replace-${originalFillId}-`), "adjustment id is unstable");
		invariant(payload.replacement_fill_id.startsWith(`fill-${originalFillId}-replacement-`), "replacement id is unstable");
		invariant(payload.quantity === 200, "replacement quantity payload mismatch");

		await page.getByRole("status", { name: "成交更正结果" }).waitFor();
		const originalRow = page.getByRole("listitem", { name: `成交 ${originalFillId}` });
		const replacementRow = page.getByRole("listitem", { name: `成交 ${payload.replacement_fill_id}` });
		await replacementRow.scrollIntoViewIfNeeded();
		invariant(await originalRow.getByText("已替换", { exact: true }).isVisible(), "original fill state not replaced");
		invariant(await originalRow.getByText(payload.replacement_fill_id, { exact: true }).isVisible(), "replacement link missing");
		invariant(await replacementRow.getByText("有效", { exact: true }).isVisible(), "replacement fill not effective");
		invariant((await originalRow.getByRole("button").count()) === 0, "original fill still exposes correction actions");
		assertions.push(
			"generated idempotency keys and replacement payload are posted",
			"fixture refetch keeps the raw original visible as replaced and links the effective replacement",
			"this evidence does not assert live backend persistence",
		);
		assertCleanPage(issues, `${evidence.viewport.name}/${evidence.scenario}`);
	} finally {
		await page.close();
	}

	return {
		...evidence,
		route: "/portfolio/transactions",
		screenshot: relative(PROJECT_ROOT, path),
		assertions,
	};
}

async function runEvidenceCase(
	browser: Browser,
	options: AcceptanceOptions,
	evidence: EvidenceCase,
): Promise<EvidenceRecord> {
	if (evidence.scenario === "review-fills") return captureReviewFills(browser, options, evidence);
	if (evidence.scenario === "fill-review") return captureFillReview(browser, options, evidence);
	if (evidence.scenario === "multi-fill-ledger") return captureMultiFillLedger(browser, options, evidence);
	if (evidence.scenario === "fill-correction") return captureFillCorrection(browser, options, evidence);
	return captureOverviewState(browser, options, evidence, evidence.scenario);
}

function renderReport(records: readonly EvidenceRecord[], capturedAt: string): string {
	const lines = [
		"# R1 Trading Frontend Fixture Visual Acceptance",
		"",
		`- Captured: ${capturedAt}`,
		`- Runtime: \`${ACCEPTANCE_SCOPE.runtime}\` verified in the browser`,
		`- API data: ${ACCEPTANCE_SCOPE.apiData}`,
		`- Evidence scope: ${ACCEPTANCE_SCOPE.proves}`,
		`- Does not prove: ${ACCEPTANCE_SCOPE.doesNotProve}`,
		`- Strategy: \`${STRATEGY_ID}\``,
		`- Account: \`${ACCOUNT_ID}\``,
		"",
	];

	for (const viewport of ACCEPTANCE_VIEWPORTS) {
		lines.push(`## ${viewport.name} (${viewport.width}x${viewport.height})`, "");
		for (const record of records.filter((item) => item.viewport.name === viewport.name)) {
			const imagePath = `${viewport.name}/${record.scenario}.png`;
			lines.push(`### ${record.scenario}`, "", `![${record.scenario}](${imagePath})`, "");
			for (const assertion of record.assertions) lines.push(`- ${assertion}`);
			lines.push("");
		}
	}

	return `${lines.join("\n")}\n`;
}

async function main(args: readonly string[]): Promise<void> {
	const options = parseAcceptanceArgs(args);
	const outDir = resolve(PROJECT_ROOT, options.outDir);
	await mkdir(outDir, { recursive: true });
	const browser = await chromium.launch({ channel: "chromium" });
	const records: EvidenceRecord[] = [];

	try {
		for (const evidence of buildEvidenceCases()) {
			const record = await runEvidenceCase(browser, options, evidence);
			records.push(record);
			console.log(`Captured ${evidence.viewport.name}/${evidence.scenario}: ${record.screenshot}`);
		}
	} finally {
		await browser.close();
	}

	const capturedAt = new Date().toISOString();
	await writeFile(
		join(outDir, "evidence.json"),
		`${JSON.stringify({ capturedAt, scope: ACCEPTANCE_SCOPE, options, records }, null, 2)}\n`,
		"utf8",
	);
	await writeFile(join(outDir, "report.md"), renderReport(records, capturedAt), "utf8");
	console.log(
		`R1 Trading frontend acceptance passed with ${records.length} screenshots in ${relative(PROJECT_ROOT, outDir)}`,
	);
}

if (import.meta.main) {
	main(process.argv.slice(2)).catch((error: unknown) => {
		console.error(error instanceof Error ? error.message : error);
		process.exit(1);
	});
}
