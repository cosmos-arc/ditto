import { readFile } from "node:fs/promises";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const webOrigin = process.env["DITTO_SYSTEM_WEB_ORIGIN"];
const apiOrigin = process.env["DITTO_SYSTEM_API_ORIGIN"];
if (!webOrigin || !apiOrigin) throw new Error("isolated system origins are required");

type Fill = { instrument_id: number; trade_date: string; direction: string; quantity: number; price: number };

async function submit(page: Page, strategy: string, start: string, end: string) {
	await page.goto(`${webOrigin}/research/strategies/${strategy}`);
	await page.getByRole("button", { name: "提交回测", exact: true }).click();
	const form = page.getByRole("dialog", { name: "提交回测" });
	await form.getByLabel("历史请求用途").selectOption("reconstruction");
	await form.getByLabel("策略版本").selectOption("1");
	await form.getByLabel("开始日期").fill(start);
	await form.getByLabel("结束日期").fill(end);
	await form.getByLabel("初始资金（元）").fill("1000000");
	await form.getByRole("button", { name: "提交回测", exact: true }).focus();
	await page.keyboard.press("Enter");
	const link = form.getByRole("link", { name: "查看本次回测" });
	await expect(link).toBeVisible();
	const id = (await link.getAttribute("href"))?.split("/").at(-1);
	if (!id) throw new Error("missing saved request");
	await link.click();
	await expect(page.getByTestId("backtest-detail-meta")).toContainText(/completed|failed/, { timeout: 60000 });
	return id;
}

async function request(page: Page, id: string) {
	return (await (await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${id}/request`)).json()).data;
}

async function report(page: Page, id: string) {
	return (await (await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${id}/report`)).json()).data;
}

function exitHeld(result: { final_account_state?: { positions?: { instrument_id: number; quantity: number; market_value: number }[]; cash_available: number; nav: number } }, instrumentId: number) {
	const state = result.final_account_state;
	if (!state) throw new Error("missing final account state");
	const held = (state.positions ?? []).find(position => position.instrument_id === instrumentId);
	if (!held) throw new Error(`missing exit-held position ${instrumentId}`);
	// The terminated holding keeps its anchored value: NAV stays the sum of
	// positions and cash, nothing is zeroed out.
	expect(state.nav).toBeCloseTo(
		(state.positions ?? []).reduce((sum, position) => sum + position.market_value, 0) + state.cash_available,
		6,
	);
	return held;
}

test("a terminated ETF keeps its holding and equity across the frozen exit fact", async ({ page }) => {
	const errors: string[] = [];
	page.on("pageerror", error => errors.push(error.message));
	const runId = await submit(page, "etf_delisting_fixture", "2015-08-20", "2015-08-28");
	await expect(page.getByTestId("backtest-detail-meta")).toContainText("completed");

	// The frozen exit fact is traceable in the saved daily participation.
	const saved = await request(page, runId);
	const delistedDays = saved.participation.filter(
		(row: { instrument_id: number; status: string; execution_rule: string | null }) =>
			row.instrument_id === 2009171 && row.status === "delisted",
	);
	expect(delistedDays.map((row: { trade_date: string }) => row.trade_date)).toEqual(["2015-08-27", "2015-08-28"]);
	for (const row of delistedDays)
		expect(row.execution_rule).toContain("已终止上市 2015-08-27; 持仓保留, 估值锚定 2015-08-26 收盘 1.77 元; 无终止上市清算会计证据");
	// Leaving the pool ≠ selling: the survivor stays eligible and keeps trading.
	expect(
		saved.participation.some(
			(row: { instrument_id: number; status: string; trade_date: string }) =>
				row.instrument_id === 2008801 && row.status === "eligible" && row.trade_date === "2015-08-28",
		),
	).toBe(true);

	const result = await report(page, runId);
	const fills: Fill[] = result.fee_statement.fills;
	const entry = fills.filter(fill => fill.instrument_id === 2009171);
	expect(entry.some(fill => fill.direction === "buy" && fill.trade_date < "2015-08-27")).toBe(true);
	// On and after the frozen termination day there is no market: no sell can
	// fill and no liquidation is invented.
	expect(entry.some(fill => fill.direction === "sell" && fill.trade_date >= "2015-08-27")).toBe(false);
	expect(fills.some(fill => fill.instrument_id === 2008801 && fill.direction === "buy" && fill.trade_date >= "2015-08-27")).toBe(true);

	const held = exitHeld(result, 2009171);
	expect(held.quantity).toBe(
		entry.reduce(
			(sum, fill) => sum + (fill.direction === "buy" ? fill.quantity : -fill.quantity),
			0,
		),
	);
	expect(held.market_value).toBeCloseTo(held.quantity * 1.77, 6);

	await page.reload();
	await page.locator("summary").filter({ hasText: "请求与冻结来源" }).press("Enter");
	const dates = page.getByLabel("逐日参与日期");
	await dates.selectOption("2015-08-27");
	const exitRow = page.getByRole("row", { name: /159917\.SZ.*已终止上市 2015-08-27; 持仓保留, 估值锚定 2015-08-26 收盘 1\.77 元/ });
	await expect(exitRow).toBeVisible();
	await exitRow.scrollIntoViewIfNeeded();
	await page.screenshot({ path: test.info().outputPath("etf-delisting-exit-note.png"), fullPage: true });
	await dates.focus();
	await expect(dates).toBeFocused();

	await page.getByRole("button", { name: "导出报告", exact: true }).click();
	const downloaded = page.waitForEvent("download");
	await page.getByRole("button", { name: "下载 JSON", exact: true }).press("Enter");
	const path = await (await downloaded).path();
	if (!path) throw new Error("export missing");
	const exported = JSON.parse(await readFile(path, "utf8"));
	expect(exported.request.runId).toBe(runId);
	expect(exported.request.participation).toEqual((await request(page, runId)).participation.map((row: { instrument_id: number; symbol: string; trade_date: string; status: string; warmup_available: number; warmup_required: number; evaluated: boolean; execution_rule: string | null }) => ({
		instrumentId: row.instrument_id, symbol: row.symbol, tradeDate: row.trade_date, status: row.status,
		warmupAvailable: row.warmup_available, warmupRequired: row.warmup_required,
		evaluated: row.evaluated, executionRule: row.execution_rule,
	})));
	await page.keyboard.press("Escape");
	await expect(page.getByRole("button", { name: "导出报告", exact: true })).toBeFocused();
	expect((await new AxeBuilder({ page }).analyze()).violations.filter(v => ["critical", "serious"].includes(v.impact ?? ""))).toEqual([]);
	expect(errors).toEqual([]);
});

