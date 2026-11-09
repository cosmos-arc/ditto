import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const webOrigin = process.env["DITTO_SYSTEM_WEB_ORIGIN"];
const apiOrigin = process.env["DITTO_SYSTEM_API_ORIGIN"];
if (!webOrigin || !apiOrigin) throw new Error("isolated system origins are required");

test("ordinary 2014 request persists its failed freeze and recovers into a new real engine run", async ({ page }) => {
	const errors: string[] = [];
	page.on("pageerror", (error) => errors.push(error.message));
	await page.goto(`${webOrigin}/research/strategies/seed_etf_industry_rotation`);
	await page.getByRole("button", { name: "提交回测", exact: true }).click();
	const form = page.getByRole("dialog", { name: "提交回测" });
	await form.getByLabel("历史请求用途").selectOption("reconstruction");
	await form.getByLabel("策略版本").selectOption("1");
	await form.getByLabel("开始日期").fill("2014-10-13");
	await form.getByLabel("结束日期").fill("2014-11-07");
	await form.getByLabel("初始资金（元）").fill("250000");
	await form.getByRole("button", { name: "提交回测", exact: true }).focus();
	await page.keyboard.press("Enter");
	const originalLink = form.getByRole("link", { name: "查看本次回测" });
	await expect(originalLink).toBeVisible();
	const originalId = (await originalLink.getAttribute("href"))?.split("/").at(-1);
	expect(originalId).toBeTruthy();
	await originalLink.click();
	await expect(page.getByTestId("backtest-detail-meta")).toContainText("failed", { timeout: 60000 });
	await page.reload();
	await expect(page.getByText(/请求区间 2014-10-13/)).toBeVisible();
	await expect(page.getByText(/missing retained fund_adj/).first()).toBeVisible();
	await expect(page.getByText(/冻结证券.*510300.SH.*510500.SH/)).toBeVisible();
	const oldResponse = await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${originalId}/request`);
	expect(oldResponse.ok()).toBeTruthy();
	const oldRequest = (await oldResponse.json()).data;
	expect(oldRequest.input_status).toBe("blocked");
	expect(Date.parse(oldRequest.sources[0].received_at)).toBeGreaterThanOrEqual(Date.UTC(2026, 0, 1));
	expect(oldRequest.sources.find((source: { dataset: string }) => source.dataset === "etf_daily").request_start).toBe(
		"2014-01-01",
	);
	const repair = await page.request.post(`${apiOrigin}/system-fixture/history/repair`);
	expect(repair.ok()).toBeTruthy();
	const recover = page.getByRole("button", { name: "补证后沿原配置新建运行" });
	await recover.focus();
	await page.keyboard.press("Enter");
	const next = page.getByRole("link", { name: "打开补证后的新运行" });
	await expect(next).toBeVisible();
	const newId = (await next.getAttribute("href"))?.split("/").at(-1);
	expect(newId).not.toBe(originalId);
	await next.click();
	await expect(page.getByTestId("backtest-detail-meta")).toContainText("completed", { timeout: 60000 });
	await page.reload();
	const disclosure = page.locator("summary").filter({ hasText: "请求与冻结来源" });
	await disclosure.focus();
	await page.keyboard.press("Enter");
	await expect(page.getByText(/输入预检通过/)).toBeVisible();
	await expect(page.getByText(/请求区间 2014-10-13/)).toBeVisible();
	const [newRun, newRequest, nav, report, oldAgain] = await Promise.all([
		page.request.get(`${apiOrigin}/api/v1/backtests/runs/${newId}`),
		page.request.get(`${apiOrigin}/api/v1/backtests/runs/${newId}/request`),
		page.request.get(`${apiOrigin}/api/v1/backtests/runs/${newId}/nav`),
		page.request.get(`${apiOrigin}/api/v1/backtests/runs/${newId}/report`),
		page.request.get(`${apiOrigin}/api/v1/backtests/runs/${originalId}/request`),
	]);
	expect((await newRun.json()).data.parent_run_id).toBe(originalId);
	const saved = (await newRequest.json()).data;
	expect(saved).toMatchObject({
		purpose: "historical_reconstruction",
		input_status: "ready",
		start_date: "2014-10-13",
		end_date: "2014-11-07",
		initial_cash: 250000,
		members: oldRequest.members,
	});
	expect(saved.participation.every((row: { evaluated: boolean }) => row.evaluated)).toBe(true);
	expect(
		saved.participation.find(
			(row: { instrument_id: number; trade_date: string }) =>
				row.instrument_id === 2001004 && row.trade_date === "2014-10-13",
		).status,
	).toBe("not_listed");
	expect(
		saved.participation.find(
			(row: { instrument_id: number; trade_date: string }) =>
				row.instrument_id === 2001004 && row.trade_date === "2014-10-14",
		).status,
	).toBe("warmup");
	expect(
		saved.participation.find(
			(row: { instrument_id: number; trade_date: string }) =>
				row.instrument_id === 2001002 && row.trade_date === "2014-10-20",
		).status,
	).toBe("outside_universe");
	const dateSelector = page.getByLabel("逐日参与日期");
	await dateSelector.focus();
	await expect(dateSelector).toBeFocused();
	await dateSelector.selectOption("2014-10-14");
	await expect(dateSelector).toHaveValue("2014-10-14");
	await expect(dateSelector).toBeFocused();
	await expect(page.getByRole("row", { name: /510050.SH.*有效行情预热不足/ })).toBeVisible();
	await dateSelector.selectOption("2014-10-20");
	await expect(page.getByRole("row", { name: /510500.SH.*当日不在证券池/ })).toBeVisible();
	const tradesResponse = await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${newId}/trades`);
	const trades = (await tradesResponse.json()).data;
	expect(trades.some((trade: { instrument_id: number }) => trade.instrument_id === 2001004)).toBe(false);
	expect((await nav.json()).data.length).toBeGreaterThan(0);
	const savedReport = (await report.json()).data;
	expect(savedReport.aggregated_trade_stats.total_trades).toBeGreaterThan(0);
	expect(savedReport.fee_statement.fills.length).toBeGreaterThan(0);
	for (const fill of savedReport.fee_statement.fills) {
		expect(fill.stamp_duty).toBe(0);
		expect(fill.transfer_fee).toBe(0);
		expect(fill.total_fee).toBe(fill.commission);
	}

	expect((await oldAgain.json()).data).toEqual(oldRequest);
	const accessibility = await new AxeBuilder({ page }).analyze();
	expect(accessibility.violations.filter((v) => ["critical", "serious"].includes(v.impact ?? ""))).toEqual([]);
	expect(errors).toEqual([]);
});

