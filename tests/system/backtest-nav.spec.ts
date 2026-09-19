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
		test("renders overlay, excess and underwater panes with KPI-consistent readouts", async ({
			page,
		}) => {
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
			await expect(
				page.locator(`[data-testid='chart-readout-backtest-nav-${RUN_WITH_BENCHMARK}-nav']`),
			).toContainText(/\d/);
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
			const deepest = await page
				.locator('[data-info-unit="nav-summary"] dt:has-text("最深回撤") + dd')
				.textContent();
			expect(deepest).toMatch(/^−\d+\.\d+%/);
			// KPI 展示 1 位小数、水下曲线 2 位小数：数值一致（容差 0.1 个百分点）
			const deepestNumber = Number.parseFloat((deepest ?? "").replace("−", ""));
			const kpiNumber = Number.parseFloat(kpiValue);
			expect(Math.abs(deepestNumber - kpiNumber)).toBeLessThanOrEqual(0.1);

			await expectNoSeriousAccessibilityViolations(page);
			expect(browserErrors).toEqual([]);
		});

		test("keyboard journey: pan and zoom the NAV cockpit without leaving focus", async ({
			page,
		}) => {
			const browserErrors = captureBrowserErrors(page);
			await page.goto(`${webOrigin}/research/backtests/${RUN_WITH_BENCHMARK}`);
			const host = page.locator(`[data-chart-interaction-contract="backtest-nav-${RUN_WITH_BENCHMARK}"]`);
			await expect(host).toBeVisible();
			await host.focus();
			const initial = (await host.getAttribute("data-chart-visible-range")) ?? "";
			await page.keyboard.press("ArrowRight");
			await expect
				.poll(async () => (await host.getAttribute("data-chart-visible-range")) ?? "")
				.not.toBe(initial);
			const panned = (await host.getAttribute("data-chart-visible-range")) ?? "";
			await page.keyboard.press("+");
			await page.keyboard.press("End");
			await expect
				.poll(async () => (await host.getAttribute("data-chart-visible-range")) ?? "")
				.not.toBe(panned);
			expect(browserErrors).toEqual([]);
		});

		test("run without a configured benchmark degrades to nav-only with an explicit state", async ({
			page,
		}) => {
			const browserErrors = captureBrowserErrors(page);
			await page.goto(`${webOrigin}/research/backtests/${RUN_NO_BENCHMARK}`);

			const host = page.locator(`[data-chart-interaction-contract="backtest-nav-${RUN_NO_BENCHMARK}"]`);
			await expect(host).toBeVisible();
			// 未配置基准：主图 + 回撤副图 = 2 panes，无基准/超额
			await expect(host).toHaveAttribute("data-chart-panes", "2");
			await expect(
				page.locator(`[data-testid='chart-readout-backtest-nav-${RUN_NO_BENCHMARK}-benchmark']`),
			).toHaveCount(0);
			await expect(
				page.locator(`[data-testid='chart-readout-backtest-nav-${RUN_NO_BENCHMARK}-excess']`),
			).toHaveCount(0);
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
