import { readFile } from "node:fs/promises";
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const apiOrigin = process.env["DITTO_SYSTEM_API_ORIGIN"];

test("share distribution facts recover through the UI, reconcile, reopen and export", async ({
	page,
}) => {
	test.setTimeout(90000);
	await page.goto("/research/strategies/historical_fees_fixture");
	await page.getByRole("button", { name: "提交回测", exact: true }).click();
	const form = page.getByRole("dialog", { name: "提交回测" });
	await form.getByLabel("历史请求用途").selectOption("reconstruction");
	await form.getByLabel("策略版本").selectOption("1");
	await form.getByLabel("开始日期").fill("2014-01-20");
	await form.getByLabel("结束日期").fill("2014-01-29");
	await form.getByLabel("初始资金（元）").fill("250000");
	await form
		.getByRole("button", { name: "提交回测", exact: true })
		.press("Enter");
	const link = form.getByRole("link", { name: "查看本次回测" });
	await expect(link).toBeVisible();
	await link.click();
	await expect(page.getByTestId("backtest-detail-meta")).toContainText(
		"failed",
		{ timeout: 60000 },
	);
	const originalId = page.url().split("/").at(-1);
	await expect(
		page
			.getByText(/share accounting requires listing and issuer tax evidence/)
			.first(),
	).toBeVisible();
	await page.request.post(`${apiOrigin}/system-fixture/distributions/repair`);
	await page.reload();
	const requestDisclosure = page
		.locator("summary")
		.filter({ hasText: "请求与冻结来源" });
	await expect(requestDisclosure).toBeVisible();
	if ((await requestDisclosure.locator("..").getAttribute("open")) === null)
		await requestDisclosure.press("Enter");
	await expect(
		page.getByRole("button", { name: "补证后沿原配置新建运行" }),
	).toBeVisible();
	await page
		.getByRole("button", { name: "补证后沿原配置新建运行" })
		.press("Enter");
	await page.getByRole("link", { name: "打开补证后的新运行" }).click();
	await expect(page.getByTestId("backtest-detail-meta")).toContainText(
		"completed",
		{ timeout: 60000 },
	);
	const runId = page.url().split("/").at(-1);
	expect(runId).not.toBe(originalId);
	const report = (
		await (
			await page.request.get(
				`${apiOrigin}/api/v1/backtests/runs/${runId}/report`,
			)
		).json()
	).data;
	const statement = report.dividend_statement;
	expect(statement.events).toHaveLength(2);
	const trades = (
		await (
			await page.request.get(
				`${apiOrigin}/api/v1/backtests/runs/${runId}/trades`,
			)
		).json()
	).data;
	const adjusted = trades.filter(
		(trade: { entry_date: string; exit_date: string }) =>
			trade.entry_date < "2014-01-22" && trade.exit_date >= "2014-01-22",
	);
	expect(adjusted.length).toBeGreaterThan(0);
	for (const trade of adjusted)
		expect(trade.entry_price).toBeCloseTo(10 / 1.5, 6);
	let cash = 250000;
	const positions = new Map<number, number>();
	for (const day of statement.balances) {
		for (const entry of statement.entries.filter(
			(e: { day: string; kind: string }) =>
				e.day === day.trade_date && e.kind === "share_credit",
		)) {
			const event = statement.events.find(
				(e: { event_id: string }) => e.event_id === entry.event_id,
			);
			positions.set(
				event.instrument_id,
				(positions.get(event.instrument_id) ?? 0) + entry.quantity,
			);
			expect(entry.quantity).toBe(event.registered_quantity / 2);
		}
		for (const fill of report.fee_statement.fills.filter(
			(fill: { trade_date: string }) => fill.trade_date === day.trade_date,
		)) {
			const signed = fill.direction === "buy" ? fill.quantity : -fill.quantity;
			positions.set(
				fill.instrument_id,
				(positions.get(fill.instrument_id) ?? 0) + signed,
			);
			cash -= signed * fill.price + fill.total_fee;
		}
		for (const entry of statement.entries.filter(
			(entry: { day: string; kind: string }) =>
				entry.day === day.trade_date &&
				["cash_payment", "tax_payment", "share_tax_payment"].includes(
					entry.kind,
				),
		))
			cash += entry.amount;
		expect(day.cash).toBeCloseTo(cash, 6);
		expect(day.nav).toBeCloseTo(
			cash + day.receivable + day.market_value - day.tax_payable,
			6,
		);
		for (const position of day.positions) {
			expect(position.quantity).toBe(positions.get(position.instrument_id));
			expect(position.available_quantity).toBeLessThanOrEqual(
				position.quantity,
			);
			expect(position.locked_quantity).toBe(
				position.quantity - position.available_quantity,
			);
			if (day.trade_date >= "2014-01-22" && day.trade_date < "2014-01-24") {
				const event = statement.events.find(
					(e: { instrument_id: number }) =>
						e.instrument_id === position.instrument_id,
				);
				expect(position.locked_quantity).toBeGreaterThanOrEqual(
					event.registered_quantity / 2,
				);
			}
		}
		if (day.trade_date === "2014-01-21")
			for (const event of statement.events)
				expect(event.registered_quantity).toBe(
					positions.get(event.instrument_id) ?? 0,
				);
	}
	const registered = statement.events.reduce(
		(sum: number, event: { registered_quantity: number }) =>
			sum + event.registered_quantity,
		0,
	);
	expect(registered).toBeGreaterThan(0);
	expect(
		statement.balances.find(
			(row: { trade_date: string }) => row.trade_date === "2014-01-22",
		).receivable,
	).toBeCloseTo(registered * 0.945, 6);
	expect(
		statement.entries
			.filter((entry: { kind: string }) => entry.kind === "cash_payment")
			.reduce(
				(sum: number, entry: { amount: number }) => sum + entry.amount,
				0,
			),
	).toBeCloseTo(registered * 0.95, 6);
	expect(
		statement.entries
			.filter((e: { kind: string }) => e.kind === "share_release")
			.every((e: { day: string }) => e.day === "2014-01-24"),
	).toBe(true);
	const credited = statement.entries.filter(
		(e: { kind: string }) => e.kind === "share_credit",
	);
	expect(credited.length).toBeGreaterThan(0);
	expect(
		new Set(credited.map((e: { event_id: string }) => e.event_id)).size,
	).toBe(credited.length);
	await page.reload();
	await page.getByRole("tab", { name: "成交", exact: true }).click();
	const disclosure = page
		.locator("summary")
		.filter({ hasText: "股票分红与送转账本" });
	await disclosure.focus();
	await page.keyboard.press("Enter");
	await expect(disclosure).toBeFocused();
	await expect(page.getByRole("table", { name: "分红每日对账" })).toBeVisible();
	await expect(
		page.getByRole("table", { name: "送转每日份额与成本" }),
	).toBeVisible();
	await page.getByRole("region", { name: "分红每日对账滚动区域" }).focus();
	await page.keyboard.press("ArrowRight");
	await page.getByRole("button", { name: "导出报告", exact: true }).click();
	const download = page.waitForEvent("download");
	await page
		.getByRole("button", { name: "下载 JSON", exact: true })
		.press("Enter");
	const path = await (await download).path();
	if (!path) throw new Error("missing exported report");
	const exported = JSON.parse(await readFile(path, "utf8"));
	expect(exported.report.dividendStatement.events).toHaveLength(2);
	expect(
		(
			await (
				await page.request.get(
					`${apiOrigin}/api/v1/backtests/runs/${runId}/report`,
				)
			).json()
		).data,
	).toEqual(report);
	expect(
		(
			await (
				await page.request.get(
					`${apiOrigin}/api/v1/backtests/runs/${originalId}`,
				)
			).json()
		).data.status,
	).toBe("failed");
	const accessibility = await new AxeBuilder({ page }).analyze();
	expect(
		accessibility.violations.filter((violation) =>
			["critical", "serious"].includes(violation.impact ?? ""),
		),
	).toEqual([]);
});
