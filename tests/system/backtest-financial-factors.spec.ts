import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const webOrigin = process.env["DITTO_SYSTEM_WEB_ORIGIN"];
const apiOrigin = process.env["DITTO_SYSTEM_API_ORIGIN"];
if (!webOrigin || !apiOrigin) throw new Error("isolated system origins are required");

const STOCK_A = 1_003_001;
const STOCK_B = 1_003_002;

// Representative run 2026-10-08..2026-11-06 (knowledge lag 1, close fills):
// - A announced before the window: roe 0.1 visible everywhere.
// - B announces 2026-10-13 (roe 0.2), is revised 2026-10-20 (roe 0.05) and
//   carries a future-dated sentinel disclosure (2026-12-31, roe 9.99).
// Expected sessions: B selectable first on 2026-10-14, revision visible on
// 2026-10-21; the sentinel must never flip selection back after 2026-10-21.
let originalRunId = "";
let originalTrades: unknown[] = [];
let originalRequest: unknown = null;
let originalReport: unknown = null;

async function submitHistoricalRun(page: import("@playwright/test").Page) {
	await page.goto(`${webOrigin}/research/strategies/financial_factors_fixture`);
	await page.getByRole("button", { name: "提交回测", exact: true }).click();
	const form = page.getByRole("dialog", { name: "提交回测" });
	await form.getByLabel("历史请求用途").selectOption("reconstruction");
	await form.getByLabel("策略版本").selectOption("1");
	await form.getByLabel("开始日期").fill("2026-10-08");
	await form.getByLabel("结束日期").fill("2026-11-06");
	await form.getByLabel("初始资金（元）").fill("250000");
	await form.getByRole("button", { name: "提交回测", exact: true }).focus();
	await page.keyboard.press("Enter");
	const link = form.getByRole("link", { name: "查看本次回测" });
	await expect(link).toBeVisible();
	const runId = (await link.getAttribute("href"))?.split("/").at(-1);
	expect(runId).toBeTruthy();
	await link.click();
	await expect(page.getByTestId("backtest-detail-meta")).toContainText("completed", { timeout: 60000 });
	return runId as string;
}

test("financial factors enter stock selection by announcement time inside one ordinary run", async ({ page, request }) => {
	const errors: string[] = [];
	page.on("pageerror", (error) => errors.push(error.message));
	const runId = await submitHistoricalRun(page);
	originalRunId = runId;

	// Persisted boundary re-read: the frozen request keeps publication and
	// source boundaries (disclosure snapshots with real receipt times).
	const [requestPayload, reportPayload, tradesPayload, navPayload] = await Promise.all([
		request.get(`${apiOrigin}/api/v1/backtests/runs/${runId}/request`),
		request.get(`${apiOrigin}/api/v1/backtests/runs/${runId}/report`),
		request.get(`${apiOrigin}/api/v1/backtests/runs/${runId}/trades`),
		request.get(`${apiOrigin}/api/v1/backtests/runs/${runId}/nav`),
	]);
	const saved = (await requestPayload.json()).data;
	originalRequest = saved;
	originalReport = (await reportPayload.json()).data;
	originalTrades = (await tradesPayload.json()).data;
	expect(saved.input_status).toBe("ready");
	expect(saved.members).toEqual(["000001.SZ", "600001.SH"]);
	const incomeSource = saved.sources.find(
		(source: { dataset: string }) => source.dataset === "income_statement",
	) as { received_at: string };
	const balanceSource = saved.sources.find(
		(source: { dataset: string }) => source.dataset === "balance_sheet",
	) as { received_at: string };
	expect(incomeSource).toBeTruthy();
	expect(Date.parse(incomeSource.received_at)).toBeGreaterThanOrEqual(Date.UTC(2026, 0, 1));
	expect(balanceSource).toBeTruthy();
	expect((await navPayload.json()).data.length).toBeGreaterThan(0);

	// The same run consumed disclosure versions per session:
	// B has no position before its announcement becomes visible.
	const trades = originalTrades as { instrument_id: number; entry_date: string; exit_date: string }[];
	const bTrades = trades.filter((trade) => trade.instrument_id === STOCK_B);
	expect(bTrades).toHaveLength(1);
	expect(bTrades[0]?.entry_date).toBe("2026-10-14");
	// The 2026-10-20 revision flips the ranking on 2026-10-21.
	expect(bTrades[0]?.exit_date).toBe("2026-10-21");
	// A is displaced by B on the announcement session and re-selected afterwards.
	const aExits = trades
		.filter((trade) => trade.instrument_id === STOCK_A)
		.map((trade) => trade.exit_date);
	expect(aExits).toContain("2026-10-14");
	expect(aExits.every((day) => day <= "2026-10-21")).toBe(true);

	// Reload persists the frozen evidence view.
	await page.reload();
	await expect(page.getByTestId("backtest-detail-meta")).toContainText("completed");
	const disclosure = page.locator("summary").filter({ hasText: "请求与冻结来源" });
	await disclosure.focus();
	await page.keyboard.press("Enter");
	await expect(page.getByText(/输入预检通过/)).toBeVisible();
	await expect(page.getByText(/请求区间 2026-10-08/)).toBeVisible();

	// The export keeps the run identity in its artifact name.
	await page.getByRole("button", { name: "导出报告" }).focus();
	await page.keyboard.press("Enter");
	const download = page.waitForEvent("download");
	await page.getByRole("button", { name: "下载 JSON" }).click();
	await expect((await download).suggestedFilename()).toBe(`${runId}-report.json`);

	const accessibility = await new AxeBuilder({ page }).analyze();
	expect(accessibility.violations.filter((v) => ["critical", "serious"].includes(v.impact ?? ""))).toEqual([]);
	expect(errors).toEqual([]);
});

