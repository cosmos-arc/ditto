import { readFile } from "node:fs/promises";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const webOrigin = process.env["DITTO_SYSTEM_WEB_ORIGIN"];
const apiOrigin = process.env["DITTO_SYSTEM_API_ORIGIN"];
if (!webOrigin || !apiOrigin) throw new Error("isolated system origins are required");

async function submit(page: Page, start: string, end: string, kind = "market_on_close", cash = "250000") {
	await page.goto(`${webOrigin}/research/strategies/chinext_${kind}_fixture`);
	await page.getByRole("button", { name: "提交回测", exact: true }).click();
	const form = page.getByRole("dialog", { name: "提交回测" });
	await form.getByLabel("历史请求用途").selectOption("reconstruction");
	await form.getByLabel("策略版本").selectOption("1");
	await form.getByLabel("开始日期").fill(start);
	await form.getByLabel("结束日期").fill(end);
	await form.getByLabel("初始资金（元）").fill(cash);
	await form.getByRole("button", { name: "提交回测", exact: true }).focus();
	await page.keyboard.press("Enter");
	const link = form.getByRole("link", { name: "查看本次回测" });
	await expect(link).toBeVisible();
	const id = (await link.getAttribute("href"))?.split("/").at(-1);
	if (!id) throw new Error("missing persisted run");
	await link.click();
	return id;
}

test("ChiNext reform repairs stale 10% input, persists both rule epochs and exports actual fees", async ({ page }) => {
	const errors: string[] = [];
	page.on("pageerror", (error) => errors.push(error.message));
	const originalId = await submit(page, "2020-08-20", "2020-08-28");
	await expect(page.getByTestId("backtest-detail-meta")).toContainText("failed", { timeout: 60000 });
	await page.reload();
	await expect(page.getByText(/stock price band disagrees with dated rule/).first()).toBeVisible();
	const original = (await (await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${originalId}/request`)).json()).data;
	expect((await page.request.post(`${apiOrigin}/system-fixture/chinext/repair`)).ok()).toBe(true);
	await page.getByRole("button", { name: "补证后沿原配置新建运行" }).focus();
	await page.keyboard.press("Enter");
	const next = page.getByRole("link", { name: "打开补证后的新运行" });
	await expect(next).toBeVisible();
	const id = (await next.getAttribute("href"))?.split("/").at(-1);
	expect(id).not.toBe(originalId);
	await next.click();
	await expect(page.getByTestId("backtest-detail-meta")).toContainText("completed", { timeout: 60000 });
	await page.reload();
	await page.locator("summary").filter({ hasText: "请求与冻结来源" }).press("Enter");
	const dates = page.getByLabel("逐日参与日期");
	await dates.focus();
	await dates.selectOption("2020-08-21");
	await expect(page.getByRole("row", { name: /300750.SZ.*chinext.*涨跌幅 10%.*1000000 股/ })).toBeVisible();
	await dates.selectOption("2020-08-24");
	await expect(dates).toBeFocused();
	await expect(page.getByRole("row", { name: /300750.SZ.*2020-08-24.*涨跌幅 20%.*300000 股.*150000 股.*0.01 元.*T\+1/ })).toBeVisible();
	const report = (await (await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${id}/report`)).json()).data;
	const fills = report.fee_statement.fills;
    expect(fills).toEqual(expect.arrayContaining([expect.objectContaining({ instrument_id: 1003001, trade_date: "2020-08-24", direction: "buy", price: 12.1 })]));
	expect(fills.some((fill: { trade_date: string }) => fill.trade_date < "2020-08-24")).toBe(true);
	expect(fills.some((fill: { trade_date: string }) => fill.trade_date >= "2020-08-24")).toBe(true);
	let cash = 250000;
	for (const fill of fills) {
		const amount = fill.price * fill.quantity;
		expect(fill.stamp_duty).toBeCloseTo(fill.direction === "sell" ? amount * 0.001 : 0, 8);
		expect(fill.transfer_fee).toBeCloseTo(amount * 0.00002, 8);
		cash += (fill.direction === "buy" ? -amount : amount) - fill.total_fee;
	}
	expect(report.fee_statement.final_cash).toBeCloseTo(cash, 8);
	const audit = (await (await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${id}/audit`)).json()).data;
	for (const day of ["2020-08-21", "2020-08-25"]) {
        expect(audit.some((row: { trade_date: string; instrument_id: number; payload: { reason?: string } }) => row.trade_date === day && row.instrument_id === 1003002 && row.payload.reason === "limit_up_no_buy")).toBe(true);
    }
    await page.screenshot({ path: test.info().outputPath("chinext-reform.png"), fullPage: true });
	await page.getByRole("button", { name: "导出报告", exact: true }).click();
	const downloadPromise = page.waitForEvent("download");
	await page.getByRole("button", { name: "下载 JSON", exact: true }).press("Enter");
	const path = await (await downloadPromise).path();
	if (!path) throw new Error("export missing");
	const exported = JSON.parse(await readFile(path, "utf8"));
	expect(exported.report.feeStatement.finalCash).toBe(report.fee_statement.final_cash);
	expect(exported.report.feeStatement.fills.length).toBe(fills.length);
	expect((await (await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${originalId}/request`)).json()).data).toEqual(original);
	const accessibility = await new AxeBuilder({ page }).analyze();
	expect(accessibility.violations.filter((v) => ["critical", "serious"].includes(v.impact ?? ""))).toEqual([]);
	expect(errors).toEqual([]);
});

