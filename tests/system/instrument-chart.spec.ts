import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";
import { readFile } from "node:fs/promises";

function requiredEnvironment(name: string): string {
	const value = process.env[name]?.trim();
	if (!value) throw new Error(`${name} is required`);
	return value;
}

const webOrigin = requiredEnvironment("DITTO_SYSTEM_WEB_ORIGIN");
const apiOrigin = requiredEnvironment("DITTO_SYSTEM_API_ORIGIN");

const ETF_ID = 2000001;
const ETF_NO_NAV_ID = 2000002;
const STOCK_ID = 1000001;

function captureBrowserErrors(page: Page): string[] {
	const errors: string[] = [];
	page.on("pageerror", (error) => errors.push(error.message));
	page.on("console", (message) => {
		if (message.type() === "error") errors.push(message.text());
	});
	return errors;
}

async function expectNoSeriousAccessibilityViolations(page: Page): Promise<void> {
	const accessibility = await new AxeBuilder({ page }).analyze();
	const serious = accessibility.violations.filter((violation) =>
		["critical", "serious"].includes(violation.impact ?? ""),
	);
	expect(serious).toEqual([]);
}

test.describe
	.serial("instrument chart candles over a seeded production API", () => {
		test("renders ETF candles, gap annotation and primary answer with zero console errors", async ({
			page,
		}) => {
			const browserErrors = captureBrowserErrors(page);
			await page.goto(`${webOrigin}/instruments/${ETF_ID}?tab=chart`);

			const host = page.locator(`[data-chart-interaction-contract="instrument-candles-${ETF_ID}"]`);
			await expect(host).toBeVisible();
			await expect(host.locator("canvas").first()).toBeVisible();

			// Primary Answer：最新收盘 + 涨跌 + 区间（真实 API 数据）
			const answer = page.locator("[data-primary-answer]");
			await expect(answer).toBeVisible();
			await expect(answer).toContainText(/收盘/);
			// Calendar sessions missing from retained prices remain explicit.
			await expect(page.getByTestId(`chart-gaps-${ETF_ID}`)).toContainText("缺失交易日");
			await expect(page.getByText(/来源 tushare · 快照/)).toBeVisible();
			const sentinelResponse = await page.request.post(`${apiOrigin}/api/v1/market/chart`, {
				headers: { "X-Ditto-API-Contract-Version": "v1" },
				data: { instrument_id: ETF_ID, start_date: "2026-01-05", end_date: "2026-03-08", period: "daily", adjustment: "none" },
			});
			expect(sentinelResponse.status()).toBe(200);
			const sentinel = (await sentinelResponse.json()).data as { bars: Array<{ high: number }>; missing_sessions: string[] };
			expect(sentinel.missing_sessions).toContain("2026-03-04");
			expect(sentinel.missing_sessions).not.toContain("2026-03-07");
			expect(Math.max(...sentinel.bars.map((bar) => bar.high))).toBeLessThan(1_000_000);

			// 指标开关（日线周期下可用）：MACD+RSI 副图让 pane 数从 2（价格+量）变 4
			const host2 = page.locator(`[data-chart-interaction-contract="instrument-candles-${ETF_ID}"]`);
			await expect(host2).toHaveAttribute("data-chart-panes", "2");
			await page.getByTestId("indicator-toggle-macd").check();
			await page.getByTestId("indicator-toggle-rsi").check();
			await expect(host2).toHaveAttribute("data-chart-panes", "4");

			// ETF 净值叠加（fixture 已播种净值）+ 刷新后开关保持（页面级持久化）
			await page.getByTestId("indicator-toggle-nav").check();
			await expect(page.locator('[data-state="nav-unavailable"]')).toHaveCount(0);
			await page.reload();
			await expect(
				page.locator(`[data-chart-interaction-contract="instrument-candles-${ETF_ID}"]`),
			).toBeVisible();
			await expect(host2).toHaveAttribute("data-chart-panes", "4");
			await expect(page.getByTestId("indicator-toggle-rsi")).toBeChecked();
			await expect(page.getByTestId("indicator-toggle-nav")).toBeChecked();

			// Weekly OHLCV and partial status come from the server calendar.
			await page.getByRole("button", { name: "周" }).click();
			await expect(host).toHaveAttribute("aria-label", /周K 线/);
			await expect(host2).toHaveAttribute("data-chart-panes", "2");
			await expect(page.getByTestId("indicator-toggle-rsi")).toBeDisabled();
			await expect(page.getByText("指标叠加仅日线周期")).toBeVisible();
			await expect(page.getByText("部分周期不完整")).toBeVisible();
			await expect(page.getByTestId(`chart-period-instrument-candles-${ETF_ID}`)).toContainText(
				"区间 2026-05-11 → 2026-05-15",
			);
			const originalEnd = await page.getByLabel("截至日期").inputValue();
			await page.getByLabel("截至日期").fill("2026-05-13");
			await expect(page.getByTestId(`chart-period-instrument-candles-${ETF_ID}`)).toContainText(
				"区间 2026-05-11 → 2026-05-13 · 未完成",
			);
			await page.getByLabel("截至日期").fill(originalEnd);
			await expect(page.getByTestId(`chart-period-instrument-candles-${ETF_ID}`)).toContainText(
				"区间 2026-05-11 → 2026-05-15",
			);
			const [csvDownload] = await Promise.all([
				page.waitForEvent("download"),
				page.getByTestId(`chart-export-csv-instrument-candles-${ETF_ID}`).click(),
			]);
			const csv = await readFile(await csvDownload.path(), "utf8");
			expect(csv).toContain("calendar_snapshot_ids");
			expect(csv).toContain("bar_source_snapshot_ids");
			expect(csv).toContain("snapshot:tushare:etf_daily:");
			expect(csv).toContain("knowledge_cutoff");
			expect(csv).toContain("weekly");
			const [pngDownload] = await Promise.all([
				page.waitForEvent("download"),
				page.getByTestId(`chart-export-png-instrument-candles-${ETF_ID}`).click(),
			]);
			expect(pngDownload.suggestedFilename()).toMatch(/\.png$/);

			// ETF 复权未接线：切换禁用并给出原因
			await expect(page.getByRole("button", { name: "前复权" })).toBeDisabled();
			await expect(page.getByText("ETF 复权暂未接入")).toBeVisible();

			await expectNoSeriousAccessibilityViolations(page);
			expect(browserErrors).toEqual([]);
		});

		test("ETF without local NAV data degrades to an explicit unavailable state", async ({ page }) => {
			const browserErrors = captureBrowserErrors(page);
			await page.goto(`${webOrigin}/instruments/${ETF_NO_NAV_ID}?tab=chart`);
			await page.getByTestId("indicator-toggle-nav").check();
			await expect(page.locator('[data-state="nav-unavailable"]')).toBeVisible();
			expect(browserErrors.filter((line) => !line.includes("status of 400"))).toEqual([]);
		});

		test("selects ETF exposure and inspects dated comparison evidence through the production API", async ({ page }) => {
			await page.goto(`${webOrigin}/markets`);
			const comparison = page.locator('[data-info-unit="etf-candidates"]');
			await expect(comparison).toBeVisible();
			await comparison.getByLabel("研究日期").fill("2026-05-20");
			await comparison.getByLabel("知识截止").fill("2026-05-22T10:00");
			await comparison.getByLabel("来源快照").selectOption("snapshot:recorded:etf-system");
			await comparison.getByLabel("指数暴露").fill("000300.SH");
			await expect(comparison.locator("details")).toHaveCount(2);
			const domestic = comparison.locator("details").filter({ hasText: "510300" });
			await domestic.locator("summary").click();
			await expect(domestic.getByText(/仅供记录式参考，不参与正式排名/)).toBeVisible();
			await expect(domestic.getByText(/跟踪偏离 0.00%/)).toBeVisible();
			await expect(domestic.getByText("规模", { exact: true }).locator("..")).toContainText("500000000 CNY");
			await expect(domestic.getByText("托管费", { exact: true }).locator("..")).toContainText("no_observation");
			const missingSeries = comparison.locator("details").filter({ hasText: "159915" });
			await missingSeries.locator("summary").click();
			await expect(missingSeries.getByText(/同口径跟踪评价不可计算/)).toBeVisible();
			await comparison.getByLabel("指数暴露").fill("NDX");
			await expect(comparison.locator("details")).toHaveCount(1);
			const crossBorder = comparison.locator("details").filter({ hasText: "513100" });
			await crossBorder.locator("summary").click();
			await expect(crossBorder.getByText("最近已披露 NAV", { exact: true }).locator("..")).toContainText("2026-05-18");
			await expect(crossBorder.getByText("原始收盘价", { exact: true }).locator("..")).toContainText("2026-05-20");
			await comparison.getByLabel("指数暴露").fill("");
			await comparison.getByLabel("资产暴露").fill("跨境股票");
			await expect(comparison.locator("details")).toHaveCount(1);
			await page.route("**/api/v1/metadata/etf-candidates?**", (route) => route.fulfill({ status: 503, body: "unavailable" }));
			await comparison.getByLabel("代码或名称").fill("513100");
			await expect(comparison.getByRole("button", { name: "比较失败，重试" })).toBeVisible();
			await page.unroute("**/api/v1/metadata/etf-candidates?**");
			await comparison.getByRole("button", { name: "比较失败，重试" }).click();
			await expect(comparison.locator("details")).toHaveCount(1);
		});

		test("saves and restores an ETF research allocation without Paper execution", async ({ page }) => {
			await page.goto(`${webOrigin}/markets`);
			const comparison = page.locator('[data-info-unit="etf-candidates"]');
			await comparison.getByLabel("来源快照").selectOption("snapshot:recorded:etf-system");
			await comparison.getByLabel("指数暴露").fill("000300.SH");
			await expect(comparison.locator("details")).toHaveCount(2);
			await comparison.getByRole("checkbox", { name: /沪深300ETF-图表验收/ }).check();
			await comparison.getByRole("checkbox", { name: /创业板ETF-无净值验收/ }).check();
			await comparison.getByLabel("配置理由").fill("equal broad exposure");
			let droppedResponse = false;
			await page.route("**/api/v1/portfolio/etf-allocations/*/versions", async (route) => {
				if (route.request().method() === "POST" && !droppedResponse) {
					droppedResponse = true;
					await route.fetch();
					await route.fulfill({ status: 503, body: "response lost" });
					return;
				}
				await route.continue();
			});
			await comparison.getByRole("button", { name: "保存候选版本" }).click();
			await expect(comparison.getByRole("alert")).toContainText("保存失败");
			await page.reload();
			await expect(comparison.getByRole("checkbox", { name: /沪深300ETF-图表验收/ })).toBeChecked();
			await expect(comparison.getByLabel("配置理由")).toHaveValue("equal broad exposure");
			await comparison.getByRole("button", { name: "保存候选版本" }).click();
			await expect(comparison.getByText(/已保存 etf-allocation-/)).toBeVisible();
			await expect(comparison.getByText(/research_only/)).toBeVisible();
			const version = new URL(page.url()).searchParams.get("etfVersion");
			expect(version).toMatch(/^etf-allocation-/);
			const cutoff = await comparison.getByLabel("知识截止").inputValue();
			await page.reload();
			await expect(comparison.getByLabel("知识截止")).toHaveValue(cutoff);
			await expect(comparison.getByRole("checkbox", { name: /沪深300ETF-图表验收/ })).toBeChecked();
			await expect(comparison.getByRole("checkbox", { name: /创业板ETF-无净值验收/ })).toBeChecked();
			await expect(comparison.getByText(/已保存 etf-allocation-/)).toBeVisible();
			await comparison.getByLabel("权重模式").selectOption("manual");
			await comparison.getByLabel("ETF 2000001 权重").fill("0.3");
			await comparison.getByLabel("ETF 2000002 权重").fill("0.5");
			await comparison.getByLabel("配置理由").fill("manual revision");
			await comparison.getByRole("button", { name: "保存候选版本" }).click();
			await expect(comparison.getByText(/已保存 etf-allocation-/)).toBeVisible();
			await expect.poll(() => new URL(page.url()).searchParams.get("etfVersion")).not.toBe(version);
			await expect(comparison.getByLabel("已保存版本").locator("option")).toHaveCount(3);
			await comparison.getByLabel("已保存版本").selectOption(version ?? "");
			await page.reload();
			await expect(comparison.getByLabel("已保存版本")).toHaveValue(version ?? "");
		});

		test("reviews a cross-border ETF target against a distinct Manual ledger", async ({ page, request }) => {
			const accountId = `etf-cross-border-${crypto.randomUUID()}`;
			const headers = { "X-Ditto-API-Contract-Version": "v1" };
			const created = await request.post(`${apiOrigin}/api/v1/manual/accounts`, {
				headers,
				data: { account_id: accountId, name: "跨境复盘账本", opened_at: "2026-05-21T00:00:00Z", currency: "CNY" },
			});
			expect(created.status()).toBe(201);
			const opening = await request.post(`${apiOrigin}/api/v1/manual/accounts/${accountId}/events`, {
				headers,
				data: { event_type: "opening_cash", trade_date: "2026-05-21", settlement_date: "2026-05-21", idempotency_key: `opening-${accountId}`, actor: "system-e2e", gross_amount: "100000" },
			});
			expect(opening.status()).toBe(201);
			await page.goto(`${webOrigin}/markets`);
			const comparison = page.locator('[data-info-unit="etf-candidates"]');
			await comparison.getByLabel("研究日期").fill("2026-05-21");
			await comparison.getByLabel("知识截止").fill("2026-05-21T18:00");
			await comparison.getByLabel("来源快照").selectOption("snapshot:recorded:etf-system");
			await comparison.getByLabel("指数暴露").fill("NDX");
			await comparison.getByRole("checkbox", { name: /跨境ETF-比较验收/ }).check();
			await comparison.getByLabel("单仓上限").fill("0.8");
			await comparison.getByLabel("配置理由").fill("cross-border recorded review");
			await comparison.getByRole("button", { name: "保存候选版本" }).click();
			await expect(comparison.getByText(/已保存 etf-allocation-/)).toBeVisible();
			await comparison.getByLabel("复盘账户").selectOption(`manual:${accountId}`);
			await comparison.getByRole("link", { name: "查看配置与账户复盘" }).click();
			const review = page.getByRole("region", { name: "ETF 配置复盘" });
			await expect(review.getByText(/已知同指数目标暴露：NDX 0.80000000/)).toBeVisible();
			await review.getByLabel("复盘账本日期").fill("2026-05-21");
			await expect(review.getByText(/Manual 用户记录账本/)).toBeVisible();
			await expect(review.getByText(/实际现金 100000/)).toBeVisible();
			await expect(review.getByText(/其他工具的穿透重叠：未知/)).toBeVisible();
			await page.reload();
			await expect(review.getByLabel("复盘账户")).toHaveValue(`manual:${accountId}`);
		});

		test("stocks stay fail-closed until the explicit experimental opt-in, then use retained factors", async ({
			page,
		}) => {
			const browserErrors = captureBrowserErrors(page);
			await page.goto(`${webOrigin}/instruments/${STOCK_ID}?tab=chart`);

			// 默认 fail-closed：experimental 成熟度门控可见
			await expect(page.locator('[data-state="experimental-disabled"]')).toBeVisible();

			// 显式研究开关后渲染真实蜡烛
			await page.getByTestId("chart-experimental-toggle").check();
			const host = page.locator(`[data-chart-interaction-contract="instrument-candles-${STOCK_ID}"]`);
			await expect(host).toBeVisible();
			const answer = page.locator("[data-primary-answer]");
			await expect(answer).toBeVisible();
			const rawClose = (await answer.locator("[data-answer-metric]").first().innerText()).trim();
			const rawScope = (await answer.locator("[data-answer-scope]").innerText()).trim();

			// 前复权（服务端保留因子）：最新收盘锚定不变（最新因子即基准），
			// 7 月前历史价格整体下修 → 区间低值改变。
			await page.getByRole("button", { name: "前复权" }).click();
			await expect(page.getByText(/复权：qfq/)).toBeVisible();
			await expect(answer.locator("[data-answer-metric]").first()).toHaveText(rawClose);
			await expect
				.poll(async () => (await answer.locator("[data-answer-scope]").innerText()).trim())
				.not.toBe(rawScope);

			await expectNoSeriousAccessibilityViolations(page);
			// fail-closed 成熟度门控按设计返回 422，浏览器会把该传输行记入
			// console error（与 outage.spec 对 net::ERR 的处理同 convention）；
			// 语义已由 experimental-disabled 面板断言，这里只要求无其他错误。
			const unexpected = browserErrors.filter((line) => !line.includes("status of 422"));
			expect(unexpected).toEqual([]);
		});
	});
