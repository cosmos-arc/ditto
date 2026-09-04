import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { chromium, type Page } from "playwright";

type JsonObject = Record<string, unknown>;

type RouteResult = {
	readonly acceptance_errors: readonly string[];
	readonly api_evidence: Record<string, JsonObject>;
	readonly console_errors: readonly string[];
	readonly failed_requests: readonly string[];
	readonly page_errors: readonly string[];
	readonly path: string;
	readonly screenshot: string;
	readonly visible_assertions: Record<string, boolean>;
};

const baseUrl = process.env.DITTO_APP_BASE_URL ?? "http://127.0.0.1:5174";
const output = resolve(process.argv[2] ?? "/tmp/ditto-q3-ui-live-20260901.json");
const screenshotRoot = resolve(process.argv[3] ?? "/tmp/ditto-q3-ui-live-20260901");
const rotationId =
	"industry-rotation:sha256:29b60dbb4bdf590a42f1388017c7a9ac860fb6577108fec0614bb29c1b0f8b53";
const selectionRunId =
	"selection-run:sha256:1f0f894e61431ce5b18d02f1cbab75cf3066b361f704d0745c0d6099347507f8";
const technicalSnapshotId =
	"snapshot:tushare:stock_daily:sha256:3afa1a31fa56daffd46e29d04e9a99f80614921772ccebfe5b59296aa1ef48c2";

function observe(page: Page) {
	const consoleErrors: string[] = [];
	const pageErrors: string[] = [];
	const failedRequests: string[] = [];
	const apiEvidence: Record<string, JsonObject> = {};
	page.on("console", (message) => {
		if (message.type() === "error") {
			const location = message.location().url;
			consoleErrors.push(location ? `${message.text()} (${location})` : message.text());
		}
	});
	page.on("pageerror", (error) => pageErrors.push(error.message));
	page.on("requestfailed", (request) => {
		if (new URL(request.url()).pathname.startsWith("/api/")) {
			failedRequests.push(`${request.method()} ${request.url()} ${request.failure()?.errorText ?? "failed"}`);
		}
	});
	page.on("response", async (response) => {
		if (!new URL(response.url()).pathname.startsWith("/api/")) return;
		if (!response.ok()) {
			failedRequests.push(`${response.request().method()} ${response.url()} HTTP ${response.status()}`);
			return;
		}
		const path = new URL(response.url()).pathname;
		if (
			path.includes("/selections/industry-rotations/") ||
			path.includes("/selections/runs") ||
			path.includes("/data-products/") ||
			path.includes("/technical-analysis/snapshots/query")
		) {
			const decoded = (await response.json()) as JsonObject;
			const rawRequestBody = response.request().postData();
			const requestBody = rawRequestBody ? (JSON.parse(rawRequestBody) as JsonObject) : null;
			apiEvidence[`${response.request().method()} ${path}`] = requestBody
				? { request: requestBody, response: decoded }
				: decoded;
		}
	});
	return {
		api_evidence: apiEvidence,
		console_errors: consoleErrors,
		failed_requests: failedRequests,
		page_errors: pageErrors,
	};
}

async function waitForText(page: Page, expected: readonly string[], acceptanceErrors: string[]): Promise<string> {
	try {
		await page.waitForFunction(
			(values) => values.every((text) => document.body.innerText.includes(text)),
			expected,
			{ timeout: 30_000 },
		);
	} catch (error) {
		acceptanceErrors.push(error instanceof Error ? error.message : String(error));
	}
	return page.locator("body").innerText();
}

await mkdir(dirname(output), { recursive: true });
await mkdir(screenshotRoot, { recursive: true });
const browser = await chromium.launch({ headless: true });
const results: RouteResult[] = [];

