import { readFile } from "node:fs/promises";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const webOrigin = process.env["DITTO_SYSTEM_WEB_ORIGIN"];
const apiOrigin = process.env["DITTO_SYSTEM_API_ORIGIN"];
if (!webOrigin || !apiOrigin) throw new Error("isolated system origins are required");

async function submit(page: Page, start: string, end: string, kind = "market_on_close", cash = "250123") {
	await page.goto(`${webOrigin}/research/strategies/star_${kind}_fixture`);
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

test("STAR opening rejects stale bands, recovers with a new snapshot and exports dated execution", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const originalId = await submit(page, "2019-07-19", "2019-07-30");
    await expect(page.getByTestId("backtest-detail-meta")).toContainText("failed", { timeout: 60000 });
    await page.reload();
    await expect(page.getByText(/stock price band disagrees with dated rule/).first()).toBeVisible();
    const original = (await (await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${originalId}/request`)).json()).data;
    expect((await page.request.post(`${apiOrigin}/system-fixture/star/repair`)).ok()).toBe(true);
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
    await dates.selectOption("2019-07-19");
    await expect(page.getByRole("row", { name: /688001.SH.*尚未上市/ })).toBeVisible();
    await dates.selectOption("2019-07-26");
    await expect(page.getByRole("row", { name: /688001.SH.*star.*无日涨跌幅限制.*100000 股.*50000 股.*200 股起.*递增 1 股/ })).toBeVisible();
    await dates.focus();
    await dates.selectOption("2019-07-29");
    await expect(dates).toBeFocused();
    await expect(page.getByRole("row", { name: /688001.SH.*2019-07-29.*涨跌幅 20%.*0.01 元.*T\+1/ })).toBeVisible();
    const report = (await (await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${id}/report`)).json()).data;
    const fills = report.fee_statement.fills;
    expect(fills.some((fill: { quantity: number }) => fill.quantity >= 200 && fill.quantity % 100 !== 0)).toBe(true);
    expect(fills.every((fill: { trade_date: string }) => fill.trade_date >= "2019-07-22")).toBe(true);
    let cash = 250123;
    for (const fill of fills) {
        const amount = fill.price * fill.quantity;
        expect(fill.stamp_duty).toBeCloseTo(fill.direction === "sell" ? amount * 0.001 : 0, 8);
        expect(fill.transfer_fee).toBeCloseTo(amount * 0.00002, 8);
        cash += (fill.direction === "buy" ? -amount : amount) - fill.total_fee;
    }
    expect(report.fee_statement.final_cash).toBeCloseTo(cash, 8);
    const audit = (await (await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${id}/audit`)).json()).data;
    expect(audit.some((row: { trade_date: string; instrument_id: number; payload: { reason?: string } }) => row.trade_date === "2019-07-29" && row.instrument_id === 1006881 && row.payload.reason === "limit_up_no_buy")).toBe(true);
    await page.screenshot({ path: test.info().outputPath("star-opening.png"), fullPage: true });
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

test("STAR IPO also supports the daily market-order model before the sixth session", async ({ page }) => {
    const id = await submit(page, "2019-07-22", "2019-07-26", "market");
    await expect(page.getByTestId("backtest-detail-meta")).toContainText("completed", { timeout: 60000 });
    await page.reload();
    const report = (await (await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${id}/report`)).json()).data;
    expect(report.fee_statement.fills.length).toBeGreaterThan(0);
    expect(report.fee_statement.fills.every((fill: { quantity: number }) => fill.quantity <= 50000)).toBe(true);
});

for (const [cash, reason] of [["1000", "order_quantity_below_dated_minimum"], ["100000000", "order_quantity_exceeds_dated_maximum"]] as const) {
    test(`STAR invalid quantity persists ${reason} without fills`, async ({ page }) => {
        const id = await submit(page, "2019-07-23", "2019-07-26", "market_on_close", cash);
        await expect(page.getByTestId("backtest-detail-meta")).toContainText("completed", { timeout: 60000 });
        await page.reload();
        const audit = (await (await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${id}/audit`)).json()).data;
        expect(audit.some((row: { payload: { reason?: string; final_quantity?: number } }) => row.payload.reason === reason && row.payload.final_quantity === 0)).toBe(true);
        const report = (await (await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${id}/report`)).json()).data;
        expect(report.fee_statement.fills).toEqual([]);
        await page.getByRole("tab", { name: "审计证据" }).click();
        const rejection = page.locator("details").filter({ hasText: reason }).first();
        await rejection.locator("summary").focus();
        await page.keyboard.press("Enter");
        await expect(rejection.locator("pre")).toBeVisible();
    });
}
