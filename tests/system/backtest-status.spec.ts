import { readFile } from "node:fs/promises";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const webOrigin = process.env["DITTO_SYSTEM_WEB_ORIGIN"];
const apiOrigin = process.env["DITTO_SYSTEM_API_ORIGIN"];
if (!webOrigin || !apiOrigin) throw new Error("isolated system origins are required");

async function retry(page: Page) {
    await page.getByRole("button", { name: "补证后沿原配置新建运行" }).focus();
    await page.keyboard.press("Enter");
    const link = page.getByRole("link", { name: "打开补证后的新运行" });
    await expect(link).toBeVisible();
    const id = (await link.getAttribute("href"))?.split("/").at(-1);
    if (!id) throw new Error("missing recovery identity");
    await link.click();
    return id;
}

async function request(page: Page, id: string) {
    return (await (await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${id}/request`)).json()).data;
}

test("unknown state and genuine missing quote retain failures; repair runs preserve halted holdings and ST/zero-turnover distinctions", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto(`${webOrigin}/research/strategies/status_fixture`);
    await page.getByRole("button", { name: "提交回测", exact: true }).click();
    const form = page.getByRole("dialog", { name: "提交回测" });
    await form.getByLabel("历史请求用途").selectOption("reconstruction");
    await form.getByLabel("策略版本").selectOption("1");
    await form.getByLabel("开始日期").fill("2014-10-20");
    await form.getByLabel("结束日期").fill("2014-10-24");
    await form.getByLabel("初始资金（元）").fill("1000000");
    await form.getByRole("button", { name: "提交回测", exact: true }).focus();
    await page.keyboard.press("Enter");
    const link = form.getByRole("link", { name: "查看本次回测" });
    await expect(link).toBeVisible();
    const originalId = (await link.getAttribute("href"))?.split("/").at(-1);
    if (!originalId) throw new Error("missing saved request");
    await link.click();
    await expect(page.getByTestId("backtest-detail-meta")).toContainText("failed", { timeout: 60000 });
    await page.reload();
    await expect(page.getByText(/unknown stock status.*1007561.*2014/).first()).toBeVisible();
    const original = await request(page, originalId);
    expect((await page.request.post(`${apiOrigin}/system-fixture/status/repair-status`)).ok()).toBe(true);
    const missingId = await retry(page);
    expect(missingId).not.toBe(originalId);
    await expect(page.getByTestId("backtest-detail-meta")).toContainText("failed", { timeout: 60000 });
    await page.reload();
    await expect(page.getByText(/missing backtest member\/date inputs/).first()).toBeVisible();
    const missing = await request(page, missingId);
    expect((await page.request.post(`${apiOrigin}/system-fixture/status/repair-quote`)).ok()).toBe(true);
    const id = await retry(page);
    expect(id).not.toBe(missingId);
    await expect(page.getByTestId("backtest-detail-meta")).toContainText("completed", { timeout: 60000 });
    await page.reload();
    await page.locator("summary").filter({ hasText: "请求与冻结来源" }).press("Enter");
    const dates = page.getByLabel("逐日参与日期");
    await dates.selectOption("2014-10-21");
    await expect(page.getByRole("row", { name: /000001.SZ.*已确认停牌.*停牌估值 10(?:\.0)? 元.*2014-10-20/ })).toBeVisible();
    await expect(page.getByRole("row", { name: /002001.SZ.*涨跌幅 5%.*ST 风险警示/ })).toBeVisible();
    await dates.focus();
    await dates.selectOption("2014-10-23");
    await expect(dates).toBeFocused();
    await expect(page.getByRole("row", { name: /002001.SZ.*零成交/ })).toBeVisible();
    const report = (await (await page.request.get(`${apiOrigin}/api/v1/backtests/runs/${id}/report`)).json()).data;
    const fills = report.fee_statement.fills;
    expect(fills.some((fill: { instrument_id: number; trade_date: string; direction: string }) => fill.instrument_id === 1007561 && fill.trade_date === "2014-10-20" && fill.direction === "buy")).toBe(true);
    expect(fills.some((fill: { instrument_id: number; trade_date: string }) => fill.instrument_id === 1007561 && ["2014-10-21", "2014-10-22"].includes(fill.trade_date))).toBe(false);
    expect(fills.some((fill: { instrument_id: number; trade_date: string; direction: string }) => fill.instrument_id === 1007561 && fill.trade_date >= "2014-10-23" && fill.direction === "sell")).toBe(true);
    expect(fills.some((fill: { instrument_id: number; trade_date: string }) => fill.instrument_id === 1007562 && fill.trade_date === "2014-10-23")).toBe(false);
    await page.getByRole("button", { name: "导出报告", exact: true }).click();
    const downloaded = page.waitForEvent("download");
    await page.getByRole("button", { name: "下载 JSON", exact: true }).press("Enter");
    const path = await (await downloaded).path();
    if (!path) throw new Error("export missing");
    const exported = JSON.parse(await readFile(path, "utf8"));
    expect(exported.request.runId).toBe(id);
    expect(exported.request.participation).toEqual((await request(page, id)).participation.map((row: { instrument_id: number; symbol: string; trade_date: string; status: string; warmup_available: number; warmup_required: number; evaluated: boolean; execution_rule: string | null }) => ({
        instrumentId: row.instrument_id, symbol: row.symbol, tradeDate: row.trade_date, status: row.status,
        warmupAvailable: row.warmup_available, warmupRequired: row.warmup_required,
        evaluated: row.evaluated, executionRule: row.execution_rule,
    })));
    expect(await request(page, originalId)).toEqual(original);
    expect(await request(page, missingId)).toEqual(missing);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("button", { name: "导出报告", exact: true })).toBeFocused();
    expect((await new AxeBuilder({ page }).analyze()).violations.filter(v => ["critical", "serious"].includes(v.impact ?? ""))).toEqual([]);
    expect(errors).toEqual([]);
});