test("a missing ETF exit fact fails closed and recovers through a new request identity", async ({ page }) => {
	const errors: string[] = [];
	page.on("pageerror", error => errors.push(error.message));
	const failedId = await submit(page, "etf_delisting_exit_fact_fixture", "2018-02-09", "2018-02-14");
	await expect(page.getByTestId("backtest-detail-meta")).toContainText("failed");
	const failed = await request(page, failedId);
	await page.reload();
	await expect(page.getByText(/missing backtest member\/date inputs.*2009271.*2018-02-14/).first()).toBeVisible();
	await page.screenshot({ path: test.info().outputPath("etf-delisting-exit-fact-refused.png"), fullPage: true });

	await page.request.post(`${apiOrigin}/system-fixture/etf-delisting/repair-exit-fact`);

	// The frozen roster keeps its missing exit fact: recovery is a new request
	// from the normal entry, never a rewrite of the failed one. The saved
	// submission draft locks the form on the previous run; the form's own
	// reset control starts another run through real UI actions.
	await page.goto(`${webOrigin}/research/strategies/etf_delisting_exit_fact_fixture`);
	await page.getByRole("button", { name: "提交回测", exact: true }).click();
	const form = page.getByRole("dialog", { name: "提交回测" });
	await form.getByRole("button", { name: "开始另一回测" }).click();
	await form.getByLabel("历史请求用途").selectOption("reconstruction");
	await form.getByLabel("策略版本").selectOption("1");
	await form.getByLabel("开始日期").fill("2018-02-09");
	await form.getByLabel("结束日期").fill("2018-02-14");
	await form.getByLabel("初始资金（元）").fill("1000000");
	await form.getByRole("button", { name: "提交回测", exact: true }).press("Enter");
	const link = form.getByRole("link", { name: "查看本次回测" });
	await expect(link).toBeVisible();
	const runId = (await link.getAttribute("href"))?.split("/").at(-1);
	if (!runId) throw new Error("missing saved request");
	await link.click();
	await expect(page.getByTestId("backtest-detail-meta")).toContainText("completed", { timeout: 60000 });
	expect(runId).not.toBe(failedId);

	const saved = await request(page, runId);
	const delistedDays = saved.participation.filter(
		(row: { instrument_id: number; status: string; execution_rule: string | null }) =>
			row.instrument_id === 2009271 && row.status === "delisted",
	);
	expect(delistedDays.map((row: { trade_date: string }) => row.trade_date)).toEqual(["2018-02-14"]);
	for (const row of delistedDays)
		expect(row.execution_rule).toContain("已终止上市 2018-02-14; 持仓保留, 估值锚定 2018-02-13 收盘 3.85 元; 无终止上市清算会计证据");

	const result = await report(page, runId);
	const fills: Fill[] = result.fee_statement.fills;
	const entry = fills.filter(fill => fill.instrument_id === 2009271);
	expect(entry.length).toBeGreaterThan(0);
	expect(entry.some(fill => fill.direction === "sell" && fill.trade_date >= "2018-02-14")).toBe(false);
	const held = exitHeld(result, 2009271);
	expect(held.quantity).toBe(
		entry.reduce(
			(sum, fill) => sum + (fill.direction === "buy" ? fill.quantity : -fill.quantity),
			0,
		),
	);
	expect(held.market_value).toBeCloseTo(held.quantity * 3.85, 6);

	expect(await request(page, failedId)).toEqual(failed);
	expect(errors).toEqual([]);
});