test("late-arriving revision keeps the frozen run and reruns into a new identity", async ({ page, request }) => {
	const errors: string[] = [];
	page.on("pageerror", (error) => errors.push(error.message));
	// A disclosure retained after the first freeze must not rewrite it.
	const repair = await request.post(`${apiOrigin}/system-fixture/financial-factors/repair`);
	expect(repair.ok()).toBeTruthy();

	const [requestAgain, reportAgain, tradesAgain] = await Promise.all([
		request.get(`${apiOrigin}/api/v1/backtests/runs/${originalRunId}/request`),
		request.get(`${apiOrigin}/api/v1/backtests/runs/${originalRunId}/report`),
		request.get(`${apiOrigin}/api/v1/backtests/runs/${originalRunId}/trades`),
	]);
	expect((await requestAgain.json()).data).toEqual(originalRequest);
	expect((await reportAgain.json()).data).toEqual(originalReport);
	expect((await tradesAgain.json()).data).toEqual(originalTrades);

	// Rerunning along the same configuration consumes the new evidence under a
	// new run identity: the late revision (announced 2026-10-23) re-selects B
	// from 2026-10-26, closing the re-entered A position that day.
	const runId = await submitHistoricalRun(page);
	expect(runId).not.toBe(originalRunId);
	const newTrades = (await (await request.get(`${apiOrigin}/api/v1/backtests/runs/${runId}/trades`)).json())
		.data as { instrument_id: number; entry_date: string; exit_date: string }[];
	const flip = newTrades.find(
		(trade) => trade.instrument_id === STOCK_A && trade.entry_date === "2026-10-21",
	);
	expect(flip?.exit_date).toBe("2026-10-26");
	const bReentry = newTrades.filter((trade) => trade.instrument_id === STOCK_B);
	expect(bReentry.map((trade) => trade.entry_date)).toEqual(["2026-10-14"]);

	// The old run is still readable with its original identity.
	await page.goto(`${webOrigin}/research/backtests/${originalRunId}`);
	await expect(page.getByTestId("backtest-detail-meta")).toContainText("completed");
	const accessibility = await new AxeBuilder({ page }).analyze();
	expect(accessibility.violations.filter((v) => ["critical", "serious"].includes(v.impact ?? ""))).toEqual([]);
	expect(errors).toEqual([]);
});
