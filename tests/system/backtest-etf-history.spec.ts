import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const webOrigin = process.env["DITTO_SYSTEM_WEB_ORIGIN"];
const apiOrigin = process.env["DITTO_SYSTEM_API_ORIGIN"];
if (!webOrigin || !apiOrigin) throw new Error("isolated system origins are required");

async function submit(page: Page, kind = "market", cash = "1000000") {
	await page.goto(`${webOrigin}/research/strategies/etf_history_${kind}_fixture`);
	await page.getByRole("button", { name: "提交回测", exact: true }).click();
	const form = page.getByRole("dialog", { name: "提交回测" });
	await form.getByLabel("历史请求用途").selectOption("reconstruction");
	await form.getByLabel("策略版本").selectOption("1");
	await form.getByLabel("开始日期").fill("2020-08-21");
	await form.getByLabel("结束日期").fill("2020-08-26");
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

test("six ETF categories refuse a missing historical declaration, recover and reread exact dated fills", async ({ page }) => {
	const oldId = await submit(page);
	await expect(page.getByTestId("backtest-detail-meta")).toContainText("failed", { timeout: 60000 });
	await page.reload();
	await expect(page.getByText(/missing\/ambiguous ETF rule.*2008006.*2020-08-21.*trading_category/).first()).toBeVisible();
	const old = await saved(page, oldId, "request");
	expect((await page.request.post(`${apiOrigin}/system-fixture/etf-history/repair`)).ok()).toBe(true);
	await page.getByRole("button", { name: "补证后沿原配置新建运行" }).focus();
	await page.keyboard.press("Enter");
	const link = page.getByRole("link", { name: "打开补证后的新运行" });
	await expect(link).toBeVisible();
	const id = (await link.getAttribute("href"))?.split("/").at(-1);
	expect(id).not.toBe(oldId);
	await link.click();
	await expect(page.getByTestId("backtest-detail-meta")).toContainText("completed", { timeout: 60000 });
	await page.reload();
	await page.locator("summary").filter({ hasText: "请求与冻结来源" }).click();
	const dates = page.getByLabel("逐日参与日期");
	await dates.focus();
	await dates.selectOption("2020-08-21");
	await expect(dates).toBeFocused();
	await expect(page.getByRole("row", { name: /159915.SZ.*股票 ETF.*涨跌幅 10%.*100 份.*0.001 元.*T\+1/ })).toBeVisible();
	await dates.selectOption("2020-08-24");
	await expect(page.getByRole("row", { name: /159915.SZ.*涨跌幅 20%/ })).toBeVisible();
	for (const category of ["债券 ETF", "黄金 ETF", "跨境 ETF", "货币 ETF", "商品期货 ETF"]) {
		await expect(page.getByRole("row", { name: new RegExp(`${category}.*T\\+0`) })).toBeVisible();
	}
	const request = await saved(page, id, "request");
	expect(request.members).toEqual(old.members);
	expect(request.start_date).toBe("2020-08-21");
	expect(request.end_date).toBe("2020-08-26");
	expect(request.sources.some((s: { dataset: string; source: string; verified: boolean }) => s.dataset === "etf_reference" && s.source === "config" && s.verified)).toBe(true);
	const report = await saved(page, id, "report");
	const fills = report.fee_statement.fills;
	for (let iid = 2008001; iid <= 2008006; iid++) {
		expect(fills.some((f: { instrument_id: number; quantity: number }) => f.instrument_id === iid && f.quantity > 0)).toBe(true);
	}
	expect(fills.every((f: { stamp_duty: number; transfer_fee: number }) => f.stamp_duty === 0 && f.transfer_fee === 0)).toBe(true);
	expect(await saved(page, oldId, "request")).toEqual(old);
	const accessibility = await new AxeBuilder({ page }).analyze();
	expect(accessibility.violations.filter((v) => ["critical", "serious"].includes(v.impact ?? ""))).toEqual([]);
});

test("ETF historical order ceilings and exchange close sessions reach saved rejection evidence", async ({ page }) => {
	expect((await page.request.post(`${apiOrigin}/system-fixture/etf-history/repair`)).ok()).toBe(true);
	const huge = await submit(page, "market", "10000000000");
	await expect(page.getByTestId("backtest-detail-meta")).toContainText("completed", { timeout: 60000 });
	const rejected = await saved(page, huge, "audit");
	for (let iid = 2008001; iid <= 2008006; iid++) {
		expect(rejected.some((r: { instrument_id: number; payload: { reason?: string } }) => r.instrument_id === iid && r.payload.reason === "order_quantity_exceeds_dated_maximum")).toBe(true);
	}
	const close = await submit(page, "market_on_close");
	await expect(page.getByTestId("backtest-detail-meta")).toContainText("completed", { timeout: 60000 });
	await page.reload();
	const audit = await saved(page, close, "audit");
	for (const iid of [2008002, 2008003, 2008004, 2008005]) {
		expect(audit.some((r: { instrument_id: number; payload: { reason?: string } }) => r.instrument_id === iid && r.payload.reason === "unsupported_order_type")).toBe(true);
	}
	const report = await saved(page, close, "report");
	for (const iid of [2008001, 2008006]) {
		expect(report.fee_statement.fills.some((f: { instrument_id: number }) => f.instrument_id === iid)).toBe(true);
	}
	await page.getByRole("tab", { name: "审计证据" }).click();
	const reason = page.locator("details").filter({ hasText: "unsupported_order_type" }).first();
	await reason.locator("summary").focus();
	await page.keyboard.press("Enter");
	await expect(reason.locator("pre")).toBeVisible();
});
