import { readFile } from "node:fs/promises";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const apiOrigin = process.env["DITTO_SYSTEM_API_ORIGIN"];
const webOrigin = process.env["DITTO_SYSTEM_WEB_ORIGIN"];
if (!webOrigin || !apiOrigin) throw new Error("isolated system origins are required");
const CONVERSION_ID = "2008941:2022-07-05";

async function submit(page: Page, cash = "1950000") {
	await page.goto(`${webOrigin}/research/strategies/etf_share_conversions_fixture`);
	await page.getByRole("button", { name: "提交回测", exact: true }).click();
	const form = page.getByRole("dialog", { name: "提交回测" });
	await form.getByLabel("历史请求用途").selectOption("reconstruction");
	await form.getByLabel("策略版本").selectOption("1");
	await form.getByLabel("开始日期").fill("2022-07-01");
	await form.getByLabel("结束日期").fill("2022-07-08");
	await form.getByLabel("初始资金（元）").fill(cash);
	await form.getByRole("button", { name: "提交回测", exact: true }).focus();
	await page.keyboard.press("Enter");
	const link = form.getByRole("link", { name: "查看本次回测" });
	await expect(link).toBeVisible();
	const id = (await link.getAttribute("href"))?.split("/").at(-1);
	await link.click();
	return id;
}