try {
	{
		const context = await browser.newContext({ viewport: { height: 960, width: 1440 } });
		const page = await context.newPage();
		const observed = observe(page);
		const acceptanceErrors: string[] = [];
		const path = `/markets/industries?snapshotId=${encodeURIComponent(rotationId)}`;
		await page.goto(`${baseUrl}${path}`, { waitUntil: "domcontentloaded" });
		const expected = ["INDUSTRY ROTATION", "行业排名", "DEGRADED", "石油石化", "MISSING INPUTS"];
		const body = await waitForText(page, expected, acceptanceErrors);
		const screenshot = resolve(screenshotRoot, "industries.png");
		await page.screenshot({ fullPage: true, path: screenshot });
		results.push({
			...observed,
			acceptance_errors: acceptanceErrors,
			path,
			screenshot,
			visible_assertions: Object.fromEntries(expected.map((text) => [text, body.includes(text)])),
		});
		await context.close();
	}

	{
		const context = await browser.newContext({ viewport: { height: 960, width: 1440 } });
		const page = await context.newPage();
		const observed = observe(page);
		const acceptanceErrors: string[] = [];
		const path = "/markets/screener";
		await page.goto(`${baseUrl}${path}`, { waitUntil: "domcontentloaded" });
		await page.getByLabel("SelectionSpec ID").fill("a-share-stock-discovery");
		const expected = ["20 in / 236 out", "入选 20", "排除 236"];
		await waitForText(page, expected, acceptanceErrors);
		await page.getByRole("tab", { name: "排除 236" }).click();
		const exclusionExpected = ["贵州茅台", "below_top_k", "RANKING"];
		const body = await waitForText(page, exclusionExpected, acceptanceErrors);
		await page.getByText("贵州茅台", { exact: true }).scrollIntoViewIfNeeded();
		const screenshot = resolve(screenshotRoot, "selection.png");
		await page.screenshot({ fullPage: true, path: screenshot });
		const visibleAssertions = Object.fromEntries([...expected, ...exclusionExpected].map((text) => [text, body.includes(text)]));
		visibleAssertions.selection_run_identity = body.includes(selectionRunId.split(":").at(-1)?.slice(0, 12) ?? "");
		results.push({
			...observed,
			acceptance_errors: acceptanceErrors,
			path,
			screenshot,
			visible_assertions: visibleAssertions,
		});
		await context.close();
	}

	{
		const context = await browser.newContext({ viewport: { height: 960, width: 1440 } });
		const page = await context.newPage();
		const observed = observe(page);
		const acceptanceErrors: string[] = [];
		const path = `/instruments/1003251?tab=technical&selectionRunId=${encodeURIComponent(selectionRunId)}`;
		await page.goto(`${baseUrl}${path}`, { waitUntil: "domcontentloaded" });
		const expected = [
			"技术证据快照",
			"DEGRADED",
			"READINGS",
			"36",
			"日线结构",
			"周线结构",
			"below_top_k",
			"missing_reference_series",
		];
		const body = await waitForText(page, expected, acceptanceErrors);
		const screenshot = resolve(screenshotRoot, "technical.png");
		await page.screenshot({ fullPage: true, path: screenshot });
		const technicalCall = Object.entries(observed.api_evidence).find(([key]) =>
			key.includes("/technical-analysis/snapshots/query"),
		)?.[1];
		const request = technicalCall?.request as JsonObject | undefined;
		const sourceSnapshotIds = request?.source_snapshot_ids;
		const visibleAssertions = Object.fromEntries(expected.map((text) => [text, body.includes(text)]));
		visibleAssertions.exact_selection_run = request?.selection_run_id === selectionRunId;
		visibleAssertions.exact_certified_history_snapshot =
			Array.isArray(sourceSnapshotIds) && sourceSnapshotIds.length === 1 && sourceSnapshotIds[0] === technicalSnapshotId;
		results.push({
			...observed,
			acceptance_errors: acceptanceErrors,
			path,
			screenshot,
			visible_assertions: visibleAssertions,
		});
		await context.close();
	}
} finally {
	await browser.close();
}

const passed = results.every(
	(result) =>
		result.acceptance_errors.length === 0 &&
		result.console_errors.length === 0 &&
		result.page_errors.length === 0 &&
		result.failed_requests.length === 0 &&
		Object.values(result.visible_assertions).every(Boolean),
);
const artifact = {
	backend: "http://127.0.0.1:8000",
	base_url: baseUrl,
	generated_at: new Date().toISOString(),
	mode: "live-backend-no-msw",
	passed,
	routes: results,
	schema: "ditto.q3-live-ui.v1",
};
await Bun.write(output, `${JSON.stringify(artifact, null, 2)}\n`);
process.stdout.write(`${JSON.stringify({ output, passed })}\n`);
if (!passed) process.exitCode = 1;
