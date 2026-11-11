import { expect, type Page, test } from "@playwright/test";

function requiredEnvironment(name: string): string {
	const value = process.env[name]?.trim();
	if (!value) throw new Error(`${name} is required`);
	return value;
}

const webOrigin = requiredEnvironment("DITTO_SYSTEM_WEB_ORIGIN");
const apiOrigin = requiredEnvironment("DITTO_SYSTEM_API_ORIGIN");

// 与 tests/system/fixtures/market_workspace_app.py 保持同一身份。
const STOCK_ID = 4_000_001;
const STOCK_NAME = "盘后样本股";
const ETF_ID = 4_100_001;
const ETF_NAME = "盘后样本ETF";
const DELISTED_ID = 4_000_002;
const DELISTED_NAME = "盘后退市样本";
const WATCHLIST_STORAGE_KEY = "ditto.market-watchlist.v1";
const API_HEADERS = { "X-Ditto-API-Contract-Version": "v1" };

interface ChartBar {
	readonly close: number;
	readonly trade_date: string;
}

interface QuoteExpectation {
	readonly changeText: string;
	readonly closeText: string;
	readonly tradeDate: string;
}

function signed(value: number, digits = 2): string {
	const sign = value > 0 ? "+" : value < 0 ? "−" : "";
	return `${sign}${Math.abs(value).toFixed(digits)}`;
}

function daysBefore(date: string, days: number): string {
	const parsed = new Date(`${date}T00:00:00Z`);
	parsed.setUTCDate(parsed.getUTCDate() - days);
	return parsed.toISOString().slice(0, 10);
}

async function fetchCalendarAnchor(page: Page): Promise<string> {
	const response = await page.request.get(`${apiOrigin}/api/v1/ingestion/status`, { headers: API_HEADERS });
	expect(response.status()).toBe(200);
	const payload = (await response.json()).data as {
		datasets: Array<{ dataset: string; latest_date: string | null; latest_status: string | null }>;
	};
	const calendar = payload.datasets.find((dataset) => dataset.dataset === "calendar");
	expect(calendar?.latest_status).toBe("success");
	expect(calendar?.latest_date).toBeTruthy();
	return calendar?.latest_date ?? "";
}

async function fetchQuoteExpectation(page: Page, instrumentId: number, anchor: string): Promise<QuoteExpectation> {
	const response = await page.request.post(`${apiOrigin}/api/v1/market/chart`, {
		headers: API_HEADERS,
		data: {
			instrument_id: instrumentId,
			start_date: daysBefore(anchor, 45),
			end_date: anchor,
			period: "daily",
			adjustment: "none",
		},
	});
	expect(response.status()).toBe(200);
	const bars = ((await response.json()).data as { bars: ChartBar[] }).bars;
	const last = bars.at(-1);
	const previous = bars.at(-2);
	expect(last).toBeTruthy();
	const close = last?.close ?? Number.NaN;
	const change = last && previous ? close - previous.close : Number.NaN;
	const changePercent = last && previous && previous.close ? (change / previous.close) * 100 : Number.NaN;
	return {
		changeText: `${signed(change)} (${signed(changePercent)}%)`,
		closeText: close.toFixed(2),
		tradeDate: last?.trade_date ?? "",
	};
}

function captureBrowserErrors(page: Page): string[] {
	const errors: string[] = [];
	page.on("pageerror", (error) => errors.push(error.message));
	page.on("console", (message) => {
		if (message.type() === "error") errors.push(message.text());
	});
	return errors;
}

async function rowQuote(page: Page, name: string): Promise<ReturnType<Page["locator"]>> {
	const row = page.locator('[data-info-unit="watchlist-row"]', { hasText: name });
	await expect(row).toBeVisible();
	return row.locator('[data-quote-field="close"]');
}