async function saved(page: Page, id: string | undefined, resource: string) {
	const response = await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${id}/${resource}`);
	expect(response.ok()).toBe(true);
	return (await response.json()).data;
}

type Fill = {
	trade_date: string;
	instrument_id: number;
	direction: "buy" | "sell";
	quantity: number;
	price: number;
	total_fee: number;
};
type Entry = { event_id: string; day: string; kind: string; amount: number; quantity: number };

test("declared split rescales holdings, halts without fills and resumes at the new price", async ({
	page,
}) => {
	test.setTimeout(120000);
	// 1. Without the retained declaration the split factor jump refuses to run.
	const failedId = await submit(page);
	await expect(page.getByTestId("backtest-detail-meta")).toContainText("failed", { timeout: 60000 });
	await expect(
		page.getByText(/corporate action requires cash\/share accounting.*2008941.*2022-07-05/).first(),
	).toBeVisible();
	await page.screenshot({ path: test.info().outputPath("conversion-refused.png"), fullPage: true });
	// 2. Retain the maintainer declaration and rerun the identical request.
	expect(
		(await page.request.post(`${apiOrigin}/system-fixture/share-conversions/repair`)).ok(),
	).toBe(true);
	await page.reload();
	const requestDisclosure = page.locator("summary").filter({ hasText: "请求与冻结来源" });
	await expect(requestDisclosure).toBeVisible();
	if ((await requestDisclosure.locator("..").getAttribute("open")) === null)
		await requestDisclosure.press("Enter");
	await page.getByRole("button", { name: "补证后沿原配置新建运行" }).press("Enter");
	const link = page.getByRole("link", { name: "打开补证后的新运行" });
	await expect(link).toBeVisible();
	const id = (await link.getAttribute("href"))?.split("/").at(-1);
	expect(id).not.toBe(failedId);
	await link.click();
	await expect(page.getByTestId("backtest-detail-meta")).toContainText("completed", {
		timeout: 60000,
	});
	// Recharts measures its container then animates the line in (~1.5s);
	// under load both lag the status flip, so settle before the evidence shot.
	await page.waitForTimeout(3000);
	await page.screenshot({ path: test.info().outputPath("conversion-completed.png"), fullPage: true });

	const request = await saved(page, id, "request");
	expect(
		request.sources.some(
			(s: { dataset: string; source: string; verified: boolean }) =>
				s.dataset === "etf_share_conversions" && s.source === "config" && s.verified,
		),
	).toBe(true);
	const report = await saved(page, id, "report");
	const statement = report.dividend_statement;
	expect(statement.conversions).toHaveLength(1);
	expect(statement.conversions[0]).toMatchObject({
		event_id: CONVERSION_ID,
		instrument_id: 2008941,
		source_ticker: "159941.SZ",
		announcement_date: "2022-06-29",
		effective_date: "2022-07-05",
		ratio: 4,
	});
	expect(statement.entries.filter((e: Entry) => e.kind === "share_conversion")).toHaveLength(1);

	// 3. Hand-recompute shares, cost and NAV from the actual fills and entries.
	const fills: Fill[] = report.fee_statement.fills;
	const etf = 2008941;
	const buy = fills.find((fill) => fill.instrument_id === etf && fill.direction === "buy");
	if (!buy) throw new Error("expected a pre-split purchase fill");
	expect(buy).toMatchObject({ trade_date: "2022-07-01", price: 2.384 });
	const entry = statement.entries.find(
		(e: Entry) => e.kind === "share_conversion" && e.event_id === CONVERSION_ID,
	);
	expect(entry.day).toBe("2022-07-05");
	expect(entry.quantity).toBe(buy.quantity * 3);
	let cash = 1_950_000;
	const positions = new Map<number, number>();
	const conversionEntry = statement.entries.find(
		(e: Entry) => e.kind === "share_conversion",
	);
	for (const day of statement.balances) {
		for (const fill of fills.filter((f) => f.trade_date === day.trade_date)) {
			const signed = fill.direction === "buy" ? fill.quantity : -fill.quantity;
			positions.set(fill.instrument_id, (positions.get(fill.instrument_id) ?? 0) + signed);
			cash -= signed * fill.price + fill.total_fee;
		}
		if (conversionEntry && conversionEntry.day === day.trade_date) {
			const converted = statement.conversions[0].instrument_id;
			positions.set(converted, (positions.get(converted) ?? 0) + conversionEntry.quantity);
		}
		expect(day.cash).toBeCloseTo(cash, 5);
		expect(day.nav).toBeCloseTo(day.cash + day.receivable + day.market_value - day.tax_payable, 5);
		for (const position of day.positions) {
			expect(position.quantity).toBe(positions.get(position.instrument_id));
			expect(position.available_quantity).toBeLessThanOrEqual(position.quantity);
			if (day.trade_date === "2022-07-04") {
				expect(position.quantity).toBe(buy.quantity);
				expect(position.average_cost).toBeCloseTo(2.384, 6);
				expect(position.quantity * position.average_cost).toBeCloseTo(
					buy.quantity * buy.price,
					5,
				);
			}
			if (day.trade_date >= "2022-07-05") {
				// Converted shares carry one quarter of the per-share cost and
				// re-spread the remaining total cost exactly.
				expect(position.average_cost).toBeCloseTo(2.384 / 4, 6);
				expect(position.total_cost).toBeCloseTo(
					position.quantity * (2.384 / 4),
					5,
				);
			}
		}
	}
	const splitDay = statement.balances.find(
		(row: { trade_date: string }) => row.trade_date === "2022-07-05",
	);
	if (!splitDay) throw new Error("expected a split-day balance row");
	const splitPosition = splitDay.positions.find(
		(p: { instrument_id: number }) => p.instrument_id === etf,
	);
	if (!splitPosition) throw new Error("expected a split-day position");
	// Same-session sells aside, the split multiplies holdings by exactly four
	// while total cost is preserved.
	const soldOnSplit = fills
		.filter((f) => f.trade_date === "2022-07-05" && f.instrument_id === etf)
		.reduce((sum, f) => sum + f.quantity, 0);
	expect(splitPosition.quantity).toBe(buy.quantity * 4 - soldOnSplit);
	expect(splitPosition.market_value).toBeCloseTo(splitPosition.quantity * 0.6, 5);

	// 4. The zero-volume session rejects without fills and resumes at 0.61.
	const audit = await saved(page, id, "audit");
	expect(
		audit.some(
			(r: { trade_date: string; instrument_id: number; payload: { reason?: string } }) =>
				r.trade_date === "2022-07-06" &&
				r.instrument_id === etf &&
				r.payload.reason === "zero_volume",
		),
	).toBe(true);
	expect(
		fills.some((f) => f.instrument_id === etf && f.trade_date === "2022-07-06"),
	).toBe(false);
	const resumed = fills.filter(
		(f) => f.instrument_id === etf && f.trade_date >= "2022-07-07",
	);
	expect(resumed.length).toBeGreaterThan(0);
	for (const fill of resumed) expect(fill.price).toBe(0.61);

	// 5. Resubmitting the identical request never converts twice.
	const trigger = await page.request.post(`${apiOrigin}/api/v1/backtests/runs`, {
		data: {
			strategy_id: "etf_share_conversions_fixture",
			strategy_version: 1,
			start_date: "2022-07-01",
			end_date: "2022-07-08",
			initial_cash: 1_950_000,
			historical_reconstruction: true,
		},
	});
	expect(trigger.ok()).toBe(true);
	const repeatId = (await trigger.json()).data.run_id;
	for (let i = 0; i < 40; i += 1) {
		const status = (
			await (await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${repeatId}`)).json()
		).data.status;
		if (status === "completed" || status === "failed") break;
		await page.waitForTimeout(2000);
	}
	const repeat = await saved(page, repeatId, "report");
	const repeatEntry = repeat.dividend_statement.entries.find(
		(e: Entry) => e.kind === "share_conversion",
	);
	expect(repeatEntry.quantity).toBe(entry.quantity);
	const repeatSplit = repeat.dividend_statement.balances.find(
		(row: { trade_date: string }) => row.trade_date === "2022-07-05",
	);
	if (!repeatSplit) throw new Error("expected a repeat split-day balance row");
	const repeatPosition = repeatSplit.positions.find(
		(p: { instrument_id: number }) => p.instrument_id === etf,
	);
	if (!repeatPosition) throw new Error("expected a repeat split-day position");
	expect(repeatPosition.quantity).toBe(splitPosition.quantity);

	// 6. Reopen the saved ledger, verify keyboard access and export.
	await page.goto(`${webOrigin}/research/backtests/${id}`);
	await page.getByRole("tab", { name: "成交", exact: true }).click();
	const disclosure = page.locator("summary").filter({ hasText: "分红与送转账本" });
	await disclosure.focus();
	await page.keyboard.press("Enter");
	await expect(disclosure).toBeFocused();
	await expect(page.getByRole("table", { name: "分红每日对账" })).toBeVisible();
	await expect(
		page.getByText(/159941\.SZ · 份额折算 1 折 4 · 生效 2022-07-05/),
	).toBeVisible();
	await expect(page.getByText(/份额折算（数量重标定）/).first()).toBeVisible();
	await page.screenshot({ path: test.info().outputPath("conversion-ledger.png"), fullPage: true });
	await page.getByRole("button", { name: "导出报告", exact: true }).click();
	const download = page.waitForEvent("download");
	await page.getByRole("button", { name: "下载 JSON", exact: true }).press("Enter");
	const path = await (await download).path();
	if (!path) throw new Error("missing exported report");
	const exported = JSON.parse(await readFile(path, "utf8"));
	expect(exported.report.dividendStatement.conversions[0].eventId).toBe(CONVERSION_ID);
	expect(
		(await (
			await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${id}/report`)
		).json()).data,
	).toEqual(report);
	expect(
		(await (
			await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${failedId}`)
		).json()).data.status,
	).toBe("failed");
	const accessibility = await new AxeBuilder({ page }).analyze();
	expect(
		accessibility.violations.filter((v) => ["critical", "serious"].includes(v.impact ?? "")),
	).toEqual([]);
});
