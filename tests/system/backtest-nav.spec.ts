import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

function requiredEnvironment(name: string): string {
	const value = process.env[name]?.trim();
	if (!value) throw new Error(`${name} is required`);
	return value;
}

const webOrigin = requiredEnvironment("DITTO_SYSTEM_WEB_ORIGIN");

// fixture 常量（tests/system/fixtures/backtest_nav_app.py）：
// sys-fx-nav-001 配置基准（行情挖空 5 日 → 断口）；sys-fx-nav-002 未配置基准。
const RUN_WITH_BENCHMARK = "sys-fx-nav-001";
const RUN_NO_BENCHMARK = "sys-fx-nav-002";

function captureBrowserErrors(page: Page): string[] {
	const errors: string[] = [];
	page.on("pageerror", (error) => errors.push(error.message));
	page.on("console", (message) => {
		if (message.type() === "error") errors.push(message.text());
	});
	return errors;
}

async function expectNoSeriousAccessibilityViolations(page: Page): Promise<void> {
	const accessibility = await new AxeBuilder({ page }).analyze();
	const serious = accessibility.violations.filter((violation) =>
		["critical", "serious"].includes(violation.impact ?? ""),
	);
	expect(serious).toEqual([]);
}

test.describe
	.serial("backtest NAV vs benchmark cockpit over a real engine run", () => {
		test("renders overlay, excess and underwater panes with KPI-consistent readouts", async ({ page }) => {
			const browserErrors = captureBrowserErrors(page);
			await page.goto(`${webOrigin}/research/backtests/${RUN_WITH_BENCHMARK}`);

			// KPI strip 与图表同页呈现（引擎 alpha_stats 为百分数单位）
			const kpiMaxDrawdown = page
				.locator("[data-testid='backtest-detail-meta'] [data-slot='metric']")
				.filter({ hasText: "最大回撤" })
				.locator("span")
				.filter({ hasText: /%$/ });
			await expect(kpiMaxDrawdown).toBeVisible();
			const kpiValue = (await kpiMaxDrawdown.textContent()) ?? "";

			const host = page.locator(`[data-chart-interaction-contract="backtest-nav-${RUN_WITH_BENCHMARK}"]`);
			await expect(host).toBeVisible();
			await expect(host.locator("canvas").first()).toBeVisible();
			// 主图（净值+基准）+ 超额副图 + 回撤副图 = 3 panes，共享时间轴与十字线
			await expect(host).toHaveAttribute("data-chart-panes", "3");

			// 图例读数：策略净值/基准/超额/回撤 四芯片（默认锚定最后非空点）
			await expect(page.locator(`[data-testid='chart-readout-backtest-nav-${RUN_WITH_BENCHMARK}-nav']`)).toContainText(
				/\d/,
			);
			await expect(
				page.locator(`[data-testid='chart-readout-backtest-nav-${RUN_WITH_BENCHMARK}-benchmark']`),
			).toContainText(/\d/);
			await expect(
				page.locator(`[data-testid='chart-readout-backtest-nav-${RUN_WITH_BENCHMARK}-excess']`),
			).toContainText(/[+−]/);
			// 默认读数锚定末点（回撤可能已修复为 0.00%）
			await expect(
				page.locator(`[data-testid='chart-readout-backtest-nav-${RUN_WITH_BENCHMARK}-drawdown']`),
			).toContainText(/\d+\.\d+%/);

			// 基准 5 日挖空 → partial 断口标注（不插值）
			await expect(page.getByText(/基准缺口 1 处/)).toBeVisible();
			await expect(page.locator('[data-state="benchmark-partial"]')).toBeVisible();

			// 同口径交叉验证：aside 水下最深读数 == KPI 最大回撤（符号相反、数值一致）
			const deepest = await page.locator('[data-info-unit="nav-summary"] dt:has-text("最深回撤") + dd').textContent();
			expect(deepest).toMatch(/^−\d+\.\d+%/);
			// KPI 展示 1 位小数、水下曲线 2 位小数：数值一致（容差 0.1 个百分点）
			const deepestNumber = Number.parseFloat((deepest ?? "").replace("−", ""));
			const kpiNumber = Number.parseFloat(kpiValue);
			expect(Math.abs(deepestNumber - kpiNumber)).toBeLessThanOrEqual(0.1);

			await expectNoSeriousAccessibilityViolations(page);
			expect(browserErrors).toEqual([]);
		});

		test("keyboard journey: pan and zoom the NAV cockpit without leaving focus", async ({ page }) => {
			const browserErrors = captureBrowserErrors(page);
			await page.goto(`${webOrigin}/research/backtests/${RUN_WITH_BENCHMARK}`);
			const host = page.locator(`[data-chart-interaction-contract="backtest-nav-${RUN_WITH_BENCHMARK}"]`);
			await expect(host).toBeVisible();
			await host.focus();
			const initial = (await host.getAttribute("data-chart-visible-range")) ?? "";
			await page.keyboard.press("ArrowRight");
			await expect.poll(async () => (await host.getAttribute("data-chart-visible-range")) ?? "").not.toBe(initial);
			const panned = (await host.getAttribute("data-chart-visible-range")) ?? "";
			await page.keyboard.press("+");
			await page.keyboard.press("End");
			await expect.poll(async () => (await host.getAttribute("data-chart-visible-range")) ?? "").not.toBe(panned);
			expect(browserErrors).toEqual([]);
		});

		test("run without a configured benchmark degrades to nav-only with an explicit state", async ({ page }) => {
			const browserErrors = captureBrowserErrors(page);
			await page.goto(`${webOrigin}/research/backtests/${RUN_NO_BENCHMARK}`);

			const host = page.locator(`[data-chart-interaction-contract="backtest-nav-${RUN_NO_BENCHMARK}"]`);
			await expect(host).toBeVisible();
			// 未配置基准：主图 + 回撤副图 = 2 panes，无基准/超额
			await expect(host).toHaveAttribute("data-chart-panes", "2");
			await expect(
				page.locator(`[data-testid='chart-readout-backtest-nav-${RUN_NO_BENCHMARK}-benchmark']`),
			).toHaveCount(0);
			await expect(page.locator(`[data-testid='chart-readout-backtest-nav-${RUN_NO_BENCHMARK}-excess']`)).toHaveCount(
				0,
			);
			await expect(
				page.locator('[data-state="benchmark-unavailable"]').filter({
					hasText: "本运行未配置基准",
				}),
			).toBeVisible();

			await expectNoSeriousAccessibilityViolations(page);
			// 404 = 未配置基准的诚实响应（本用例的被测状态），语义已由上面的显式状态断言覆盖。
			expect(browserErrors.filter((line) => !line.includes("status of 404"))).toEqual([]);
		});
	});

