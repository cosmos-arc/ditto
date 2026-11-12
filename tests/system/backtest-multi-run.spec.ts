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
const apiOrigin = requiredEnvironment("DITTO_SYSTEM_API_ORIGIN");

const API_HEADERS = { "X-Ditto-API-Contract-Version": "v1" };

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

		test("saves a research judgment from the comparison and converts it to a sourced plan", async ({ page }) => {
			const browserErrors = captureBrowserErrors(page);
			await page.goto(`${webOrigin}/research/backtests`);
			await page.getByRole("checkbox", { name: `加入对比 ${RUN_A}` }).check();
			await page.getByRole("checkbox", { name: `加入对比 ${RUN_B}` }).check();
			await page.getByRole("button", { name: "回测对比" }).click();
			const dialog = page.getByRole("dialog", { name: "回测对比" });
			const section = dialog.getByTestId("research-judgment-section");
			await expect(section).toBeVisible();

			// 保存判断：绑定明确比较成员 run_ids + 可选后续验证策略@版本（比较成员提供选项）。
			await section.getByLabel("判断结论").fill("两个 run 同口径可比；001 回撤更浅但收益略低，次日优先观察放量修复");
			const strategySelect = section.getByLabel("后续验证策略版本");
			await expect(strategySelect).toContainText("sys-fx-etf-rotation@1");
			await strategySelect.selectOption("sys-fx-etf-rotation@1");
			await section.getByRole("button", { name: "保存研究判断" }).click();
			await expect(section.getByText(/research-judgment:sha256:/).first()).toBeVisible();
			const judgmentId =
				(await section.getByText(/research-judgment:sha256:/).first().textContent()) ?? "";
			expect(judgmentId).toMatch(/^research-judgment:sha256:[0-9a-f]{64}$/u);

			// 重开找回：刷新后从服务端重读，判断条目绑定原 run 身份（链接到各 run 详情）。
			await page.reload();
			await page.getByRole("button", { name: "回测对比" }).click();
			const reopenedSection = page
				.getByRole("dialog", { name: "回测对比" })
				.getByTestId("research-judgment-section");
			const entry = reopenedSection.getByTestId("research-judgment-entry");
			await expect(entry).toContainText(judgmentId);
			await expect(entry).toContainText(RUN_A);
			await expect(entry).toContainText(RUN_B);
			await expect(entry.getByRole("link", { name: RUN_A })).toHaveAttribute(
				"href",
				`/research/backtests/${RUN_A}`,
			);

			// 真实 API 复核：判断绑定明确 run/comparison 身份，不随后续数据漂移。
			const judgment = (await (
				await page.request.get(`${apiOrigin}/api/v1/research/judgments/${judgmentId}`, {
					headers: API_HEADERS,
				})
			).json()) as { data: { run_ids: string[]; strategy_id: string; strategy_version: number } };
			expect(judgment.data.run_ids).toEqual([RUN_A, RUN_B]);
			expect(judgment.data.strategy_id).toBe("sys-fx-etf-rotation");
			expect(judgment.data.strategy_version).toBe(1);

			// 进入验证：既有策略详情页（提交回测入口）+ 返回研究判断回程链接。
			await entry.getByRole("link", { name: /进入验证 sys-fx-etf-rotation@v1/ }).click();
			await expect(page.getByTestId("strategy-detail-meta")).toBeVisible();
			await expect(page.getByRole("button", { name: "提交回测" })).toBeVisible();
			const returnBanner = page.getByTestId("strategy-judgment-return");
			await expect(returnBanner).toContainText(judgmentId);
			await returnBanner.getByRole("link", { name: "返回研究判断" }).click();
			await expect(page).toHaveURL(/\/research\/backtests$/u);

			// 转入次日计划：判断列表的交接链接带 ?judgment= 来源进入计划面板。
			await page.goto(`${webOrigin}/markets/watchlist?judgment=${encodeURIComponent(judgmentId)}`);
			const panel = page.locator('[data-info-unit="watchlist-next-day-plan"]');
			const anchor = await fetchCalendarAnchor(page);
			await expect(panel.getByLabel("观察日期")).toHaveValue(anchor);
			await expect(panel.getByTestId("plan-source-judgment")).toContainText(judgmentId);
			// 真实操作加入自选候选（代码检索 → 保存），不用 API 代替用户动作。
			await page.getByRole("button", { name: "添加标的" }).click();
			await page.getByLabel("搜索代码或名称").fill("510300");
			await page.getByRole("button", { name: "检索" }).click();
			await page.getByRole("button", { name: "加入自选 沪深300ETF-回测验收" }).click();
			await panel.getByRole("checkbox", { name: /回测验收/ }).check();
			await panel.getByLabel("510300 候选理由").fill("按判断结论执行观察：放量收复则保留");
			await panel.getByLabel("次日计划", { exact: true }).fill("次日开盘观察放量修复是否延续");
			await panel.getByRole("button", { name: "保存理由与次日计划" }).click();
			await expect(panel.getByText(/next-day-plan:sha256:/)).toBeVisible();

			// 直接 API 复核：保存的计划携带来源判断身份（UI→API→持久化→重读）。
			const plans = (await (
				await page.request.get(`${apiOrigin}/api/v1/market/next-day-plans`, {
					headers: API_HEADERS,
				})
			).json()) as { data: Array<{ source_judgment_id: string | null }> };
			const sourced = plans.data.filter((item) => item.source_judgment_id === judgmentId);
			expect(sourced).toHaveLength(1);

			// 刷新后已保存条目显示来源，面板重开仍是同一份记录。
			await page.goto(`${webOrigin}/markets/watchlist?judgment=${encodeURIComponent(judgmentId)}`);
			const reopenedPanel = page.locator('[data-info-unit="watchlist-next-day-plan"]');
			const savedList = reopenedPanel.getByRole("region", { name: "已保存理由与次日计划" });
			await expect(savedList).toContainText("次日开盘观察放量修复是否延续");
			await expect(savedList).toContainText(judgmentId);

			expect(browserErrors).toEqual([]);
		});
});

async function fetchCalendarAnchor(page: Page): Promise<string> {
	const response = await page.request.get(`${apiOrigin}/api/v1/ingestion/status`, { headers: API_HEADERS });
	expect(response.status()).toBe(200);
	const payload = (await response.json()).data as {
		datasets: Array<{ dataset: string; latest_date: string | null; latest_status: string | null }>;
	};
	const calendar = payload.datasets.find((dataset) => dataset.dataset === "calendar");
	expect(calendar?.latest_status).toBe("success");
	expect(calendar?.latest_date).toBeTruthy();
	return calendar?.latest_date ?? "";
}
