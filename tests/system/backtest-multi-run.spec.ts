import AxeBuilder from "@axe-core/playwright";
import { readFile } from "node:fs/promises";
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

test.describe
	.serial("backtest catalog multi-run NAV overlay", () => {
		test("overlays two completed runs with legend toggles and a metrics diff table", async ({ page }) => {
			const browserErrors = captureBrowserErrors(page);
			await page.goto(`${webOrigin}/research/backtests`);

			// 从目录加入 B，经正式详情入口加入 A；整页导航与刷新均读取同一会话集合。
			await page.getByRole("checkbox", { name: `加入对比 ${RUN_B}` }).check();
			await page.getByRole("button", { name: `选择回测 ${RUN_A}` }).click();
			await page.getByRole("link", { name: "打开回测结果" }).click();
			await page.getByRole("button", { name: "加入对比", exact: true }).click();
			await expect(page.getByRole("status")).toContainText("已加入对比");
			await page.reload();
			await expect(page.getByRole("button", { name: "移出对比", exact: true })).toBeVisible();
			const detailCompare = page.getByRole("button", { name: "对比视图", exact: true });
			await detailCompare.focus();
			await page.keyboard.press("Enter");
			const detailDialog = page.getByRole("dialog", { name: "回测对比" });
			await expect(detailDialog.getByRole("list", { name: "对比集合" }).getByRole("listitem")).toHaveCount(2);
			await page.keyboard.press("Escape");
			await expect(detailDialog).not.toBeVisible();
			await expect(detailCompare).toBeFocused();
			await page.getByRole("button", { name: "移出对比", exact: true }).click();
			await expect(page.getByRole("status")).toContainText("已移出对比");
			await page.getByRole("button", { name: "加入对比", exact: true }).click();
			await page.goto(`${webOrigin}/research/backtests`);
			await expect(page.getByRole("checkbox", { name: `加入对比 ${RUN_A}` })).toBeChecked();
			await expect(page.getByRole("checkbox", { name: `加入对比 ${RUN_B}` })).toBeChecked();
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

			// 比较前口径核对：五轴表格 + 逐 run 结论；fixture 两 run 同口径均并入叠加
			const caliber = dialog.getByTestId("multi-run-caliber");
			await expect(caliber).toBeVisible();
			for (const runId of [RUN_A, RUN_B]) {
				await expect(caliber.locator(`tr[data-run-id='${runId}']`)).toHaveAttribute(
					"data-caliber-comparable",
					"true",
				);
				await expect(caliber.locator(`tr[data-run-id='${runId}']`)).toContainText("并入叠加");
			}
			// 对称未记录轴披露为未核对，而不是假装可比
			const disclosure = dialog.getByTestId("multi-run-caliber-disclosure");
			await expect(disclosure).toContainText(/未核对轴/);

			// 一致导出：对比 CSV 与表内展示串同值（键盘可达）
			const exportButton = dialog.getByRole("button", { name: "导出对比 CSV" });
			await exportButton.focus();
			const downloaded = page.waitForEvent("download");
			await page.keyboard.press("Enter");
			const download = await downloaded;
			expect(download.suggestedFilename()).toBe("backtest-compare.csv");
			const csvPath = await download.path();
			if (!csvPath) throw new Error("comparison CSV download missing");
			const csv = await readFile(csvPath, "utf8");
			// 身份注释行携带集合成员（顺序跟随会话选择序，不预设排序）
			const comparisonLine = csv.split("\n")[0] ?? "";
			expect(comparisonLine).toContain("# comparison=");
			expect(comparisonLine).toContain(RUN_A);
			expect(comparisonLine).toContain(RUN_B);
			// 口径列与结论列同表格文本；指标单元格与差异表同值
			expect(csv).toContain("并入叠加");
			for (const runId of [RUN_A, RUN_B]) {
				const displayed = await table.locator(`tr[data-run-id='${runId}']`).innerText();
				const annualized = displayed.match(/-?\d+\.\d+%/g)?.[0];
				if (annualized) expect(csv).toContain(annualized);
			}

			const accessibility = await new AxeBuilder({ page }).analyze();
			const serious = accessibility.violations.filter((violation) =>
				["critical", "serious"].includes(violation.impact ?? ""),
			);
			expect(serious).toEqual([]);
			expect(browserErrors).toEqual([]);

			// 集合内移除写回会话；再次刷新及列表重选使用同一集合。
			await dialog.getByRole("button", { name: `移出对比 ${RUN_A}` }).click();
			await page.keyboard.press("Escape");
			await expect(page.getByRole("button", { name: "回测对比", exact: true })).toBeFocused();
			await page.reload();
			await expect(page.getByRole("checkbox", { name: `加入对比 ${RUN_A}` })).not.toBeChecked();
			await expect(page.getByTestId("compare-selection-count")).toContainText("1/8");
			await page.getByRole("checkbox", { name: `加入对比 ${RUN_B}` }).uncheck();
			await expect(page.getByTestId("compare-selection-count")).toContainText("0/8");
		});
	});
