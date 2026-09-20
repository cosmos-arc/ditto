import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

/**
 * #215 ②：回测目录多 run 净值叠加对比。
 * 真实引擎 fixture（backtest_nav_app）含两个已完成 run（sys-fx-nav-001/002，
 * 各自落盘 nav 与 report）；断言勾选 ≥2 run 后叠加图 + 指标差异表 + 图例开关。
 */

function requiredEnvironment(name: string): string {
	const value = process.env[name]?.trim();
	if (!value) throw new Error(`${name} is required`);
	return value;
}

const webOrigin = requiredEnvironment("DITTO_SYSTEM_WEB_ORIGIN");

// fixture 常量（tests/system/fixtures/backtest_nav_app.py）
const RUN_A = "sys-fx-nav-001";
const RUN_B = "sys-fx-nav-002";

function captureBrowserErrors(page: Page): string[] {
	const errors: string[] = [];
	page.on("pageerror", (error) => errors.push(error.message));
	page.on("console", (message) => {
		if (message.type() === "error") errors.push(message.text());
	});
	return errors;
}

test.describe.serial("backtest catalog multi-run NAV overlay", () => {
	test("overlays two completed runs with legend toggles and a metrics diff table", async ({ page }) => {
		const browserErrors = captureBrowserErrors(page);
		await page.goto(`${webOrigin}/research/backtests`);

		// 勾选两个 run 进入对比集合（上限 8）
		await page.getByRole("checkbox", { name: `加入对比 ${RUN_A}` }).check();
		await page.getByRole("checkbox", { name: `加入对比 ${RUN_B}` }).check();
		await expect(page.getByTestId("compare-selection-count")).toContainText("2/8");

		await page.getByRole("button", { name: "回测对比" }).click();
		const dialog = page.getByRole("dialog", { name: "回测对比" });
		await expect(dialog).toBeVisible();

		// 真实 cockpit：两条归一化净值序列 + canvas
		const compare = dialog.getByTestId("backtest-multi-run-compare");
		await expect(compare).toBeVisible();
		const chartHost = page.locator('[data-chart-interaction-contract="backtest-multi-run-nav"]');
		await expect(chartHost).toBeVisible();
		await expect(chartHost.locator("canvas").first()).toBeVisible();

		// 图例开关：隐藏 run B 后序列退出叠加（chip aria-pressed false）
		const legend = dialog.getByTestId("multi-run-legend");
		await expect(legend.getByRole("button", { name: RUN_A })).toHaveAttribute("data-legend-visible", "true");
		await legend.getByRole("button", { name: RUN_B }).click();
		await expect(legend.getByRole("button", { name: RUN_B })).toHaveAttribute("data-legend-visible", "false");

		// 指标差异表：两个 run 均已发布 report，行呈现引擎百分数口径
		const table = dialog.getByTestId("multi-run-metrics");
		for (const runId of [RUN_A, RUN_B]) {
			await expect(table.locator(`tr[data-run-id='${runId}']`)).toHaveAttribute("data-report-published", "true");
			await expect(table.locator(`tr[data-run-id='${runId}']`)).toContainText(/%/);
		}

		const accessibility = await new AxeBuilder({ page }).analyze();
		const serious = accessibility.violations.filter((violation) =>
			["critical", "serious"].includes(violation.impact ?? ""),
		);
		expect(serious).toEqual([]);
		expect(browserErrors).toEqual([]);
	});
});
