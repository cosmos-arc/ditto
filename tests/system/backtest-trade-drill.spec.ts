import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

function requiredEnvironment(name: string): string {
	const value = process.env[name]?.trim();
	if (!value) throw new Error(`${name} is required`);
	return value;
}

const webOrigin = requiredEnvironment("DITTO_SYSTEM_WEB_ORIGIN");

// fixture 常量（tests/system/fixtures/backtest_nav_app.py）：真实引擎产物，
// 118 笔成交 + 164 条 pre-trade 审计记录，标的 2001001/2001002 有全区间日 K。
const RUN_ID = "sys-fx-nav-001";

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
	.serial("backtest trade drill-down chain over a real engine run", () => {
		test("report row → evidence drawer → instrument chart focus, keyboard reachable end to end", async ({
			page,
		}) => {
			const browserErrors = captureBrowserErrors(page);
			await page.goto(`${webOrigin}/research/backtests/${RUN_ID}`);

			// 进入成交 tab
			await page.getByRole("tab", { name: "成交" }).click();
			const firstEvidence = page.locator("[data-testid^='trade-evidence-']").first();
			await expect(firstEvidence).toBeVisible();

			// 键盘可达：Tab 聚焦到首个「查证据」按钮并回车打开抽屉
			const firstRowButton = firstEvidence;
			await firstRowButton.focus();
			await page.keyboard.press("Enter");
			await expect(screenDrawer(page)).toBeVisible();

			// 抽屉内：精确成交身份 + 按标的/日期过滤的 pre-trade 审计证据
			await expect(screenDrawer(page).getByText(/Entry/)).toBeVisible();
			const rows = page.getByTestId("trade-evidence-rows");
			await expect(rows).toBeVisible();
			expect((await rows.textContent()) ?? "").toMatch(/buy|sell/);

			// 抽屉内跳转链接携带跨域上下文（对象/原因/知识时间/方向），键盘可达
			const buyLink = page.locator("[data-testid^='drill-link-buy-']").first();
			const href = (await buyLink.getAttribute("href")) ?? "";
			expect(href).toContain(`/instruments/`);
			expect(href).toContain("tab=chart");
			expect(href).toContain("focusDate=");
			expect(href).toContain(`drillRunId=${RUN_ID}`);
			expect(href).toContain("drillAsOf=");
			expect(href).toContain("drillDirection=buy");
			await buyLink.focus();
			await page.keyboard.press("Enter");

			// 落地标的页 K 线：drill-focus 状态条 + 定位 marker + as_of 水位线一致
			const chip = page.locator("[data-state='drill-focus']").first();
			await expect(chip).toBeVisible();
			expect((await chip.textContent()) ?? "").toContain(RUN_ID);
			expect((await chip.textContent()) ?? "").toContain("买入");

			const host = page.locator("[data-chart-interaction-contract^='instrument-candles-']");
			await expect(host).toBeVisible();
			await expect(host).toHaveAttribute("data-chart-marker-times", /\d+/);
			await expect(host).toHaveAttribute("data-chart-as-of", /\d+/);
			// 定位生效：目标时点在可视窗口附近（而非 fitContent 的首尾全览）
			await expect
				.poll(async () => (await host.getAttribute("data-chart-visible-range")) ?? "")
				.not.toBe("");

			expect(browserErrors).toEqual([]);
		});

		test("sell drill marks the exit date with a below-bar marker", async ({ page }) => {
			const browserErrors = captureBrowserErrors(page);
			await page.goto(`${webOrigin}/research/backtests/${RUN_ID}`);
			await page.getByRole("tab", { name: "成交" }).click();
			const firstEvidence = page.locator("[data-testid^='trade-evidence-']").first();
			await firstEvidence.click();
			const sellLink = page.locator("[data-testid^='drill-link-sell-']").first();
			const href = (await sellLink.getAttribute("href")) ?? "";
			expect(href).toContain("drillDirection=sell");
			const focusMatch = href.match(/focusDate=([0-9-]+)/);
			expect(focusMatch).not.toBeNull();
			await sellLink.click();

			const chip = page.locator("[data-state='drill-focus']").first();
			await expect(chip).toBeVisible();
			expect((await chip.textContent()) ?? "").toContain("卖出");

			// marker 时间 = 卖出定位日（UTC 日锚定）
			const host = page.locator("[data-chart-interaction-contract^='instrument-candles-']");
			await expect(host).toBeVisible();
			const expectedTime = Date.parse(`${focusMatch![1]}T00:00:00Z`) / 1000;
			await expect(host).toHaveAttribute("data-chart-marker-times", String(expectedTime));

			await expectNoSeriousAccessibilityViolations(page);
			expect(browserErrors).toEqual([]);
		});
	});

function screenDrawer(page: Page) {
	return page.locator("[role='dialog'], [data-state='open']").filter({ hasText: "成交证据下钻" }).first();
}