test("main-board IPO rules survive a failed freeze, repair, fills, rejection and reload", async ({ page }) => {
	const errors: string[] = [];
	page.on("pageerror", (error) => errors.push(error.message));
	await page.goto(`${webOrigin}/research/strategies/mainboard_ipo_fixture`);
	await page.getByRole("button", { name: "提交回测", exact: true }).click();
	const form = page.getByRole("dialog", { name: "提交回测" });
	await form.getByLabel("历史请求用途").selectOption("reconstruction");
	await form.getByLabel("策略版本").selectOption("1");
	await form.getByLabel("开始日期").fill("2026-10-08");
	await form.getByLabel("结束日期").fill("2026-10-16");
	await form.getByLabel("初始资金（元）").fill("250000");
	await form.getByRole("button", { name: "提交回测", exact: true }).focus();
	await page.keyboard.press("Enter");
	const link = form.getByRole("link", { name: "查看本次回测" });
	await expect(link).toBeVisible();
	const originalId = (await link.getAttribute("href"))?.split("/").at(-1);
	await link.click();
	await expect(page.getByTestId("backtest-detail-meta")).toContainText("failed", { timeout: 60000 });
	await page.reload();
	await expect(page.getByText(/stock price band disagrees with dated rule/).first()).toBeVisible();
	const oldRequest = (await (await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${originalId}/request`)).json())
		.data;
	expect((await page.request.post(`${apiOrigin}/system-fixture/mainboard/repair`)).ok()).toBe(true);
	await page.getByRole("button", { name: "补证后沿原配置新建运行" }).focus();
	await page.keyboard.press("Enter");
	const next = page.getByRole("link", { name: "打开补证后的新运行" });
	await expect(next).toBeVisible();
	const newId = (await next.getAttribute("href"))?.split("/").at(-1);
	expect(newId).not.toBe(originalId);
	await next.click();
	await expect(page.getByTestId("backtest-detail-meta")).toContainText("completed", { timeout: 60000 });
	await page.reload();
	await page.locator("summary").filter({ hasText: "请求与冻结来源" }).click();
	const dates = page.getByLabel("逐日参与日期");
	await dates.focus();
	await expect(dates).toBeFocused();
	await dates.selectOption("2026-10-13");
	await expect(page.getByRole("row", { name: /001246.SZ.*无日涨跌幅限制/ })).toBeVisible();
	await dates.selectOption("2026-10-14");
	await expect(dates).toBeFocused();
	await expect(page.getByRole("row", { name: /001246.SZ.*涨跌幅 10%.*100 股.*0.01 元.*T\+1/ })).toBeVisible();
	const trades = (await (await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${newId}/trades`)).json()).data;
	expect(
		trades.some(
			(row: { instrument_id: number; entry_date: string }) =>
				row.instrument_id === 1001002 && row.entry_date === "2026-10-08",
		),
	).toBe(true);
	// The second purchase is still open, so it belongs to saved holdings, not closed round trips.
	const report = (await (await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${newId}/report`)).json()).data;
	expect(report.final_account_state.positions).toEqual([
		expect.objectContaining({ instrument_id: 1001002, quantity: 1900 }),
	]);
	const audit = (await (await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${newId}/audit`)).json()).data;
	expect(
		audit.some(
			(row: { trade_date: string; instrument_id: number; payload: { reason?: string } }) =>
				row.trade_date === "2026-10-14" && row.instrument_id === 1001002 && row.payload.reason === "limit_up_no_buy",
		),
	).toBe(true);
	expect(audit).toEqual(
		expect.arrayContaining([
			expect.objectContaining({
				trade_date: "2026-10-15",
				instrument_id: 1001002,
				payload: expect.objectContaining({ decision: "accepted", final_quantity: 1900 }),
			}),
		]),
	);
	expect(trades).toEqual(
		expect.arrayContaining([
			expect.objectContaining({ instrument_id: 1001001, entry_date: "2026-10-13", exit_date: "2026-10-14" }),
		]),
	);
	expect(
		(await (await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${originalId}/request`)).json()).data,
	).toEqual(oldRequest);
	const accessibility = await new AxeBuilder({ page }).analyze();
	expect(accessibility.violations.filter((v) => ["critical", "serious"].includes(v.impact ?? ""))).toEqual([]);
	expect(errors).toEqual([]);
});

test("an unlimited SZSE IPO refuses market orders and reopens the saved reason", async ({ page }) => {
	await page.goto(`${webOrigin}/research/strategies/mainboard_market_fixture`);
	await page.getByRole("button", { name: "提交回测", exact: true }).click();
	const form = page.getByRole("dialog", { name: "提交回测" });
	await form.getByLabel("历史请求用途").selectOption("reconstruction");
	await form.getByLabel("策略版本").selectOption("1");
	await form.getByLabel("开始日期").fill("2026-10-08");
	await form.getByLabel("结束日期").fill("2026-10-13");
	await form.getByLabel("初始资金（元）").fill("250000");
	await form.getByRole("button", { name: "提交回测", exact: true }).click();
	const link = form.getByRole("link", { name: "查看本次回测" });
	await expect(link).toBeVisible();
	const id = (await link.getAttribute("href"))?.split("/").at(-1);
	await link.click();
	await expect(page.getByTestId("backtest-detail-meta")).toContainText("completed", { timeout: 60000 });
	await page.reload();
	const audit = (await (await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${id}/audit`)).json()).data;
	expect(audit).toEqual(
		expect.arrayContaining([
			expect.objectContaining({
				trade_date: "2026-10-08",
				instrument_id: 1001002,
				payload: expect.objectContaining({ decision: "rejected", reason: "unsupported_order_type", final_quantity: 0 }),
			}),
		]),
	);
	const report = (await (await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${id}/report`)).json()).data;
	await page.getByRole("tab", { name: "审计证据" }).click();
	const rejection = page.locator("details").filter({ hasText: "unsupported_order_type" }).first();
	await rejection.locator("summary").focus();
	await page.keyboard.press("Enter");
	await expect(rejection.locator("pre")).toBeVisible();
	await expect(rejection.locator("pre")).toContainText("unsupported_order_type");
	expect(
		report.final_account_state.positions.some((row: { instrument_id: number }) => row.instrument_id === 1001002),
	).toBe(false);
});
