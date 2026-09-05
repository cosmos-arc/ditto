import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { chromium } from "playwright";

type RouteResult = {
	readonly console_errors: readonly string[];
	readonly acceptance_errors: readonly string[];
	readonly failed_requests: readonly string[];
	readonly market_context: Record<string, unknown> | null;
	readonly page_errors: readonly string[];
	readonly path: string;
	readonly screenshot: string;
	readonly visible_assertions: Record<string, boolean>;
};

const baseUrl = process.env["DITTO_APP_BASE_URL"] ?? "http://127.0.0.1:5174";
const output = resolve(process.argv[2] ?? "/tmp/ditto-q2-ui-live-20260901.json");
const screenshotRoot = resolve(process.argv[3] ?? "/tmp/ditto-q2-ui-live-20260901");
const routes = [
	{
		path: "/markets",
		expected: ["Risk On", "Degraded", "global_index_return_1d", "Downstream impact chain"],
	},
	{
		path: "/",
		expected: ["市场脉搏", "DAILY BRIEF", "风险偏好", "MarketContext EvidenceBrief"],
	},
] as const;

await mkdir(dirname(output), { recursive: true });
await mkdir(screenshotRoot, { recursive: true });
const browser = await chromium.launch({ headless: true });
const results: RouteResult[] = [];

try {
	for (const route of routes) {
		const context = await browser.newContext({ viewport: { height: 960, width: 1440 } });
		const page = await context.newPage();
		const consoleErrors: string[] = [];
		const acceptanceErrors: string[] = [];
		const pageErrors: string[] = [];
		const failedRequests: string[] = [];
		let marketContext: Record<string, unknown> | null = null;
		page.on("console", (message) => {
			if (message.type() === "error") {
				const location = message.location().url;
				consoleErrors.push(location ? `${message.text()} (${location})` : message.text());
			}
		});
		page.on("pageerror", (error) => pageErrors.push(error.message));
		page.on("requestfailed", (request) => {
			if (request.url().includes("/api/")) {
				failedRequests.push(`${request.method()} ${request.url()} ${request.failure()?.errorText ?? "failed"}`);
			}
		});
		page.on("response", async (response) => {
			if (!response.ok() && response.url().includes("/api/")) {
				failedRequests.push(`${response.request().method()} ${response.url()} HTTP ${response.status()}`);
			}
			if (response.url().includes("/api/v1/market/context")) {
				if (response.ok()) {
					const decoded = (await response.json()) as { readonly data?: Record<string, unknown> };
					marketContext = decoded.data ?? null;
				}
			}
		});

		await page.goto(`${baseUrl}${route.path}`, { waitUntil: "domcontentloaded" });
		try {
			await page.waitForFunction(
				(expected) => expected.every((text) => document.body.innerText.includes(text)),
				route.expected,
				{ timeout: 20_000 },
			);
		} catch (error) {
			acceptanceErrors.push(error instanceof Error ? error.message : String(error));
		}
		const body = await page.locator("body").innerText();
		const screenshot = resolve(screenshotRoot, route.path === "/" ? "today.png" : "markets.png");
		await page.screenshot({ fullPage: true, path: screenshot });
		const visibleAssertions = Object.fromEntries(route.expected.map((text) => [text, body.includes(text)]));
		visibleAssertions["no_market_context_blocked"] =
			!body.includes("MarketContext blocked") && !body.includes("MarketContext 不可用");
		results.push({
			acceptance_errors: acceptanceErrors,
			console_errors: consoleErrors,
			failed_requests: failedRequests,
			market_context: marketContext,
			page_errors: pageErrors,
			path: route.path,
			screenshot,
			visible_assertions: visibleAssertions,
		});
		await context.close();
	}
} finally {
	await browser.close();
}

const passed = results.every((result) => {
	const snapshots = result.market_context?.["source_snapshot_ids"];
	return (
		result.acceptance_errors.length === 0 &&
		result.console_errors.length === 0 &&
		result.page_errors.length === 0 &&
		result.failed_requests.length === 0 &&
		Object.values(result.visible_assertions).every(Boolean) &&
		result.market_context?.["status"] === "degraded" &&
		result.market_context?.["regime_label"] === "risk_on" &&
		Array.isArray(snapshots) &&
		snapshots.some((value) => String(value).includes("global_index_daily"))
	);
});
const artifact = {
	backend: "http://127.0.0.1:8000",
	base_url: baseUrl,
	generated_at: new Date().toISOString(),
	mode: "live-backend-no-msw",
	passed,
	routes: results,
	schema: "ditto.q2-live-ui.v1",
};
await writeFile(output, `${JSON.stringify(artifact, null, 2)}\n`, "utf8");
process.stdout.write(`${JSON.stringify({ output, passed })}\n`);
if (!passed) process.exitCode = 1;