test.describe.serial("post-market observation to anchored instrument workspace over a seeded production API", () => {
	test("markets landing shows the most recent complete trading day from real ingestion results", async ({ page }) => {
		const browserErrors = captureBrowserErrors(page);
		const anchor = await fetchCalendarAnchor(page);
		await page.goto(`${webOrigin}/markets`);
		const anchorItem = page.locator('[data-info-unit="market-observation-anchor"]');
		await expect(anchorItem).toContainText("最近完整交易日");
		await expect(anchorItem).toContainText(anchor);
		// 本 fixture 未播种市场上下文证据：上下文面板如实失败并提供重试，
		// 但盘后锚点、标的目录等仍可用任务不被封死（部分缺失不伪装完整）。
		const contextError = page.locator('[data-info-unit="market-context-error"]');
		await expect(contextError).toBeVisible();
		await expect(contextError.getByRole("button", { name: "重试市场上下文" })).toBeVisible();
		await expect(page.getByText(/个标的/).first()).toBeVisible();
		// 唯一允许的控制台错误是市场上下文的 422（真实缺失，非静默假成功）。
		const unexpected = browserErrors.filter((line) => !line.includes("status of 422"));
		expect(unexpected).toEqual([]);
	});

	test("watchlist shows real post-market quotes; entering the chart keeps object and observation date", async ({
		page,
	}) => {
		const browserErrors = captureBrowserErrors(page);
		const anchor = await fetchCalendarAnchor(page);
		const stockQuote = await fetchQuoteExpectation(page, STOCK_ID, anchor);

		// 真实操作加入自选（名称检索 → 保存），不用 API 代替用户动作。
		await page.goto(`${webOrigin}/markets/watchlist`);
		await page.getByRole("button", { name: "添加标的" }).click();
		await page.getByLabel("搜索代码或名称").fill("盘后样本");
		await page.getByRole("button", { name: "检索" }).click();
		await expect(page.getByRole("button", { name: `加入自选 ${STOCK_NAME}` })).toBeVisible();
		await page.getByRole("button", { name: `加入自选 ${STOCK_NAME}` }).click();
		await page.getByRole("button", { name: "添加标的" }).click();
		await page.getByLabel("搜索代码或名称").fill("盘后样本");
		await page.getByRole("button", { name: "检索" }).click();
		await page.getByRole("button", { name: `加入自选 ${ETF_NAME}` }).click();

		// 摘要锚点与行情列都来自真实结果；数字与直接 API 同值。
		const anchorCell = page.getByTestId("watchlist-anchor");
		await expect(anchorCell).toContainText(anchor);
		const stockRow = page.locator('[data-info-unit="watchlist-row"]', { hasText: STOCK_NAME });
		await expect(stockRow.locator('[data-quote-field="close"]')).toHaveText(stockQuote.closeText);
		await expect(stockRow.locator('[data-quote-field="change"]')).toHaveText(stockQuote.changeText);
		await expect(stockRow.locator('[data-quote-field="date"]')).toHaveText(`行情日 ${stockQuote.tradeDate}`);

		// 从自选进入标的工作面：对象与观察日随链接携带（表→图同一交易日）。
		const chartHref = `/instruments/${STOCK_ID}?tab=chart&observeDate=${stockQuote.tradeDate}`;
		await expect(page.getByRole("link", { name: STOCK_NAME })).toHaveAttribute("href", chartHref);
		await page.getByRole("link", { name: STOCK_NAME }).click();
		await expect(page).toHaveURL(new RegExp(`/instruments/${STOCK_ID}\\?tab=chart&observeDate=${stockQuote.tradeDate}`));

		// 表图协同：图表截至日期锚定观察日，Primary Answer 与自选行情列同收盘。
		const anchorChip = page.getByTestId(`observe-anchor-${STOCK_ID}`);
		await expect(anchorChip).toHaveAttribute("data-state", "observe-anchor");
		await expect(anchorChip).toContainText(stockQuote.tradeDate);
		await expect(page.getByLabel("截至日期")).toHaveValue(stockQuote.tradeDate);
		const answer = page.locator("[data-primary-answer]");
		await expect(answer.locator("[data-answer-metric]").first()).toHaveText(stockQuote.closeText);
		await expect(answer.locator("[data-answer-scope]")).toContainText(`${stockQuote.tradeDate} 收盘`);

		// 键盘：图表宿主可聚焦，+/- 键缩放改变可见区间（真实交互，非截图代验）。
		const host = page.locator(`[data-chart-interaction-contract="instrument-candles-${STOCK_ID}"]`);
		await host.focus();
		const rangeBefore = await host.getAttribute("data-chart-visible-range");
		await page.keyboard.press("+");
		await page.keyboard.press("+");
		await expect
			.poll(async () => host.getAttribute("data-chart-visible-range"))
			.not.toBe(rangeBefore);

		// 周/月图表与复权能力继续复用：周期切换真实重新取数。
		await page.getByRole("button", { name: "周" }).click();
		await expect(host).toHaveAttribute("aria-label", /周K 线/);
		await page.getByRole("button", { name: "日" }).click();
		await expect(host).toHaveAttribute("aria-label", /日K 线/);

		// 返回原观察上下文：清单对象集合与行情列恢复。
		await page.goBack();
		await expect(page).toHaveURL(/\/markets\/watchlist/);
		await expect(page.getByRole("link", { name: STOCK_NAME })).toBeVisible();
		await expect(await rowQuote(page, STOCK_NAME)).toHaveText(stockQuote.closeText);
		const stored = await page.evaluate((key: string) => window.localStorage.getItem(key), WATCHLIST_STORAGE_KEY);
		expect(JSON.parse(stored ?? "[]")).toContain(STOCK_ID);
		expect(browserErrors).toEqual([]);
	});

	test("ETF leg reuses NAV evidence with its own dates and returns to the watchlist", async ({ page }) => {
		const browserErrors = captureBrowserErrors(page);
		const anchor = await fetchCalendarAnchor(page);
		const etfQuote = await fetchQuoteExpectation(page, ETF_ID, anchor);

		await page.goto(`${webOrigin}/markets/watchlist`);
		await page.getByRole("button", { name: "添加标的" }).click();
		await page.getByLabel("搜索代码或名称").fill("盘后样本");
		await page.getByRole("button", { name: "检索" }).click();
		await page.getByRole("button", { name: `加入自选 ${ETF_NAME}` }).click();

		const etfRow = page.locator('[data-info-unit="watchlist-row"]', { hasText: ETF_NAME });
		await expect(etfRow.locator('[data-quote-field="close"]')).toHaveText(etfQuote.closeText);
		await expect(etfRow.locator('[data-quote-field="date"]')).toHaveText(`行情日 ${etfQuote.tradeDate}`);

		await page.getByRole("link", { name: ETF_NAME }).click();
		await expect(page).toHaveURL(new RegExp(`/instruments/${ETF_ID}\\?tab=chart&observeDate=${etfQuote.tradeDate}`));
		// 价格与净值各自日期：本地净值库覆盖锚点日，净值叠加可用（非不可得降级）。
		await page.getByTestId("indicator-toggle-nav").check();
		await expect(page.locator('[data-state="nav-unavailable"]')).toHaveCount(0);
		const answer = page.locator("[data-primary-answer]");
		await expect(answer.locator("[data-answer-metric]").first()).toHaveText(etfQuote.closeText);

		await page.goBack();
		await expect(page).toHaveURL(/\/markets\/watchlist/);
		await expect(page.getByRole("link", { name: ETF_NAME })).toBeVisible();
		expect(browserErrors).toEqual([]);
	});

	test("delisted watchlist object stays visible with explicit delisted and unavailable quote states", async ({
		page,
	}) => {
		await page.addInitScript(
			(ids: string) => {
				window.localStorage.setItem("ditto.market-watchlist.v1", ids);
			},
			JSON.stringify([DELISTED_ID]),
		);
		await page.goto(`${webOrigin}/markets/watchlist`);
		const delistedRow = page.locator('[data-info-unit="watchlist-row"][data-row-state="delisted"]');
		await expect(delistedRow).toBeVisible();
		await expect(delistedRow).toContainText(DELISTED_NAME);
		await expect(delistedRow.getByText("已退出")).toBeVisible();
		// 本地行情库无该对象可见日 K：行情不可得明确标注，不伪造价格；
		// 进入工作面仍可用（不带观察日锚点）。
		await expect(delistedRow.locator('[data-quote-state="unavailable"]')).toBeVisible();
		await expect(page.getByRole("link", { name: DELISTED_NAME })).toHaveAttribute(
			"href",
			`/instruments/${DELISTED_ID}`,
		);
	});
});