test("strategy detail submits an exact ordinary version and recovers a lost response without another run", async ({
	page,
}) => {
	const strategyId = "seed_etf_trend_swing";
	const submissions: { key: string | undefined; body: unknown; runId: string }[] = [];
	await page.route("**/api/v1/backtests/runs", async (route) => {
		if (route.request().method() !== "POST") return route.continue();
		const response = await route.fetch();
		expect(response.status()).toBe(202);
		const payload = await response.json();
		expect(typeof payload.data.run_id).toBe("string");
		submissions.push({
			key: route.request().headers()["idempotency-key"],
			body: route.request().postDataJSON(),
			runId: payload.data.run_id,
		});
		if (submissions.length === 1) return route.abort("failed");
		return route.fulfill({ response });
	});
	await page.goto(`${webOrigin}/research/strategies/${strategyId}`);
	await page.getByRole("button", { name: "提交回测", exact: true }).click();
	const form = page.getByRole("dialog", { name: "提交回测" });
	await expect(form.getByLabel("策略版本")).toHaveValue("2");
	await expect(form.getByRole("option", { name: /^v1/ })).toHaveCount(1);
	await form.getByLabel("策略版本").selectOption("1");
	await form.getByLabel("开始日期").fill("2025-01-02");
	await form.getByLabel("结束日期").fill("2025-01-31");
	await form.getByLabel("初始资金（元）").fill("250000.50");
	await form.getByLabel("允许实验数据").check();
	await form.getByRole("button", { name: "提交回测", exact: true }).focus();
	await page.keyboard.press("Enter");
	await expect(form.getByRole("alert")).toBeVisible();
	await page.reload();
	await page.getByRole("button", { name: "提交回测", exact: true }).click();
	await expect(form.getByLabel("策略版本")).toHaveValue("1");
	await expect(form.getByLabel("初始资金（元）")).toHaveValue("250000.50");
	await form.getByRole("button", { name: "提交回测", exact: true }).click();
	const link = form.getByRole("link", { name: "查看本次回测" });
	await expect(link).toBeVisible();
	expect(submissions).toHaveLength(2);
	expect(submissions[0]?.key).toBeTruthy();
	expect(submissions[1]).toEqual(submissions[0]);
	expect(submissions[0]?.body).toEqual({
		strategy_id: strategyId,
		strategy_version: 1,
		start_date: "2025-01-02",
		end_date: "2025-01-31",
		initial_cash: 250000.5,
		allow_experimental_data: true,
        historical_reconstruction: false,
	});
	const runId = submissions[0]?.runId;
	expect(runId).toBeTruthy();
	await link.click();
	await expect(page).toHaveURL(`${webOrigin}/research/backtests/${encodeURIComponent(runId ?? "")}`);
	await page.reload();
	await expect(page.getByTestId("backtest-detail-meta")).toContainText("v1");
	await expect(page.getByTestId("backtest-detail-meta")).toContainText("failed");
	const apiOrigin = requiredEnvironment("DITTO_SYSTEM_API_ORIGIN");
	const runs = await page.request.get(`${apiOrigin}/api/v1/backtests/runs?strategy_id=${strategyId}`);
	expect(runs.ok()).toBeTruthy();
	const body = await runs.json();
	expect(body.data).toHaveLength(1);
	expect(body.data[0]).toMatchObject({
		run_id: runId,
		strategy_id: strategyId,
		strategy_version: "1",
		status: "failed",
	});
	expect(body.data[0].error_message).toContain("在 2025-01-02 解析到 0 成员");
	await page.goto(`${webOrigin}/research/strategies/${strategyId}`);
	await page.getByRole("button", { name: "提交回测", exact: true }).click();
	await expect(form.getByRole("link", { name: "查看本次回测" })).toBeVisible();
	await expect(form.getByRole("button", { name: "提交回测", exact: true })).toBeDisabled();
	await page.keyboard.press("Escape");
	await expect(page.getByRole("button", { name: "提交回测", exact: true })).toBeFocused();
	expect(submissions).toHaveLength(2);
});

