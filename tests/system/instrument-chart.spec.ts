import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

function requiredEnvironment(name: string): string {
	const value = process.env[name]?.trim();
	if (!value) throw new Error(`${name} is required`);
	return value;
}

const webOrigin = requiredEnvironment("DITTO_SYSTEM_WEB_ORIGIN");

const ETF_ID = 2000001;
const ETF_NO_NAV_ID = 2000002;
const STOCK_ID = 1000001;

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
	.serial("instrument chart candles over a seeded production API", () => {
		test("renders ETF candles, gap annotation and primary answer with zero console errors", async ({
			page,
		}) => {
			const browserErrors = captureBrowserErrors(page);
			await page.goto(`${webOrigin}/instruments/${ETF_ID}?tab=chart`);

			const host = page.locator(`[data-chart-interaction-contract="instrument-candles-${ETF_ID}"]`);
			await expect(host).toBeVisible();
			await expect(host.locator("canvas").first()).toBeVisible();

			// Primary Answer：最新收盘 + 涨跌 + 区间（真实 API 数据）
			const answer = page.locator("[data-primary-answer]");
			await expect(answer).toBeVisible();
			await expect(answer).toContainText(/收盘/);
			// partial：断口范围标注（fixture 挖空 6 个交易日 → 单处缺口）
			await expect(page.getByText(/缺口 .+ →/)).toBeVisible();

			// 指标开关（日线周期下可用）：MACD+RSI 副图让 pane 数从 2（价格+量）变 4
			const host2 = page.locator(`[data-chart-interaction-contract="instrument-candles-${ETF_ID}"]`);
			await expect(host2).toHaveAttribute("data-chart-panes", "2");
			await page.getByTestId("indicator-toggle-macd").check();
			await page.getByTestId("indicator-toggle-rsi").check();
			await expect(host2).toHaveAttribute("data-chart-panes", "4");

			// ETF 净值叠加（fixture 已播种净值）+ 刷新后开关保持（页面级持久化）
			await page.getByTestId("indicator-toggle-nav").check();
			await expect(page.locator('[data-state="nav-unavailable"]')).toHaveCount(0);
			await page.reload();
			await expect(
				page.locator(`[data-chart-interaction-contract="instrument-candles-${ETF_ID}"]`),
			).toBeVisible();
			await expect(host2).toHaveAttribute("data-chart-panes", "4");
			await expect(page.getByTestId("indicator-toggle-rsi")).toBeChecked();
			await expect(page.getByTestId("indicator-toggle-nav")).toBeChecked();

			// 周期切周线：本地重采样，指标仅日线（开关禁用并说明）
			await page.getByRole("button", { name: "周" }).click();
			await expect(host).toHaveAttribute("aria-label", /周K 线/);
			await expect(host2).toHaveAttribute("data-chart-panes", "2");
			await expect(page.getByTestId("indicator-toggle-rsi")).toBeDisabled();
			await expect(page.getByText("指标叠加仅日线周期")).toBeVisible();

			// ETF 复权未接线：切换禁用并给出原因
			await expect(page.getByRole("button", { name: "前复权" })).toBeDisabled();
			await expect(page.getByText("ETF 复权暂未接入")).toBeVisible();

			await expectNoSeriousAccessibilityViolations(page);
			expect(browserErrors).toEqual([]);
		});

		test("ETF without local NAV data degrades to an explicit unavailable state", async ({ page }) => {
			const browserErrors = captureBrowserErrors(page);
			await page.goto(`${webOrigin}/instruments/${ETF_NO_NAV_ID}?tab=chart`);
			await page.getByTestId("indicator-toggle-nav").check();
			await expect(page.locator('[data-state="nav-unavailable"]')).toBeVisible();
			expect(browserErrors.filter((line) => !line.includes("status of 400"))).toEqual([]);
		});

		test("stocks stay fail-closed until the explicit experimental opt-in, then adjust locally", async ({
			page,
		}) => {
			const browserErrors = captureBrowserErrors(page);
			await page.goto(`${webOrigin}/instruments/${STOCK_ID}?tab=chart`);

			// 默认 fail-closed：experimental 成熟度门控可见
			await expect(page.locator('[data-state="experimental-disabled"]')).toBeVisible();

			// 显式研究开关后渲染真实蜡烛
			await page.getByTestId("chart-experimental-toggle").check();
			const host = page.locator(`[data-chart-interaction-contract="instrument-candles-${STOCK_ID}"]`);
			await expect(host).toBeVisible();
			const answer = page.locator("[data-primary-answer]");
			await expect(answer).toBeVisible();
			const rawClose = (await answer.locator("[data-answer-metric]").first().innerText()).trim();
			const rawScope = (await answer.locator("[data-answer-scope]").innerText()).trim();

			// 前复权（本地因子自算）：最新收盘锚定不变（最新因子即基准），
			// 7 月前历史价格整体下修 → 区间低值改变。
			await page.getByRole("button", { name: "前复权" }).click();
			await expect(page.getByText(/复权：qfq/)).toBeVisible();
			await expect(answer.locator("[data-answer-metric]").first()).toHaveText(rawClose);
			await expect
				.poll(async () => (await answer.locator("[data-answer-scope]").innerText()).trim())
				.not.toBe(rawScope);

			await expectNoSeriousAccessibilityViolations(page);
			// fail-closed 成熟度门控按设计返回 400，浏览器会把该传输行记入
			// console error（与 outage.spec 对 net::ERR 的处理同 convention）；
			// 语义已由 experimental-disabled 面板断言，这里只要求无其他错误。
			const unexpected = browserErrors.filter((line) => !line.includes("status of 400"));
			expect(unexpected).toEqual([]);
		});
	});
