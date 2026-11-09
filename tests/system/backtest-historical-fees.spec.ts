import { readFile } from "node:fs/promises";
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const webOrigin = process.env["DITTO_SYSTEM_WEB_ORIGIN"];
const apiOrigin = process.env["DITTO_SYSTEM_API_ORIGIN"];
if (!webOrigin || !apiOrigin) throw new Error("isolated system origins are required");

for (const [start, end] of [
	["2014-01-13", "2014-01-17"],
	["2015-07-29", "2015-08-05"],
	["2022-04-27", "2022-05-06"],
	["2023-08-24", "2023-08-29"],
] as const) {
	test(`ordinary fee bills reconcile across ${start}..${end}, reload and export`, async ({ page }) => {
		const errors: string[] = [];
		page.on("pageerror", (error) => errors.push(error.message));
		await page.goto(`${webOrigin}/research/strategies/historical_fees_fixture`);
		await page.getByRole("button", { name: "提交回测", exact: true }).click();
		const form = page.getByRole("dialog", { name: "提交回测" });
		await form.getByLabel("历史请求用途").selectOption("reconstruction");
		await form.getByLabel("策略版本").selectOption("1");
		await form.getByLabel("开始日期").fill(start);
		await form.getByLabel("结束日期").fill(end);
		await form.getByLabel("初始资金（元）").fill("250000");
		await form.getByRole("button", { name: "提交回测", exact: true }).focus();
		await page.keyboard.press("Enter");
		const link = form.getByRole("link", { name: "查看本次回测" });
		await expect(link).toBeVisible();
		const runId = (await link.getAttribute("href"))?.split("/").at(-1);
		await link.click();
		await expect(page.getByTestId("backtest-detail-meta")).toContainText("completed", { timeout: 60000 });
		const report = (await (await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${runId}/report`)).json()).data;
		expect(report.fee_statement).toBeTruthy();
		const statement = report.fee_statement;
		expect(statement.fills.length).toBeGreaterThan(2);
		expect(report.aggregated_trade_stats).not.toHaveProperty("profit_factor");
		expect(report.aggregated_trade_stats).not.toHaveProperty("avg_win_loss_ratio");
		let cash = 250000;
		let fees = 0;
		const directions = new Set<string>();
		for (const fill of statement.fills) {
			const amount = fill.quantity * fill.price;
			expect(fill.price).toBe(10);
			const commission = Math.max(5, amount * 0.0003);
			const stamp = fill.direction === "sell" ? amount * (fill.trade_date < "2023-08-28" ? 0.001 : 0.0005) : 0;
			const transfer =
				fill.trade_date < "2015-08-01"
					? fill.instrument_id === 1002001
						? fill.quantity * 0.0003
						: amount * 0.0000255
					: amount * (fill.trade_date < "2022-04-29" ? 0.00002 : 0.00001);
			expect(fill.commission).toBeCloseTo(commission, 8);
			expect(fill.stamp_duty).toBeCloseTo(stamp, 8);
			expect(fill.transfer_fee).toBeCloseTo(transfer, 8);
			expect(fill.total_fee).toBeCloseTo(commission + stamp + transfer, 8);
			cash += (fill.direction === "buy" ? -amount : amount) - fill.total_fee;
			fees += fill.total_fee;
			directions.add(`${fill.symbol}:${fill.direction}`);
		}
		expect(directions.size).toBe(4);
		expect(statement.final_cash).toBeCloseTo(cash, 8);
		expect(report.alpha_stats.total_fees).toBeCloseTo(fees, 8);
		expect(report.final_nav).toBeCloseTo(250000 - fees, 8);
		await page.reload();
		await page.getByRole("tab", { name: "成交", exact: true }).click();
		const disclosure = page.locator("summary").filter({ hasText: "逐笔费用账单" });
		await disclosure.focus();
		await page.keyboard.press("Enter");
		await expect(disclosure).toBeFocused();
		await expect(page.getByRole("table", { name: "逐笔费用账单" })).toBeVisible();
		const scroll = page.getByRole("region", { name: "逐笔费用账单滚动区域" });
		await scroll.focus();
		await expect(scroll).toBeFocused();
		await page.keyboard.press("ArrowRight");
		await expect(page.getByText(/研究佣金.*中登过户费/)).toBeVisible();
		await page.getByRole("button", { name: "导出报告", exact: true }).click();
		const downloadPromise = page.waitForEvent("download");
		await page.getByRole("button", { name: "下载 JSON", exact: true }).press("Enter");
		const downloaded = await downloadPromise;
		const path = await downloaded.path();
		if (!path) throw new Error("export file missing");
		const exported = JSON.parse(await readFile(path, "utf8"));
		expect(exported.report.feeStatement.finalCash).toBe(statement.final_cash);
		expect(exported.report.feeStatement.fills.map((fill: { totalFee: number }) => fill.totalFee)).toEqual(
			statement.fills.map((fill: { total_fee: number }) => fill.total_fee),
		);
		expect(
			exported.report.feeStatement.fills.map((fill: { schedule: { asOfDate: string } }) => fill.schedule.asOfDate),
		).toEqual(statement.fills.map((fill: { schedule: { as_of_date: string } }) => fill.schedule.as_of_date));
		expect(exported.report.finalNav).toBe(report.final_nav);
		expect((await (await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${runId}/report`)).json()).data).toEqual(
			report,
		);
		const accessibility = await new AxeBuilder({ page }).analyze();
		expect(accessibility.violations.filter((v) => ["critical", "serious"].includes(v.impact ?? ""))).toEqual([]);
		expect(errors).toEqual([]);
	});
}