for (const kind of ["market_on_close", "market"]) {
	test(`ChiNext IPO ${kind} obeys the fifth/sixth session across the National Day closure`, async ({ page }) => {
		const id = await submit(page, "2020-10-09", "2020-10-14", kind);
		await expect(page.getByTestId("backtest-detail-meta")).toContainText("completed", { timeout: 60000 });
		await page.reload();
		await page.locator("summary").filter({ hasText: "请求与冻结来源" }).press("Enter");
		const dates = page.getByLabel("逐日参与日期");
		await dates.selectOption("2020-10-12");
		await expect(page.getByRole("row", { name: /300896.SZ.*无日涨跌幅限制.*不接受市价申报/ })).toBeVisible();
		await dates.selectOption("2020-10-13");
		await expect(page.getByRole("row", { name: /300896.SZ.*涨跌幅 20%/ })).toBeVisible();
		const report = (await (await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${id}/report`)).json()).data;
		const audit = (await (await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${id}/audit`)).json()).data;
		if (kind === "market_on_close") {
			expect(report.fee_statement.fills.some((fill: { instrument_id: number; trade_date: string }) => fill.instrument_id === 1003003 && fill.trade_date === "2020-10-09")).toBe(true);
		} else {
			expect(audit.some((row: { instrument_id: number; payload: { reason?: string } }) => row.instrument_id === 1003003 && row.payload.reason === "unsupported_order_type")).toBe(true);
		}
		expect(audit.some((row: { trade_date: string; instrument_id: number; payload: { reason?: string } }) => row.trade_date === "2020-10-13" && row.instrument_id === 1003003 && row.payload.reason === "limit_up_no_buy")).toBe(true);
	});
}

test("oversized ChiNext submissions retain their rejection instead of becoming partial fills", async ({ page }) => {
	const id = await submit(page, "2020-10-09", "2020-10-12", "market_on_close", "100000000");
	await expect(page.getByTestId("backtest-detail-meta")).toContainText("completed", { timeout: 60000 });
	await page.reload();
	const audit = (await (await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${id}/audit`)).json()).data;
	expect(audit.some((row: { payload: { reason?: string; final_quantity?: number } }) => row.payload.reason === "order_quantity_exceeds_dated_maximum" && row.payload.final_quantity === 0)).toBe(true);
	await page.getByRole("tab", { name: "审计证据" }).click();
	const rejection = page.locator("details").filter({ hasText: "order_quantity_exceeds_dated_maximum" }).first();
	await rejection.locator("summary").focus();
	await page.keyboard.press("Enter");
	await expect(rejection.locator("pre")).toBeVisible();
});
