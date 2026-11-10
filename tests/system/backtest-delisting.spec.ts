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
	await expect(page.getByTestId("backtest-detail-meta")).toContainText("failed", { timeout: 60000 });
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
	expect(state.nav).toBeCloseTo(
		(state.positions ?? []).reduce((sum, position) => sum + position.market_value, 0) + state.cash_available,
		6,
	);
	return held;
}

test("delisted holding survives exit with evidenced anchor; missing final-status evidence recovers along the original config", async ({ page }) => {
	const errors: string[] = [];
	page.on("pageerror", error => errors.push(error.message));
	const failedId = await submit(page, "delisting_fixture", "2017-07-03", "2017-07-10");
	const failed = await request(page, failedId);
	await page.reload();
	await expect(page.getByText(/unknown stock status.*1005603.*2017-07/).first()).toBeVisible();

	await page.request.post(`${apiOrigin}/system-fixture/delisting/repair-status`);
	await page.getByRole("button", { name: "补证后沿原配置新建运行" }).focus();
	await page.keyboard.press("Enter");
	const link = page.getByRole("link", { name: "打开补证后的新运行" });
	await expect(link).toBeVisible();
	const runId = (await link.getAttribute("href"))?.split("/").at(-1);
	if (!runId) throw new Error("missing recovery identity");
	await link.click();
	await expect(page.getByTestId("backtest-detail-meta")).toContainText("completed", { timeout: 60000 });
	expect(runId).not.toBe(failedId);

	// The frozen exit fact is traceable in the saved daily participation.
	const saved = await request(page, runId);
	const delistedDays = saved.participation.filter(
		(row: { instrument_id: number; status: string; execution_rule: string | null }) =>
			row.instrument_id === 1005603 && row.status === "delisted",
	);
	expect(delistedDays.map((row: { trade_date: string }) => row.trade_date)).toEqual(["2017-07-07", "2017-07-10"]);
	for (const row of delistedDays)
		expect(row.execution_rule).toContain("已退出上市 2017-07-07; 持仓保留, 估值锚定 2017-07-06 收盘 1.7 元; 无退市清算会计证据");

	const result = await report(page, runId);
	const fills: Fill[] = result.fee_statement.fills;
	const entry = fills.filter(fill => fill.instrument_id === 1005603);
	expect(entry.some(fill => fill.direction === "buy" && fill.trade_date === "2017-07-03")).toBe(true);
	// Before the exit the stock still trades: rebalancing sells are honest.
	expect(entry.some(fill => fill.direction === "sell" && fill.trade_date < "2017-07-07")).toBe(true);
	// On and after the frozen exit day there is no market: no sell can fill
	// and none is invented.
	expect(entry.some(fill => fill.direction === "sell" && fill.trade_date >= "2017-07-07")).toBe(false);
	expect(fills.some(fill => fill.instrument_id === 1007561 && fill.direction === "buy")).toBe(true);

	const held = exitHeld(result, 1005603);
	expect(held.quantity).toBe(
		entry.reduce(
			(sum, fill) => sum + (fill.direction === "buy" ? fill.quantity : -fill.quantity),
			0,
		),
	);
	expect(held.market_value).toBeCloseTo(held.quantity * 1.7, 6);

	await page.reload();
	await page.locator("summary").filter({ hasText: "请求与冻结来源" }).press("Enter");
	const dates = page.getByLabel("逐日参与日期");
	await dates.selectOption("2017-07-07");
	await expect(page.getByRole("row", { name: /000033\.SZ.*已退出上市 2017-07-07; 持仓保留, 估值锚定 2017-07-06 收盘 1\.7 元/ })).toBeVisible();
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
	expect(await request(page, failedId)).toEqual(failed);
	expect((await new AxeBuilder({ page }).analyze()).violations.filter(v => ["critical", "serious"].includes(v.impact ?? ""))).toEqual([]);
	expect(errors).toEqual([]);
});

test("a missing exit fact fails closed and recovers through a new request identity", async ({ page }) => {
	const errors: string[] = [];
	page.on("pageerror", error => errors.push(error.message));
	const failedId = await submit(page, "delisting_exit_fact_fixture", "2016-05-09", "2016-05-16");
	const failed = await request(page, failedId);
	await page.reload();
	await expect(page.getByText(/missing backtest member\/date inputs.*1005762.*2016-05-13/).first()).toBeVisible();

	await page.request.post(`${apiOrigin}/system-fixture/delisting/repair-exit-fact`);

	// The frozen roster keeps its missing exit fact: recovery is a new request
	// from the normal entry, never a rewrite of the failed one. The saved
	// submission draft locks the form on the previous run; the form's own
	// reset control starts another run through real UI actions.
	await page.goto(`${webOrigin}/research/strategies/delisting_exit_fact_fixture`);
	await page.getByRole("button", { name: "提交回测", exact: true }).click();
	const form = page.getByRole("dialog", { name: "提交回测" });
	await form.getByRole("button", { name: "开始另一回测" }).click();
	await form.getByLabel("历史请求用途").selectOption("reconstruction");
	await form.getByLabel("策略版本").selectOption("1");
	await form.getByLabel("开始日期").fill("2016-05-09");
	await form.getByLabel("结束日期").fill("2016-05-16");
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
			row.instrument_id === 1005762 && row.status === "delisted",
	);
	expect(delistedDays.map((row: { trade_date: string }) => row.trade_date)).toEqual(["2016-05-13", "2016-05-16"]);
	for (const row of delistedDays)
		expect(row.execution_rule).toContain("已退出上市 2016-05-13; 持仓保留, 估值锚定 2016-05-12 收盘 4.4 元; 无退市清算会计证据");

	const result = await report(page, runId);
	const fills: Fill[] = result.fee_statement.fills;
	const entry = fills.filter(fill => fill.instrument_id === 1005762);
	expect(entry.length).toBeGreaterThan(0);
	expect(entry.every(fill => fill.direction === "buy")).toBe(true);
	const held = exitHeld(result, 1005762);
	expect(held.quantity).toBe(entry.reduce((sum, fill) => sum + fill.quantity, 0));
	expect(held.market_value).toBeCloseTo(held.quantity * 4.4, 6);

	expect(await request(page, failedId)).toEqual(failed);
	expect(errors).toEqual([]);
});
