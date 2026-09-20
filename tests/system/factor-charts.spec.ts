import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

function requiredEnvironment(name: string): string {
	const value = process.env[name]?.trim();
	if (!value) throw new Error(`${name} is required`);
	return value;
}

const webOrigin = requiredEnvironment("DITTO_SYSTEM_WEB_ORIGIN");

// fixture 常量（tests/system/fixtures/factor_series_app.py）：
// 因子秩与次日收益严格同向（IC=1.0），20 只 ETF × 80 交易日。
const FACTOR_ID = "fx-momentum-20";
const SCOPE_QUERY = new URLSearchParams({
	snapshotId: "snap-fx",
	startDate: "2026-01-05",
	endDate: "2026-04-24",
	registryHash: "f".repeat(64),
}).toString();

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
	.serial("factor research charts over the real evaluation stack", () => {
		test("renders IC/IR dual-axis, quantile layers with LS spread, and the monthly heatmap", async ({
			page,
		}) => {
			const browserErrors = captureBrowserErrors(page);
			await page.goto(`${webOrigin}/research/factors/${FACTOR_ID}?${SCOPE_QUERY}`);

			// IC/滚动 IR 双轴图
			const icHost = page.locator(`[data-chart-interaction-contract="factor-ic-${FACTOR_ID}"]`);
			await expect(icHost).toBeVisible();
			await expect(icHost.locator("canvas").first()).toBeVisible();
			// 双轴图例读数：IC 左轴、滚动 IR 右轴
			await expect(
				page.locator(`[data-testid='chart-readout-factor-ic-${FACTOR_ID}-ic']`),
			).toContainText(/1\.000/);
			await expect(
				page.getByTestId(`factor-ic-chart-${FACTOR_ID}`).getByText("Rank IC"),
			).toBeVisible();
			await expect(page.getByText("滚动IR(20d)")).toBeVisible();

			// 分位分层 + 多空 spread（Q1–Q5 六条线）
			const quantileHost = page.locator(
				`[data-chart-interaction-contract="factor-quantile-${FACTOR_ID}"]`,
			);
			await expect(quantileHost).toBeVisible();
			for (const id of ["q_1", "q_2", "q_3", "q_4", "q_5", "ls_spread"]) {
				await expect(
					page.locator(`[data-testid='chart-readout-factor-quantile-${FACTOR_ID}-${id}']`),
				).toBeVisible();
			}

			// 月度 IC 热力图：4 个聚合月份单元格（IC=1.000），缺月占位 —
			const heatmap = page.getByTestId(`factor-monthly-ic-${FACTOR_ID}`);
			await expect(heatmap).toBeVisible();
			expect((await heatmap.textContent()) ?? "").toContain("1.000");
			const januaryCell = heatmap.locator("tbody tr").last().locator("td").first();
			await expect(januaryCell).toContainText(/1\.000|—/);

			// 窗口元信息（真实计算输出）
			await expect(page.getByText(/80 个评估日/)).toBeVisible();

			await expectNoSeriousAccessibilityViolations(page);
			// 不可变诊断制品 404/422（无实验证据/registry hash 不匹配）为诚实响应，语义已由显式状态断言覆盖
			expect(
				browserErrors.filter(
					(line) => !line.includes("status of 404") && !line.includes("status of 422"),
				),
			).toEqual([]);
		});

		test("keyboard journey: pan the IC chart without leaving focus", async ({ page }) => {
			const browserErrors = captureBrowserErrors(page);
			await page.goto(`${webOrigin}/research/factors/${FACTOR_ID}?${SCOPE_QUERY}`);
			const host = page.locator(`[data-chart-interaction-contract="factor-ic-${FACTOR_ID}"]`);
			await expect(host).toBeVisible();
			await host.focus();
			const initial = (await host.getAttribute("data-chart-visible-range")) ?? "";
			await page.keyboard.press("ArrowRight");
			await expect
				.poll(async () => (await host.getAttribute("data-chart-visible-range")) ?? "")
				.not.toBe(initial);
			expect(
				browserErrors.filter(
					(line) => !line.includes("status of 404") && !line.includes("status of 422"),
				),
			).toEqual([]);
		});
	});