test.describe("backtest catalog column alignment", () => {
	// 表头与数据列的几何对齐是视觉合同：程序化断言（getBoundingClientRect 级），
	// 逐列左缘差 ≤2px，跨三个视口；相邻列之间保持可见间隙。
	const VIEWPORTS = [
		{ width: 1512, height: 900 },
		{ width: 1280, height: 800 },
		{ width: 1024, height: 768 },
	];

	test("header cells sit above their data columns with visible column gaps", async ({ page }) => {
		const browserErrors = captureBrowserErrors(page);
		for (const viewport of VIEWPORTS) {
			await page.setViewportSize(viewport);
			await page.goto(`${webOrigin}/research/backtests`);
			const firstRow = page.locator("button[aria-label^='选择回测']").first();
			await expect(firstRow).toBeVisible();
			const headerCells = page.getByTestId("runs-header-row").locator("div > *");
			const rowCells = firstRow.locator("> *");
			expect(await headerCells.count()).toBe(5);
			expect(await rowCells.count()).toBe(5);
			const headerBoxes = [];
			const rowBoxes = [];
			for (let index = 0; index < 5; index += 1) {
				headerBoxes.push(await headerCells.nth(index).boundingBox());
				rowBoxes.push(await rowCells.nth(index).boundingBox());
			}
			for (let index = 0; index < 5; index += 1) {
				const header = headerBoxes[index];
				const cell = rowBoxes[index];
				expect(header, `header cell ${index}`).not.toBeNull();
				expect(cell, `data cell ${index}`).not.toBeNull();
				expect(Math.abs((header?.x ?? 0) - (cell?.x ?? 0)), `column ${index} left edge @${viewport.width}`).toBeLessThanOrEqual(2);
			}
			for (let index = 1; index < 5; index += 1) {
				const gap = (rowBoxes[index]?.x ?? 0) - ((rowBoxes[index - 1]?.x ?? 0) + (rowBoxes[index - 1]?.width ?? 0));
				expect(gap, `visible gap before column ${index} @${viewport.width}`).toBeGreaterThanOrEqual(8);
			}
		}
		expect(browserErrors).toEqual([]);
	});
});
