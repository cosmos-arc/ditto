import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

/**
 * #215 ①（CR 收窄交付）：三组合单 as_of 权重漂移可视化。
 * 真实 fixture（portfolio_agent_app）经生产 comparison query 产出三面两两漂移；
 * 断言矩阵呈现（标的并集 + 现金）、列头图例开关、as_of 可见与零 console error。
 */

function requiredEnvironment(name: string): string {
	const value = process.env[name]?.trim();
	if (!value) throw new Error(`${name} is required`);
	return value;
}

const apiOrigin = requiredEnvironment("DITTO_SYSTEM_API_ORIGIN");

function captureBrowserErrors(page: Page): string[] {
	const errors: string[] = [];
	page.on("pageerror", (error) => errors.push(error.message));
	page.on("console", (message) => {
		if (message.type() === "error") errors.push(message.text());
	});
	return errors;
}

test.describe.serial("portfolio comparison drift matrix over the live fixture", () => {
	test("renders pairwise drift with legend column toggles and as_of visibility", async ({ page, request }) => {
		const browserErrors = captureBrowserErrors(page);
		const fixture = await (await request.get(`${apiOrigin}/system-fixture/portfolio`)).json();
		const identity = fixture.identity;
		const comparisonUrl = new URL(identity.frontend_path, apiOrigin);
		comparisonUrl.pathname = "/api/v1/portfolio/comparison";
		comparisonUrl.searchParams.delete("mode");
		const comparison = (await (await request.get(comparisonUrl.toString())).json()).data;

		await page.goto(identity.frontend_path);
		const chart = page.getByTestId("portfolio-drift-chart");
		await expect(chart).toBeVisible();

		// PIT 语义在图上可见：单一 as_of、同 valuation snapshot
		await expect(page.getByTestId("drift-as-of")).toContainText(`AS OF ${comparison.as_of} · 同快照对比`);
		await expect(chart).toContainText(comparison.valuation_snapshot_id);

		// 行 = 三组合标的并集（600519/510300）+ 现金；列 = 三组两两对比
		for (const rowKey of ["instrument-600519", "instrument-510300", "cash"]) {
			await expect(chart.getByTestId(`drift-cell-${rowKey}-model_vs_paper`)).toBeVisible();
		}
		// fixture 事实：510300 paper 侧未成交（weight 0 vs model 0.30）→ model_vs_paper 漂移 −3000 bps
		await expect(chart.getByTestId("drift-cell-instrument-510300-model_vs_paper")).toContainText("−3000.0 bps");

		// 列头即图例开关：隐藏 MODEL → PAPER 列后该列清空，其余列不受影响
		const modelVsPaper = chart.getByRole("button", { name: /MODEL → PAPER/ });
		await expect(modelVsPaper).toHaveAttribute("aria-pressed", "true");
		await modelVsPaper.click();
		await expect(modelVsPaper).toHaveAttribute("aria-pressed", "false");
		await expect(chart.getByTestId("drift-cell-instrument-510300-model_vs_paper")).toHaveText("");
		await expect(chart.getByTestId("drift-cell-instrument-510300-model_vs_manual")).toContainText(/bps/);
		// 键盘可达：focus 落在开关按钮上
		await expect(modelVsPaper).toBeFocused();

		const accessibility = await new AxeBuilder({ page }).analyze();
		const serious = accessibility.violations.filter((violation) =>
			["critical", "serious"].includes(violation.impact ?? ""),
		);
		expect(serious).toEqual([]);
		expect(browserErrors).toEqual([]);
	});
});
